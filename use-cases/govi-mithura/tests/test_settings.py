"""Tests for provider-neutral LLM configuration."""

from pathlib import Path

import pytest

from settings import ConfigurationError, LLMSettings

ENV_EXAMPLE_PATH = Path(__file__).parents[1] / ".env.example"


def test_env_example_matches_portable_runtime_defaults() -> None:
    active_values = {
        key: value
        for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
        for key, value in [line.split("=", maxsplit=1)]
    }

    assert active_values["LLM_PROVIDER"] == "openai_compatible"
    assert active_values["LLM_REQUEST_TIMEOUT_SECONDS"] == "30"
    assert active_values["LLM_MAX_RETRIES"] == "1"
    assert active_values["LLM_API_KEY"] == ""
    assert active_values["AK_WHATSAPP__VERIFY_TOKEN"] == ""
    assert active_values["AK_WHATSAPP__ACCESS_TOKEN"] == ""
    assert active_values["AK_WHATSAPP__APP_SECRET"] == ""
    assert active_values["AK_WHATSAPP__PHONE_NUMBER_ID"] == ""


def test_settings_require_model_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    with pytest.raises(ConfigurationError, match="LLM_MODEL"):
        LLMSettings.from_environment()


def test_settings_accept_openai_compatible_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "provider/model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")

    settings = LLMSettings.from_environment()

    assert settings.model == "provider/model"
    assert settings.api_key == "test-key"
    assert settings.base_url == "https://example.invalid/v1"
    assert settings.provider == "openai_compatible"


def test_settings_default_to_openai_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_MODEL", "provider/model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    settings = LLMSettings.from_environment()

    assert settings.provider == "openai_compatible"


def test_settings_accept_google_ai_studio_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google_ai_studio")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("LLM_THINKING_LEVEL", "low")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    settings = LLMSettings.from_environment()

    assert settings.provider == "google_ai_studio"
    assert settings.model == "gemini-3.5-flash"
    assert settings.api_key == "gemini-test-key"
    assert settings.base_url is None
    assert settings.thinking_level == "low"


def test_settings_require_key_for_google_ai_studio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google_ai_studio")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY"):
        LLMSettings.from_environment()


def test_settings_accept_google_vertex_adc_without_static_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google_vertex")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "global")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = LLMSettings.from_environment()

    assert settings.provider == "google_vertex"
    assert settings.api_key is None
    assert settings.google_cloud_project == "test-project"
    assert settings.google_cloud_location == "global"


def test_settings_require_project_for_google_vertex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google_vertex")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.6-flash")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    with pytest.raises(ConfigurationError, match="GOOGLE_CLOUD_PROJECT"):
        LLMSettings.from_environment()


def test_settings_reject_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "magic")

    with pytest.raises(ConfigurationError, match="google_ai_studio.*google_vertex.*openai_compatible"):
        LLMSettings.from_environment()


def test_settings_reject_unknown_thinking_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_MODEL", "provider/model")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_THINKING_LEVEL", "turbo")

    with pytest.raises(ConfigurationError, match="LLM_THINKING_LEVEL"):
        LLMSettings.from_environment()


def test_request_timeout_and_retries_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google_ai_studio")
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")

    settings = LLMSettings.from_environment()

    assert settings.request_timeout == 30.0
    assert settings.max_retries == 1


@pytest.mark.parametrize(
    ("raw_timeout", "raw_retries", "expected_timeout", "expected_retries"),
    [
        ("45", "4", 45.0, 4),
        ("5", "0", 5.0, 0),
        ("300", "5", 300.0, 5),
        ("", "  ", 30.0, 1),
    ],
)
def test_request_timeout_and_retries_read_overrides(
    monkeypatch: pytest.MonkeyPatch,
    raw_timeout: str,
    raw_retries: str,
    expected_timeout: float,
    expected_retries: int,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google_ai_studio")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", raw_timeout)
    monkeypatch.setenv("LLM_MAX_RETRIES", raw_retries)

    settings = LLMSettings.from_environment()

    assert settings.request_timeout == expected_timeout
    assert settings.max_retries == expected_retries


@pytest.mark.parametrize(
    ("raw_timeout", "raw_retries", "expected_setting"),
    [
        ("fast", "1", "LLM_REQUEST_TIMEOUT_SECONDS"),
        ("nan", "1", "LLM_REQUEST_TIMEOUT_SECONDS"),
        ("inf", "1", "LLM_REQUEST_TIMEOUT_SECONDS"),
        ("4.9", "1", "LLM_REQUEST_TIMEOUT_SECONDS"),
        ("301", "1", "LLM_REQUEST_TIMEOUT_SECONDS"),
        ("30", "many", "LLM_MAX_RETRIES"),
        ("30", "-1", "LLM_MAX_RETRIES"),
        ("30", "6", "LLM_MAX_RETRIES"),
    ],
)
def test_request_timeout_and_retries_reject_invalid_overrides(
    monkeypatch: pytest.MonkeyPatch,
    raw_timeout: str,
    raw_retries: str,
    expected_setting: str,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google_ai_studio")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", raw_timeout)
    monkeypatch.setenv("LLM_MAX_RETRIES", raw_retries)

    with pytest.raises(ConfigurationError, match=expected_setting):
        LLMSettings.from_environment()
