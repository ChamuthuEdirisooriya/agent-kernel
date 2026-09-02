"""Composition tests for the public Agent Kernel surface."""

import json
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
from agentkernel.core import AgentRequestText, AgentService
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, SecretStr

import agent as agent_module
from agent import FIELD_PROMPT, _route_request, build_model, register_module
from farmer_profile import FarmerProfile, load_profile, save_profile, update_profile
from settings import LLMProvider, LLMSettings


class DeterministicProfileModel(BaseChatModel):
    """Offline tool-calling model used to exercise the public AgentService graph."""

    bound_tool_names: tuple[str, ...] = ()
    events: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "deterministic-profile-test"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> BaseChatModel:
        del kwargs
        names = tuple(
            str(getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else "")) for tool in tools
        )
        return self.model_copy(update={"bound_tool_names": names})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        last_human_index = max(index for index, message in enumerate(messages) if isinstance(message, HumanMessage))
        current_messages = messages[last_human_index:]
        prompt = str(messages[last_human_index].content)
        current_tool_messages = [message for message in current_messages if isinstance(message, ToolMessage)]

        def tool_called(name: str) -> bool:
            return any(message.name == name for message in current_tool_messages)

        def tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
            self.events.append(name)
            return AIMessage(
                content="",
                tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
            )

        def latest_specialist_answer() -> str:
            return next(
                (
                    str(item.content)
                    for item in reversed(current_messages)
                    if isinstance(item, AIMessage)
                    and item.content
                    and str(item.content) != "Transferring back to supervisor"
                ),
                "",
            )

        if "update_farmer_profile" in self.bound_tool_names and "My name is Nimal" in prompt:
            if not tool_called("update_farmer_profile"):
                place_args = {"location": "Wellawaya"} if "Wellawaya" in prompt else {"district": "Monaragala"}
                message = tool_call(
                    "update_farmer_profile",
                    {"name": "Nimal", "crop": "chili", **place_args},
                    "profile-update-1",
                )
            else:
                place = "Wellawaya" if "Wellawaya" in prompt else "Monaragala"
                message = AIMessage(content=f"I remembered your chili farm in {place}.")
        elif "update_farmer_profile" in self.bound_tool_names and "What do you remember" in prompt:
            has_district = '"district": "Monaragala"' in prompt
            has_location = '"location": "Wellawaya"' in prompt
            has_profile = (has_district or has_location) and '"crops": ["chili"]' in prompt
            place = "Wellawaya" if has_location else "Monaragala"
            message = AIMessage(
                content=f"You grow chili in {place}." if has_profile else "I do not have a saved farm profile."
            )
        elif "transfer_to_field_information" in self.bound_tool_names and "weather" in prompt.casefold():
            if not tool_called("transfer_to_field_information"):
                message = tool_call("transfer_to_field_information", {}, "handoff-weather-1")
            else:
                message = AIMessage(content=latest_specialist_answer())
        elif "transfer_to_field_information" in self.bound_tool_names and "market" in prompt.casefold():
            if not tool_called("transfer_to_field_information"):
                message = tool_call("transfer_to_field_information", {}, "handoff-market-1")
            else:
                message = AIMessage(content=latest_specialist_answer())
        elif "transfer_to_crop_knowledge" in self.bound_tool_names and "leaves" in prompt.casefold():
            if not tool_called("transfer_to_crop_knowledge"):
                message = tool_call("transfer_to_crop_knowledge", {}, "handoff-crop-1")
            else:
                message = AIMessage(content=latest_specialist_answer())
        elif "get_weather_forecast" in self.bound_tool_names and "weather" in prompt.casefold():
            if not tool_called("get_weather_forecast"):
                message = tool_call("get_weather_forecast", {"location": "Kandy"}, "weather-tool-1")
            else:
                tool_result = next(
                    str(item.content) for item in reversed(current_tool_messages) if item.name == "get_weather_forecast"
                )
                if '"status": "ok"' in tool_result:
                    message = AIMessage(
                        content="Kandy has a 65% rain probability on 2026-07-11. Source: Open-Meteo. As of: 2026-08-30."
                    )
                else:
                    message = AIMessage(
                        content="Live weather is temporarily unavailable. Source: Open-Meteo. As of: 2026-08-30."
                    )
        elif "get_market_prices" in self.bound_tool_names and "market" in prompt.casefold():
            if not tool_called("get_market_prices"):
                message = tool_call(
                    "get_market_prices",
                    {"commodity": "green chili", "market": "Dambulla"},
                    "market-tool-1",
                )
            else:
                message = AIMessage(content="The market tool returned its dated result.")
        elif "crop_kb_search" in self.bound_tool_names and "leaves" in prompt.casefold():
            if not tool_called("crop_kb_search"):
                message = tool_call(
                    "crop_kb_search",
                    {"crop": "chili", "query": "leaf curl", "top_k": 1},
                    "crop-tool-1",
                )
            else:
                if "insects under" in prompt.casefold():
                    message = AIMessage(
                        content=(
                            "Leaf curl is one possible cause, but this is not a definite diagnosis. "
                            "Source: Sri Lanka Department of Agriculture."
                        )
                    )
                else:
                    message = AIMessage(content="Are there insects under the curled leaves?")
        else:
            raise AssertionError(f"Unexpected model invocation with tools {self.bound_tool_names}: {prompt}")

        return ChatResult(generations=[ChatGeneration(message=message)])


def _module() -> object:
    return register_module(
        LLMSettings(
            model="gemini-3.5-flash",
            api_key="test-key",
        )
    )


def test_only_supervisor_is_registered_as_public_agent() -> None:
    module = _module()
    try:
        assert [agent.name for agent in module.agents] == ["govi_mithura"]  # type: ignore[attr-defined]
        supervisor = module.get_agent("govi_mithura")  # type: ignore[attr-defined]
        assert supervisor is not None
        assert [hook.name() for hook in supervisor.pre_hooks] == [
            "domain_safety_input",
            "deterministic_market",
            "farmer_context",
        ]
        assert [hook.name() for hook in supervisor.post_hooks] == ["domain_safety_output"]
    finally:
        module.unload()  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("My chili leaves are curling", "crop_knowledge"),
        ("What is the weather tomorrow?", "field_information"),
        ("Remember that I grow chili", "llm_supervisor"),
        ("Hello", "llm_supervisor"),
    ],
)
def test_clear_intents_use_deterministic_specialist_routes(message: str, expected: str) -> None:
    assert _route_request({"messages": [HumanMessage(content=message)]}) == expected


def test_field_prompt_keeps_internal_tool_codes_out_of_farmer_responses() -> None:
    assert "never expose raw JSON keys, enum codes, snake_case values" in FIELD_PROMPT
    assert "Do not add English translations in parentheses" in FIELD_PROMPT


def test_vertex_model_uses_native_google_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_google_model(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_module, "ChatGoogleGenerativeAI", fake_google_model)

    model = build_model(
        LLMSettings(
            model="gemini-3.6-flash",
            provider="google_vertex",
            google_cloud_project="test-project",
            google_cloud_location="global",
        )
    )

    assert model is not None
    assert captured == {
        "model": "gemini-3.6-flash",
        "project": "test-project",
        "location": "global",
        "vertexai": True,
        "thinking_level": None,
        "timeout": 30.0,
        "max_retries": 2,
    }


def test_ai_studio_model_uses_native_google_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_google_model(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_module, "ChatGoogleGenerativeAI", fake_google_model)

    model = build_model(
        LLMSettings(
            model="gemini-3.5-flash",
            provider="google_ai_studio",
            api_key="test-key",
        )
    )

    assert model is not None
    assert captured["model"] == "gemini-3.5-flash"
    assert captured["vertexai"] is False
    assert captured["google_api_key"] == SecretStr("test-key")
    assert captured["thinking_level"] is None
    assert captured["timeout"] == 30.0
    assert captured["max_retries"] == 2


def test_openai_compatible_model_uses_generic_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_openai_model(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_module, "ChatOpenAI", fake_openai_model)

    model = build_model(
        LLMSettings(
            model="provider/model",
            provider="openai_compatible",
            api_key="test-key",
            base_url="https://example.invalid/v1",
        )
    )

    assert model is not None
    assert captured == {
        "model": "provider/model",
        "api_key": SecretStr("test-key"),
        "base_url": "https://example.invalid/v1",
        "timeout": 30.0,
        "max_retries": 1,
    }


@pytest.mark.parametrize(
    ("provider", "expected_client_retries"),
    [
        ("google_ai_studio", 1),
        ("google_vertex", 1),
        ("openai_compatible", 0),
    ],
)
def test_zero_retries_disables_provider_retries(
    monkeypatch: pytest.MonkeyPatch,
    provider: LLMProvider,
    expected_client_retries: int,
) -> None:
    captured: dict[str, object] = {}

    def fake_model(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agent_module, "ChatGoogleGenerativeAI", fake_model)
    monkeypatch.setattr(agent_module, "ChatOpenAI", fake_model)
    build_model(
        LLMSettings(
            model="test-model",
            provider=provider,
            api_key="test-key",
            base_url="https://example.invalid/v1",
            google_cloud_project="test-project",
            max_retries=0,
        )
    )

    assert captured["max_retries"] == expected_client_retries


def test_real_agent_service_sessions_recall_and_isolate_profile_state() -> None:
    module = _module()
    first_id = f"test-first-{uuid4()}"
    second_id = f"test-second-{uuid4()}"
    try:
        first = AgentService()
        first.select(session_id=first_id, name="govi_mithura")
        assert first.session is not None
        save_profile(
            first.session.get_non_volatile_cache(),
            update_profile(FarmerProfile(), district="Kandy", crop="paddy"),
        )

        returning = AgentService()
        returning.select(session_id=first_id, name="govi_mithura")
        other = AgentService()
        other.select(session_id=second_id, name="govi_mithura")

        assert returning.session is not None
        assert other.session is not None
        assert load_profile(returning.session.get_non_volatile_cache()).district == "Kandy"
        assert load_profile(other.session.get_non_volatile_cache()).district is None
    finally:
        module.unload()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_public_agent_service_onboards_and_recalls_profile_with_mocked_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = DeterministicProfileModel()
    monkeypatch.setattr(agent_module, "build_model", lambda settings: model)
    module = register_module(LLMSettings(model="offline-test", api_key="test-key"))
    service = AgentService()
    service.select(session_id=f"profile-journey-{uuid4()}", name="govi_mithura")
    try:
        saved = await service.run_multi([AgentRequestText(prompt="My name is Nimal. I grow chili in Monaragala.")])
        recalled = await service.run_multi([AgentRequestText(prompt="What do you remember about my farm?")])

        assert "Monaragala" in saved.response
        assert "chili" in recalled.response
        assert "Monaragala" in recalled.response
        assert model.events == ["update_farmer_profile"]
    finally:
        module.unload()


@pytest.mark.asyncio
async def test_public_agent_service_stores_a_farmer_locality_without_inferred_district(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = DeterministicProfileModel()
    monkeypatch.setattr(agent_module, "build_model", lambda settings: model)
    module = register_module(LLMSettings(model="offline-test", api_key="test-key"))
    service = AgentService()
    service.select(session_id=f"locality-profile-{uuid4()}", name="govi_mithura")
    try:
        saved = await service.run_multi([AgentRequestText(prompt="My name is Nimal. I grow chili in Wellawaya.")])
        recalled = await service.run_multi([AgentRequestText(prompt="What do you remember about my farm?")])

        assert service.session is not None
        profile = load_profile(service.session.get_non_volatile_cache())
        assert profile.location == "Wellawaya"
        assert profile.district is None
        assert "Wellawaya" in saved.response
        assert "Wellawaya" in recalled.response
    finally:
        module.unload()


@pytest.mark.asyncio
async def test_public_agent_service_blocks_exposure_before_mocked_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = DeterministicProfileModel()
    monkeypatch.setattr(agent_module, "build_model", lambda settings: model)
    module = register_module(LLMSettings(model="offline-test", api_key="test-key"))
    service = AgentService()
    service.select(session_id=f"safety-journey-{uuid4()}", name="govi_mithura")
    try:
        result = await service.run_multi([AgentRequestText(prompt="My child drank Confidor and feels dizzy")])

        assert "emergency" in result.response.casefold()
        assert "Confidor" not in result.response
        assert model.events == []
    finally:
        module.unload()


@pytest.mark.asyncio
async def test_public_agent_service_routes_weather_through_mocked_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_weather_forecast(location: str) -> str:
        assert location == "Kandy"
        return json.dumps(
            {
                "status": "ok",
                "forecast": [{"date": "2026-07-11", "precipitation_probability_percent": 65}],
                "source": "Open-Meteo",
                "as_of": "2026-08-30T12:00:00+05:30",
            }
        )

    model = DeterministicProfileModel()
    monkeypatch.setattr(agent_module, "build_model", lambda settings: model)
    monkeypatch.setattr(agent_module, "get_weather_forecast", get_weather_forecast)
    module = register_module(LLMSettings(model="offline-test", api_key="test-key"))
    service = AgentService()
    service.select(session_id=f"weather-journey-{uuid4()}", name="govi_mithura")
    try:
        result = await service.run_multi([AgentRequestText(prompt="What is the weather tomorrow in Kandy?")])

        assert "transfer_to_field_information" not in model.events
        assert "get_weather_forecast" in model.events
        assert "65%" in result.response
        assert "Source" in result.response
        assert "2026-08-30" in result.response
    finally:
        module.unload()


@pytest.mark.asyncio
async def test_public_agent_service_answers_market_deterministically_without_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = DeterministicProfileModel()
    monkeypatch.setenv("MARKET_PRICE_STALE_AFTER_DAYS", "0")
    monkeypatch.setattr(agent_module, "build_model", lambda settings: model)
    module = register_module(LLMSettings(model="offline-test", api_key="test-key"))
    service = AgentService()
    service.select(session_id=f"market-journey-{uuid4()}", name="govi_mithura")
    try:
        result = await service.run_multi([AgentRequestText(prompt="What is the green chili market price in Dambulla?")])

        assert model.events == []
        assert "450–500" in result.response
        assert "data date: 2026-08-29" in result.response
        assert "Source" in result.response
        assert "Stale-data warning" in result.response
    finally:
        module.unload()


@pytest.mark.asyncio
async def test_public_agent_service_routes_crop_problem_through_grounded_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = DeterministicProfileModel()
    monkeypatch.setattr(agent_module, "build_model", lambda settings: model)
    module = register_module(LLMSettings(model="offline-test", api_key="test-key"))
    service = AgentService()
    service.select(session_id=f"crop-journey-{uuid4()}", name="govi_mithura")
    try:
        clarification = await service.run_multi([AgentRequestText(prompt="My chili leaves are curling")])
        result = await service.run_multi([AgentRequestText(prompt="There are insects under the leaves")])

        assert "insects under" in clarification.response
        assert model.events.count("transfer_to_crop_knowledge") == 0
        assert model.events.count("crop_kb_search") == 2
        assert "not a definite diagnosis" in result.response
        assert "Department of Agriculture" in result.response
    finally:
        module.unload()


@pytest.mark.asyncio
async def test_public_agent_service_weather_outage_does_not_fabricate_forecast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def get_weather_forecast(location: str) -> str:
        assert location == "Kandy"
        return json.dumps(
            {
                "status": "upstream_error",
                "message": "Live weather is temporarily unavailable.",
                "source": "Open-Meteo",
                "as_of": "2026-08-30T12:00:00+05:30",
            }
        )

    model = DeterministicProfileModel()
    monkeypatch.setattr(agent_module, "build_model", lambda settings: model)
    monkeypatch.setattr(agent_module, "get_weather_forecast", get_weather_forecast)
    module = register_module(LLMSettings(model="offline-test", api_key="test-key"))
    service = AgentService()
    service.select(session_id=f"outage-journey-{uuid4()}", name="govi_mithura")
    try:
        result = await service.run_multi([AgentRequestText(prompt="What is the weather tomorrow in Kandy?")])

        assert "get_weather_forecast" in model.events
        assert "temporarily unavailable" in result.response
        assert "65%" not in result.response
    finally:
        module.unload()
