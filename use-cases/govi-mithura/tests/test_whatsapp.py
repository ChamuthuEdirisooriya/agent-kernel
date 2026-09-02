"""Offline tests for secured Agent Kernel WhatsApp integration behavior."""

from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from agentkernel.core import AgentReplyText, AgentRequestText, Config
from agentkernel.integration.whatsapp import whatsapp_chat
from fastapi import FastAPI

import whatsapp_runtime
from settings import ConfigurationError
from whatsapp_runtime import (
    GoviMithuraWhatsAppHandler,
    WhatsAppStartupSettings,
    build_whatsapp_handler,
    normalize_whatsapp_text,
)

VALID_ENV = {
    "AK_WHATSAPP__VERIFY_TOKEN": "test-verify-token",
    "AK_WHATSAPP__ACCESS_TOKEN": "test-access-token",
    "AK_WHATSAPP__APP_SECRET": "test-app-secret",
    "AK_WHATSAPP__PHONE_NUMBER_ID": "123456789012345",
    "AK_WHATSAPP__API_VERSION": "v25.0",
}


def test_whatsapp_text_normalization_removes_literal_html_space_entities() -> None:
    raw = (
        "**මූලාශ්‍රය:** [Open-Meteo](https://open-meteo.com/en/docs) &#x20;\n"
        "[https://example.com/food\\_price](https://example.com/food_price)  \n"
    )

    assert normalize_whatsapp_text(raw) == (
        "*මූලාශ්‍රය:* Open-Meteo (https://open-meteo.com/en/docs)\nhttps://example.com/food_price"
    )


@pytest.fixture
def configured_handler(monkeypatch: pytest.MonkeyPatch) -> GoviMithuraWhatsAppHandler:
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)
    config = Config.get().model_copy(deep=True)
    config.whatsapp.verify_token = VALID_ENV["AK_WHATSAPP__VERIFY_TOKEN"]
    config.whatsapp.access_token = VALID_ENV["AK_WHATSAPP__ACCESS_TOKEN"]
    config.whatsapp.app_secret = VALID_ENV["AK_WHATSAPP__APP_SECRET"]
    config.whatsapp.phone_number_id = VALID_ENV["AK_WHATSAPP__PHONE_NUMBER_ID"]
    config.whatsapp.api_version = VALID_ENV["AK_WHATSAPP__API_VERSION"]
    config.whatsapp.agent = "govi_mithura"
    monkeypatch.setattr(Config, "get", classmethod(lambda cls: config))
    return build_whatsapp_handler()


def _whatsapp_config(**overrides: str) -> SimpleNamespace:
    """Build a stand-in for the resolved Config.get().whatsapp block."""
    fields = {key.removeprefix("AK_WHATSAPP__").lower(): value for key, value in VALID_ENV.items()}
    return SimpleNamespace(**{**fields, **overrides})


def test_whatsapp_startup_requires_app_secret() -> None:
    with pytest.raises(ConfigurationError, match="AK_WHATSAPP__APP_SECRET") as error:
        WhatsAppStartupSettings.from_config(_whatsapp_config(app_secret=""))

    assert VALID_ENV["AK_WHATSAPP__ACCESS_TOKEN"] not in str(error.value)


@pytest.mark.parametrize(
    ("name", "invalid_value"),
    [
        ("AK_WHATSAPP__PHONE_NUMBER_ID", "+94 77 123 4567"),
        ("AK_WHATSAPP__API_VERSION", "24"),
    ],
)
def test_whatsapp_startup_rejects_invalid_identifiers(name: str, invalid_value: str) -> None:
    field = name.removeprefix("AK_WHATSAPP__").lower()

    with pytest.raises(ConfigurationError):
        WhatsAppStartupSettings.from_config(_whatsapp_config(**{field: invalid_value}))


@pytest.mark.asyncio
async def test_webhook_verification_requires_matching_token(
    configured_handler: whatsapp_chat.AgentWhatsAppRequestHandler,
) -> None:
    app = FastAPI()
    app.include_router(configured_handler.get_router())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        accepted = await client.get(
            "/whatsapp/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VALID_ENV["AK_WHATSAPP__VERIFY_TOKEN"],
                "hub.challenge": "42",
            },
        )
        rejected = await client.get(
            "/whatsapp/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"},
        )

    assert accepted.status_code == 200
    assert accepted.json() == 42
    assert rejected.status_code == 403


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_hmac_before_processing(
    configured_handler: whatsapp_chat.AgentWhatsAppRequestHandler,
) -> None:
    app = FastAPI()
    app.include_router(configured_handler.get_router())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/whatsapp/webhook",
            json={"object": "whatsapp_business_account", "entry": []},
            headers={"x-hub-signature-256": "sha256=invalid"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_valid_signed_webhook_dispatches_text_message(
    configured_handler: whatsapp_chat.AgentWhatsAppRequestHandler,
) -> None:
    configured_handler._handle_message = AsyncMock()  # type: ignore[method-assign]
    app = FastAPI()
    app.include_router(configured_handler.get_router())
    message = {"id": "wamid.1", "from": "94770000001", "type": "text", "text": {"body": "Hello"}}
    value = {"messages": [message], "metadata": {"phone_number_id": "123456789012345"}}
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": value}]}],
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(VALID_ENV["AK_WHATSAPP__APP_SECRET"].encode(), body, hashlib.sha256).hexdigest()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/whatsapp/webhook",
            content=body,
            headers={"content-type": "application/json", "x-hub-signature-256": f"sha256={digest}"},
        )

    assert response.status_code == 200
    configured_handler._handle_message.assert_awaited_once_with(message, value)


@pytest.mark.asyncio
async def test_text_flow_uses_phone_number_as_isolated_session(
    configured_handler: GoviMithuraWhatsAppHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selections: list[tuple[str, str | None]] = []
    received_text: list[str] = []

    class FakeAgentService:
        agent: object | None = None

        def select(self, session_id: str, name: str | None = None) -> None:
            selections.append((session_id, name))
            self.agent = object()

        async def run_multi(self, requests: list[Any]) -> AgentReplyText:
            assert isinstance(requests[0], AgentRequestText)
            received_text.append(requests[0].prompt)
            return AgentReplyText(response="Govi Mithura response")

    monkeypatch.setattr(whatsapp_runtime, "AgentService", FakeAgentService)
    configured_handler._send_message = AsyncMock()  # type: ignore[method-assign]

    for message_id, phone, text in [
        ("wamid.1", "94770000001", "My crop is chili"),
        ("wamid.2", "94770000001", "Remember my district"),
        ("wamid.3", "94770000002", "My crop is paddy"),
    ]:
        await configured_handler._handle_message(
            {"id": message_id, "from": phone, "type": "text", "text": {"body": text}},
            {},
        )

    assert selections[0][0] == selections[1][0]
    assert selections[0][0] != selections[2][0]
    assert all(session_id.startswith("whatsapp:") for session_id, _ in selections)
    assert all("9477000000" not in session_id for session_id, _ in selections)
    assert all(agent_name == "govi_mithura" for _, agent_name in selections)
    assert received_text == ["My crop is chili", "Remember my district", "My crop is paddy"]
    assert configured_handler._send_message.await_count == 3


@pytest.mark.asyncio
async def test_duplicate_message_id_is_processed_once(
    configured_handler: GoviMithuraWhatsAppHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_count = 0

    class FakeAgentService:
        agent: object | None = None

        def select(self, session_id: str, name: str | None = None) -> None:
            del session_id, name
            self.agent = object()

        async def run_multi(self, requests: list[Any]) -> AgentReplyText:
            nonlocal run_count
            del requests
            run_count += 1
            return AgentReplyText(response="One response")

    monkeypatch.setattr(whatsapp_runtime, "AgentService", FakeAgentService)
    configured_handler._send_message = AsyncMock()  # type: ignore[method-assign]
    message: dict[str, object] = {
        "id": "wamid.duplicate",
        "from": "94770000001",
        "type": "text",
        "text": {"body": "Hello"},
    }

    await configured_handler._handle_message(message, {})
    await configured_handler._handle_message(message, {})

    assert run_count == 1
    assert configured_handler._send_message.await_count == 1


@pytest.mark.asyncio
async def test_empty_agent_reply_sends_fallback_and_completes_message(
    configured_handler: GoviMithuraWhatsAppHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_count = 0

    class FakeAgentService:
        agent: object | None = None

        def select(self, session_id: str, name: str | None = None) -> None:
            del session_id, name
            self.agent = object()

        async def run_multi(self, requests: list[Any]) -> AgentReplyText:
            nonlocal run_count
            del requests
            run_count += 1
            return AgentReplyText(response="   ")

    monkeypatch.setattr(whatsapp_runtime, "AgentService", FakeAgentService)
    configured_handler._send_message = AsyncMock()  # type: ignore[method-assign]
    message: dict[str, object] = {
        "id": "wamid.empty-response",
        "from": "94770000001",
        "type": "text",
        "text": {"body": "Hello"},
    }

    await configured_handler._handle_message(message, {})
    await configured_handler._handle_message(message, {})

    assert run_count == 1
    configured_handler._send_message.assert_awaited_once_with(
        "94770000001",
        "Sorry, there was an error processing your request.",
        "wamid.empty-response",
    )


@pytest.mark.asyncio
async def test_message_id_is_released_when_response_and_fallback_delivery_fail(
    configured_handler: GoviMithuraWhatsAppHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_count = 0

    class FakeAgentService:
        agent: object | None = None

        def select(self, session_id: str, name: str | None = None) -> None:
            del session_id, name
            self.agent = object()

        async def run_multi(self, requests: list[Any]) -> AgentReplyText:
            nonlocal run_count
            del requests
            run_count += 1
            return AgentReplyText(response="Recovered response")

    monkeypatch.setattr(whatsapp_runtime, "AgentService", FakeAgentService)
    configured_handler._send_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=[RuntimeError("response delivery failed"), RuntimeError("fallback delivery failed"), None]
    )
    message: dict[str, object] = {
        "id": "wamid.retry-after-send-failure",
        "from": "94770000001",
        "type": "text",
        "text": {"body": "Hello"},
    }

    with pytest.raises(RuntimeError, match="fallback delivery failed"):
        await configured_handler._handle_message(message, {})
    await configured_handler._handle_message(message, {})

    assert run_count == 2
    assert configured_handler._send_message.await_count == 3


@pytest.mark.asyncio
async def test_message_id_is_released_when_agent_and_fallback_delivery_fail(
    configured_handler: GoviMithuraWhatsAppHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_count = 0

    class FakeAgentService:
        agent: object | None = None

        def select(self, session_id: str, name: str | None = None) -> None:
            del session_id, name
            self.agent = object()

        async def run_multi(self, requests: list[Any]) -> AgentReplyText:
            nonlocal run_count
            del requests
            run_count += 1
            if run_count == 1:
                raise RuntimeError("agent failed")
            return AgentReplyText(response="Recovered response")

    monkeypatch.setattr(whatsapp_runtime, "AgentService", FakeAgentService)
    configured_handler._send_message = AsyncMock(  # type: ignore[method-assign]
        side_effect=[RuntimeError("fallback delivery failed"), None]
    )
    message: dict[str, object] = {
        "id": "wamid.retry-after-agent-failure",
        "from": "94770000001",
        "type": "text",
        "text": {"body": "Hello"},
    }

    with pytest.raises(RuntimeError, match="fallback delivery failed"):
        await configured_handler._handle_message(message, {})
    await configured_handler._handle_message(message, {})

    assert run_count == 2
    assert configured_handler._send_message.await_count == 2
