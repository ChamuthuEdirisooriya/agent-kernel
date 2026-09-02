"""Agent Kernel hooks for deterministic commands and trusted profile context."""

from __future__ import annotations

from agentkernel.core import (
    Agent,
    AgentReply,
    AgentReplyText,
    AgentRequest,
    AgentRequestText,
    PreHook,
    Runtime,
    Session,
)

from farmer_profile import language_preference, load_profile, normalized, record_topic
from field_tools import grounded_market_price_reply, resolve_market_price_request
from language import build_language_guidance, reply_in_sinhala, session_reply_in_sinhala
from routing import Intent, classify_intent
from trusted_context import enrich_message

RESET_REQUEST = "#reset"
RESET_CONFIRMATION = "#reset confirm"


def _text_request(requests: list[AgentRequest]) -> AgentRequestText | None:
    return next((request for request in requests if isinstance(request, AgentRequestText)), None)


def _halting_reply(session: Session, response: str) -> AgentReplyText:
    """Persist this session, then return a reply that halts the run.

    Runtime.run returns as soon as a pre-hook replies, before its own sessions().store() call, so
    every durable write a halting hook made is dropped unless the hook stores it first.
    """
    Runtime.current().sessions().store(session)
    return AgentReplyText(response=response)


def _erase_durable_state(session: Session, agent: Agent) -> None:
    """Erase every durable key this app writes, including the framework's own.

    Session.clear() drops the keys in memory, but SessionStore.store() upserts per key and never
    deletes, so each key must be overwritten with an empty value to survive a serializing store.
    An empty framework context is written rather than cleared for the same reason.
    """
    session.clear()
    session.set(agent.runner.name, None)
    session.set_framework_context({})


def _reset_warning(sinhala: bool) -> str:
    """Return the reset confirmation prompt in the farmer's language."""
    if sinhala:
        return "මෙය ඔබගේ මතකගත ගොවි පැතිකඩ සහ සංවාද තත්ත්වය මකා දමයි. ඉදිරියට යාමට #reset confirm ලෙස ලියන්න."
    return "This will erase your remembered profile and conversation state. Type #reset confirm to continue."


def _reset_confirmation(sinhala: bool) -> str:
    """Return the completed-reset acknowledgement in the farmer's language."""
    if sinhala:
        return "ඔබගේ ගොවි මිතුරා පැතිකඩ සහ සංවාද තත්ත්වය මකා දමා ඇත."
    return "Your Govi Mithura profile and conversation state have been cleared."


class DeterministicMarketPreHook(PreHook):
    """Answer clear market-price requests from the verified snapshot without an LLM call."""

    async def on_run(
        self,
        session: Session,
        agent: Agent,
        requests: list[AgentRequest],
    ) -> list[AgentRequest] | AgentReply:
        del agent
        request = _text_request(requests)
        if request is None or classify_intent(request.prompt) is not Intent.MARKET_PRICE:
            return requests
        cache = session.get_non_volatile_cache()
        resolved = resolve_market_price_request(request.prompt)
        if resolved is None:
            return AgentReplyText(
                response=grounded_market_price_reply(
                    request.prompt,
                    sinhala=session_reply_in_sinhala(cache, request.prompt),
                )
            )
        profile = record_topic(cache, Intent.MARKET_PRICE.value)
        sinhala = reply_in_sinhala(profile, request.prompt)
        return _halting_reply(session, grounded_market_price_reply(request.prompt, sinhala=sinhala))

    def name(self) -> str:
        return "deterministic_market"


class FarmerContextPreHook(PreHook):
    """Handle reset commands and prepend trusted profile/routing context."""

    async def on_run(
        self,
        session: Session,
        agent: Agent,
        requests: list[AgentRequest],
    ) -> list[AgentRequest] | AgentReply:
        text_request = _text_request(requests)
        if text_request is None:
            return requests

        cache = session.get_non_volatile_cache()
        command = normalized(text_request.prompt)
        if command in {RESET_REQUEST, RESET_CONFIRMATION}:
            sinhala = session_reply_in_sinhala(cache, text_request.prompt)
            if command == RESET_REQUEST:
                return AgentReplyText(response=_reset_warning(sinhala))
            _erase_durable_state(session, agent)
            return _halting_reply(session, _reset_confirmation(sinhala))

        intent = classify_intent(text_request.prompt)
        profile = record_topic(cache, intent.value) if intent is not Intent.SMALLTALK_OR_OTHER else load_profile(cache)
        stored_profile = profile.model_dump(mode="json")
        context = {
            "deterministic_intent_hint": intent.value,
            "untrusted_farmer_profile": stored_profile if profile.has_context() else None,
            "language_guidance": build_language_guidance(text_request.prompt, language_preference(profile)),
        }
        enriched = AgentRequestText(prompt=enrich_message(context, text_request.prompt))
        return [enriched if request is text_request else request for request in requests]

    def name(self) -> str:
        return "farmer_context"
