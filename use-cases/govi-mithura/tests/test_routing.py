"""Tests for deterministic routing hints."""

import pytest

from routing import Intent, classify_intent


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("My chili leaves are curling", Intent.CROP_PROBLEM),
        ("මගේ මිරිස් කොළ වක්ර වෙලා", Intent.CROP_PROBLEM),
        ("Will it rain tomorrow in Kandy?", Intent.WEATHER_ADVICE),
        ("කුරුණෑගලට හෙට වැසි වසියිද?", Intent.WEATHER_ADVICE),
        ("What is the Dambulla wholesale price?", Intent.MARKET_PRICE),
        ("දඹුල්ල වෙළඳපළ මිල කීයද?", Intent.MARKET_PRICE),
        ("I planted paddy yesterday", Intent.PROFILE_UPDATE),
        ("මම මොනරාගල මිරිස් වගා කළා", Intent.PROFILE_UPDATE),
        ("මිරිස් කොළ වල පැල්ලම් තියෙනවා", Intent.CROP_PROBLEM),
        ("හෙට වර්ෂාපතන සම්භාවිතාව කීයද?", Intent.WEATHER_ADVICE),
        ("මීගොඩ අමු මිරිස් තොග මිල කීයද?", Intent.MARKET_PRICE),
        ("How is the weather in Dambulla tomorrow?", Intent.WEATHER_ADVICE),
        ("දඹුල්ලේ හෙට කාලගුණය කොහොමද?", Intent.WEATHER_ADVICE),
        ("Remember my district is Dambulla", Intent.PROFILE_UPDATE),
        ("Dambulla", Intent.SMALLTALK_OR_OTHER),
        ("Hello", Intent.SMALLTALK_OR_OTHER),
    ],
)
def test_classify_intent(message: str, expected: Intent) -> None:
    assert classify_intent(message) is expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What is the chili price tomorrow in Dambulla?", Intent.MARKET_PRICE),
        ("දඹුල්ලේ මිරිස් මිල හෙට කීයද?", Intent.MARKET_PRICE),
        ("What is the chili price?", Intent.MARKET_PRICE),
        ("Will rain damage my chili leaves?", Intent.WEATHER_ADVICE),
        ("I planted paddy yesterday", Intent.PROFILE_UPDATE),
    ],
)
def test_overlapping_intent_precedence_is_explicit(message: str, expected: Intent) -> None:
    assert classify_intent(message) is expected
