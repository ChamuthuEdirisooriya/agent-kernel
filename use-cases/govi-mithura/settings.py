"""Environment-backed settings for Govi Mithura."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Literal, cast


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


LLMProvider = Literal["google_ai_studio", "google_vertex", "openai_compatible"]
ThinkingLevel = Literal["minimal", "low", "medium", "high"]


def _bounded_float(
    name: str,
    raw: str | None,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    """Read a finite numeric override and reject ambiguous production configuration."""
    if not raw or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number between {minimum:g} and {maximum:g}.") from exc
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} must be a number between {minimum:g} and {maximum:g}.")
    return value


def _bounded_non_negative_int(
    name: str,
    raw: str | None,
    *,
    default: int,
    maximum: int,
) -> int:
    """Read a bounded retry count and fail fast when a deployment value is invalid."""
    if not raw or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a whole number between 0 and {maximum}.") from exc
    if not 0 <= value <= maximum:
        raise ConfigurationError(f"{name} must be a whole number between 0 and {maximum}.")
    return value


@dataclass(frozen=True)
class LLMSettings:
    """Provider-explicit model settings used by LangGraph."""

    model: str
    provider: LLMProvider = "openai_compatible"
    api_key: str | None = None
    base_url: str | None = None
    google_cloud_project: str | None = None
    google_cloud_location: str = "global"
    thinking_level: ThinkingLevel | None = None
    request_timeout: float = 30.0
    max_retries: int = 1

    @classmethod
    def from_environment(cls) -> "LLMSettings":
        """Load settings without coupling application logic to one model provider."""
        model = os.getenv("LLM_MODEL", "").strip()
        raw_provider = os.getenv("LLM_PROVIDER", "openai_compatible").strip().casefold()
        if raw_provider not in {"google_ai_studio", "google_vertex", "openai_compatible"}:
            raise ConfigurationError(
                "LLM_PROVIDER must be 'google_ai_studio', 'google_vertex', or " "'openai_compatible'."
            )
        provider = cast(LLMProvider, raw_provider)

        if provider == "google_ai_studio":
            api_key = (
                os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("LLM_API_KEY") or ""
            ).strip()
        else:
            api_key = (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        base_url = (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip() or None
        google_cloud_project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip() or None
        google_cloud_location = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
        raw_thinking_level = os.getenv("LLM_THINKING_LEVEL", "").strip().casefold()
        if raw_thinking_level not in {"", "minimal", "low", "medium", "high"}:
            raise ConfigurationError("LLM_THINKING_LEVEL must be 'minimal', 'low', 'medium', or 'high'.")
        thinking_level = cast(ThinkingLevel, raw_thinking_level) if raw_thinking_level else None

        request_timeout = _bounded_float(
            "LLM_REQUEST_TIMEOUT_SECONDS",
            os.getenv("LLM_REQUEST_TIMEOUT_SECONDS"),
            default=30.0,
            minimum=5.0,
            maximum=300.0,
        )
        max_retries = _bounded_non_negative_int(
            "LLM_MAX_RETRIES",
            os.getenv("LLM_MAX_RETRIES"),
            default=1,
            maximum=5,
        )

        missing = []
        if not model:
            missing.append("LLM_MODEL")
        if provider == "google_ai_studio" and not api_key:
            missing.append("GEMINI_API_KEY (or GOOGLE_API_KEY or LLM_API_KEY)")
        if provider == "openai_compatible" and not api_key:
            missing.append("LLM_API_KEY (or OPENAI_API_KEY)")
        if provider == "google_vertex" and not google_cloud_project:
            missing.append("GOOGLE_CLOUD_PROJECT")
        if missing:
            raise ConfigurationError("Missing required LLM configuration: " + ", ".join(missing))

        return cls(
            model=model,
            provider=provider,
            api_key=api_key or None,
            base_url=base_url,
            google_cloud_project=google_cloud_project,
            google_cloud_location=google_cloud_location,
            thinking_level=thinking_level,
            request_timeout=request_timeout,
            max_retries=max_retries,
        )
