"""Validated WhatsApp startup composition for Govi Mithura."""

from __future__ import annotations

import asyncio
import hmac
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from html import unescape
from typing import Any

from agentkernel.core import AgentReplyText, AgentRequestText, AgentService, Config
from agentkernel.whatsapp import AgentWhatsAppRequestHandler

from settings import ConfigurationError

PHONE_NUMBER_ID_PATTERN = re.compile(r"^\d{6,25}$")
API_VERSION_PATTERN = re.compile(r"^v\d+\.\d+$")
MESSAGE_DEDUP_TTL_SECONDS = 24 * 60 * 60
MESSAGE_DEDUP_MAX_ENTRIES = 4096
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
MARKDOWN_BOLD_PATTERN = re.compile(r"\*\*([^*\n]+)\*\*")
MARKDOWN_ESCAPE_PATTERN = re.compile(r"\\([\\`*_{}\[\]()#+\-.!])")


def _plain_whatsapp_link(match: re.Match[str]) -> str:
    label, url = match.groups()
    plain_label = MARKDOWN_ESCAPE_PATTERN.sub(r"\1", label.strip())
    return url if plain_label == url else f"{plain_label} ({url})"


def normalize_whatsapp_text(text: str) -> str:
    """Translate common model markup into WhatsApp-native plain-text formatting."""
    normalized = unescape(text)
    normalized = MARKDOWN_LINK_PATTERN.sub(_plain_whatsapp_link, normalized)
    normalized = MARKDOWN_BOLD_PATTERN.sub(r"*\1*", normalized)
    return "\n".join(line.rstrip() for line in normalized.splitlines()).strip()


@dataclass(frozen=True)
class WhatsAppStartupSettings:
    """Secrets and identifiers required for the secured WhatsApp webhook."""

    verify_token: str
    access_token: str
    app_secret: str
    phone_number_id: str
    api_version: str = "v25.0"

    @classmethod
    def from_config(cls, whatsapp: Any = None) -> "WhatsAppStartupSettings":
        """Validate the resolved WhatsApp config, never returning secret values in errors.

        Reads Config.get().whatsapp — the same object AgentWhatsAppRequestHandler runs on, and the
        one AKConfig resolves from AK_WHATSAPP__* env vars, .env, and config.yaml. Validating
        os.environ instead would gate on a different set of values than the handler actually uses.
        """
        resolved = Config.get().whatsapp if whatsapp is None else whatsapp
        names = {
            "verify_token": "AK_WHATSAPP__VERIFY_TOKEN",
            "access_token": "AK_WHATSAPP__ACCESS_TOKEN",
            "app_secret": "AK_WHATSAPP__APP_SECRET",
            "phone_number_id": "AK_WHATSAPP__PHONE_NUMBER_ID",
        }
        values = {field: str(getattr(resolved, field, "") or "").strip() for field in names}
        missing = [variable for field, variable in names.items() if not values[field]]
        if missing:
            raise ConfigurationError("Missing required WhatsApp configuration: " + ", ".join(missing))

        api_version = str(getattr(resolved, "api_version", "") or "").strip() or "v25.0"
        if not PHONE_NUMBER_ID_PATTERN.fullmatch(values["phone_number_id"]):
            raise ConfigurationError("AK_WHATSAPP__PHONE_NUMBER_ID must contain 6-25 digits.")
        if not API_VERSION_PATTERN.fullmatch(api_version):
            raise ConfigurationError("AK_WHATSAPP__API_VERSION must use a value such as v25.0.")

        return cls(**values, api_version=api_version)


class GoviMithuraWhatsAppHandler(AgentWhatsAppRequestHandler):
    """Text-only handler with private session identifiers and retry deduplication."""

    def __init__(self, settings: WhatsAppStartupSettings) -> None:
        super().__init__()
        self._session_hmac_key = settings.app_secret.encode()
        self._completed_message_ids: OrderedDict[str, float] = OrderedDict()
        self._in_flight_message_ids: set[str] = set()
        self._dedup_lock = asyncio.Lock()

    def _private_session_id(self, phone_number: str) -> str:
        digest = hmac.digest(self._session_hmac_key, phone_number.encode(), "sha256").hex()
        return f"whatsapp:{digest}"

    async def _claim_message(self, message_id: str) -> bool:
        now = time.monotonic()
        async with self._dedup_lock:
            while self._completed_message_ids:
                oldest_id, seen_at = next(iter(self._completed_message_ids.items()))
                if now - seen_at <= MESSAGE_DEDUP_TTL_SECONDS:
                    break
                self._completed_message_ids.pop(oldest_id)
            if message_id in self._completed_message_ids or message_id in self._in_flight_message_ids:
                return False
            self._in_flight_message_ids.add(message_id)
            return True

    async def _complete_message(self, message_id: str) -> None:
        async with self._dedup_lock:
            self._in_flight_message_ids.discard(message_id)
            self._completed_message_ids[message_id] = time.monotonic()
            while len(self._completed_message_ids) > MESSAGE_DEDUP_MAX_ENTRIES:
                self._completed_message_ids.popitem(last=False)

    async def _release_message(self, message_id: str) -> None:
        async with self._dedup_lock:
            self._in_flight_message_ids.discard(message_id)

    async def _deliver_reply(self, message: dict[str, object], message_id: str, from_number: str) -> None:
        """Answer one claimed message, falling back to a delivered apology on any failure."""
        text_payload = message.get("text")
        if message.get("type") != "text" or not isinstance(text_payload, dict):
            await self._send_message(from_number, "Govi Mithura currently supports text messages only.", message_id)
            return
        text = text_payload.get("body")
        if not isinstance(text, str) or not text.strip():
            return

        service = AgentService()
        try:
            if self._whatsapp_agent_acknowledgement:
                await self._send_message(from_number, self._whatsapp_agent_acknowledgement, message_id)
            service.select(session_id=self._private_session_id(from_number), name=self._whatsapp_agent)
            if not service.agent:
                await self._send_message(from_number, "Govi Mithura is temporarily unavailable.", message_id)
                return
            result = await service.run_multi([AgentRequestText(prompt=text)])
            response_text = result.response if isinstance(result, AgentReplyText) else str(result)
            response_text = normalize_whatsapp_text(response_text)
            if not response_text.strip():
                raise ValueError("Agent returned an empty WhatsApp reply.")
            await self._send_message(from_number, response_text, message_id)
        except Exception as exc:
            self._log.error("WhatsApp message processing failed (%s)", type(exc).__name__)
            await self._send_message(from_number, "Sorry, there was an error processing your request.", message_id)

    async def _handle_message(self, message: dict[str, object], value: dict[str, object]) -> None:
        """Process one text message without exposing the phone number as a session identifier."""
        del value
        message_id = message.get("id")
        from_number = message.get("from")
        if not isinstance(message_id, str) or not isinstance(from_number, str):
            self._log.warning("WhatsApp message missing required sender or message ID")
            return
        if not await self._claim_message(message_id):
            self._log.info("Ignored duplicate WhatsApp message ID")
            return

        # Only an escaping exception means nothing was delivered, so only then is the claim
        # released for a later Meta retry; every other path has answered the farmer.
        try:
            await self._deliver_reply(message, message_id, from_number)
        except BaseException:
            await self._release_message(message_id)
            raise
        await self._complete_message(message_id)


def build_whatsapp_handler() -> GoviMithuraWhatsAppHandler:
    """Fail closed on incomplete security configuration, then build the Agent Kernel handler."""
    settings = WhatsAppStartupSettings.from_config()
    return GoviMithuraWhatsAppHandler(settings)
