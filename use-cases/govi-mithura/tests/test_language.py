"""Tests for controlled Sinhala language guidance."""

from __future__ import annotations

import pytest

from language import (
    build_language_guidance,
    clean_sinhala_weather_reply,
    detect_message_language,
    load_sinhala_glossary,
)


def test_sinhala_script_is_detected_deterministically() -> None:
    assert detect_message_language("හෙට වැස්ස වසියිද?") == "si"
    assert detect_message_language("Will it rain tomorrow?") == "en"


@pytest.mark.parametrize(
    "message",
    [
        "Reply in Sinhala.",
        "Please respond in Sinhala",
        "Speak to me in Sinhala, please.",
    ],
)
def test_explicit_english_request_for_sinhala_is_detected(message: str) -> None:
    assert detect_message_language(message) == "si"


def test_sinhala_glossary_is_validated_and_flags_unreviewed_terms() -> None:
    glossary = load_sinhala_glossary()

    assert glossary.schema_version == 1
    assert glossary.review_status == "native_speaker_demo_flow_approved"
    assert len(glossary.entries) == len({entry.key for entry in glossary.entries})
    # sinhala_terms() keys by english, so a duplicate there would silently drop an entry.
    assert len(glossary.entries) == len({entry.english for entry in glossary.entries})
    assert any(entry.status == "native_speaker_approved" for entry in glossary.entries)
    assert any(entry.status == "pending_review" for entry in glossary.entries)
    assert all(source.url.startswith("https://") for source in glossary.sources)


def test_sinhala_guidance_preserves_technical_english_terms() -> None:
    guidance = build_language_guidance("මිරිස් කොළ හැකිළිලා")

    assert guidance["response_language"] == "si"
    assert guidance["terminology"]["leaf curl"].endswith("(leaf curl)")  # type: ignore[index]
    assert "Do not invent translations" in guidance["style"]  # type: ignore[operator]
    assert "ගොවි මිතුරා" in guidance["style"]  # type: ignore[operator]
    assert "never shorten it" in guidance["style"]  # type: ignore[operator]


@pytest.mark.parametrize("preferred", ["si"])
def test_stored_sinhala_preference_wins_for_english_message(preferred: str) -> None:
    assert build_language_guidance("What is tomorrow's forecast?", preferred)["response_language"] == "si"


def test_sinhala_weather_cleanup_removes_glosses_but_preserves_source_links() -> None:
    reply = """වැල්ලවාය සඳහා කාලගුණ අනාවැකිය (weather forecast):
*උපරිම උෂ්ණත්වය (maximum temperature):* 34.7°C
මොණරාගල වෙනුවට භූගෝලීය স্থානගත කිරීම් (coordinates) පදනම් කරගත් අනාවැකියකි (Open-Meteo coordinates for the named locality).
*මූලාශ්‍රය (source):* [Open-Meteo](https://open-meteo.com/en/docs)
"""

    cleaned = clean_sinhala_weather_reply(reply)

    assert "weather forecast" not in cleaned
    assert "maximum temperature" not in cleaned
    assert "coordinates" not in cleaned
    assert "স্থ" not in cleaned
    assert "භූ-ඛණ්ඩාංක" in cleaned
    assert "මොණරාගල" not in cleaned
    assert "මොනරාගල" in cleaned
    assert "[Open-Meteo](https://open-meteo.com/en/docs)" in cleaned
