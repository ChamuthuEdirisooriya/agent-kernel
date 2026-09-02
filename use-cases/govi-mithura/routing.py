"""Deterministic routing hints for clear farmer intents."""

from __future__ import annotations

from enum import StrEnum

from farmer_profile import normalized


class Intent(StrEnum):
    """Primary intent labels used by the supervisor."""

    CROP_PROBLEM = "crop_problem"
    WEATHER_ADVICE = "weather_advice"
    MARKET_PRICE = "market_price"
    PROFILE_UPDATE = "profile_update"
    SMALLTALK_OR_OTHER = "smalltalk_or_other"


WEATHER_TERMS = (
    "weather",
    "forecast",
    "rain",
    "wind",
    "tomorrow",
    "කාලගුණය",
    "වැස්ස",
    "වැසි",
    "වසියිද",
    "හෙට",
    "කාලගුණ අනාවැකිය",
    "වර්ෂාපතනය",
    "සුළං",
)
MARKET_REQUEST_TERMS = (
    "price",
    "market",
    "wholesale",
    "මිල",
    "වෙළඳපොළ",
    "වෙළඳපළ",
    "තොග මිල",
)
CROP_TERMS = (
    "leaf",
    "leaves",
    "curl",
    "yellow",
    "pest",
    "disease",
    "chili",
    "chilli",
    "paddy",
    "rice",
    "කොළ",
    "පත්ර",
    "පත්‍ර",
    "හැකිළ",
    "මැලව",
    "පැල්ලම්",
    "කීඩෑ",
    "රෝග",
    "මිරිස්",
    "වී",
)
PROFILE_TERMS = (
    "i grow",
    "i planted",
    "my farm",
    "my field",
    "my district",
    "remember",
    "මම වගා කරන",
    "මම සිටවුවා",
    "මගේ වගාව",
    "මම වගා කළා",
    "මම හිටෙව්වා",
    "වගා කළා",
    "හිටෙව්වා",
    "මගේ දිස්ත්‍රික්කය",
    "මතක තියාගන්න",
)


def classify_intent(message: str) -> Intent:
    """Classify unambiguous keyword-based intents; the LLM resolves ambiguity later."""
    text = normalized(message)
    if any(term in text for term in MARKET_REQUEST_TERMS):
        return Intent.MARKET_PRICE
    if any(term in text for term in WEATHER_TERMS):
        return Intent.WEATHER_ADVICE
    if any(term in text for term in PROFILE_TERMS):
        return Intent.PROFILE_UPDATE
    if any(term in text for term in CROP_TERMS):
        return Intent.CROP_PROBLEM
    return Intent.SMALLTALK_OR_OTHER
