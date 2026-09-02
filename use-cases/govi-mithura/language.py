"""Controlled language guidance for English and Sinhala farmer conversations."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict

from farmer_profile import Cache, FarmerProfile, language_preference, load_profile

GLOSSARY_PATH = Path(__file__).parent / "data" / "sinhala_glossary.json"
SINHALA_PATTERN = re.compile(r"[\u0D80-\u0DFF]")
BENGALI_PATTERN = re.compile(r"[\u0980-\u09FF]+")
PARENTHETICAL_ENGLISH_GLOSS_PATTERN = re.compile(
    r"\s*\((?!https?://)(?=[^()\n]*[A-Za-z])[^()\n]*\)",
    re.IGNORECASE,
)
EXPLICIT_SINHALA_REQUEST_PATTERN = re.compile(
    r"\b(?:reply|respond|answer|speak|talk)(?:\s+to\s+me)?\s+in\s+sinhala\b",
    re.IGNORECASE,
)
SINHALA_PRODUCT_NAME = "ගොවි මිතුරා"


class GlossaryEntry(BaseModel):
    """One controlled English-to-Sinhala term."""

    key: str
    english: str
    sinhala: str
    status: Literal["official_usage", "plain_language", "native_speaker_approved", "pending_review"]


class GlossarySource(BaseModel):
    """Public source used to select terminology."""

    title: str
    url: str


class SinhalaGlossary(BaseModel):
    """Validated glossary artifact injected into trusted agent context."""

    # Frozen because load_sinhala_glossary() is cached and hands the same instance to every caller.
    model_config = ConfigDict(frozen=True)

    schema_version: int
    language: Literal["si"]
    review_status: Literal["pending_native_speaker_review", "native_speaker_demo_flow_approved", "reviewed"]
    review_note: str
    sources: list[GlossarySource]
    entries: list[GlossaryEntry]


@lru_cache(maxsize=1)
def load_sinhala_glossary() -> SinhalaGlossary:
    """Load and validate the versioned Sinhala glossary."""
    with GLOSSARY_PATH.open(encoding="utf-8") as handle:
        return SinhalaGlossary.model_validate(json.load(handle))


def detect_message_language(message: str) -> Literal["en", "si"]:
    """Detect Sinhala script or an explicit English request; otherwise use English."""
    return "si" if SINHALA_PATTERN.search(message) or EXPLICIT_SINHALA_REQUEST_PATTERN.search(message) else "en"


def resolve_response_language(message: str, preferred_language: str | None = None) -> Literal["en", "si"]:
    """Resolve deterministic reply language using the same preference rule as model guidance."""
    return "si" if preferred_language == "si" else detect_message_language(message)


def reply_in_sinhala(profile: FarmerProfile, message: str) -> bool:
    """Decide a deterministic reply's language exactly as build_language_guidance decides the model's."""
    return resolve_response_language(message, language_preference(profile)) == "si"


def session_reply_in_sinhala(cache: Cache, message: str) -> bool:
    """Load this conversation's profile and decide the deterministic reply language."""
    return reply_in_sinhala(load_profile(cache), message)


def clean_sinhala_weather_reply(reply: str) -> str:
    """Remove model-added English glosses and foreign-script leakage from Sinhala weather text.

    Markdown source URLs are deliberately preserved. This is restricted to weather replies so
    reviewed technical crop terms such as ``පත්‍ර හැකිළීම (leaf curl)`` remain available.
    """
    cleaned = reply.replace("භූගෝලීය স্থානගත කිරීම්", "භූ-ඛණ්ඩාංක")
    cleaned = cleaned.replace("භූගෝලීය ස්ථානගත කිරීම්", "භූ-ඛණ්ඩාංක")
    cleaned = cleaned.replace("මොණරාගල", "මොනරාගල")
    cleaned = cleaned.replace("geocoded_locality", "නම් කළ ප්‍රදේශයේ භූ-ඛණ්ඩාංක")
    cleaned = cleaned.replace("district_representative", "දිස්ත්‍රික්කයේ නියෝජිත ස්ථානයක භූ-ඛණ්ඩාංක")
    cleaned = PARENTHETICAL_ENGLISH_GLOSS_PATTERN.sub("", cleaned)
    cleaned = BENGALI_PATTERN.sub("", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned)


@lru_cache(maxsize=1)
def sinhala_terms() -> Mapping[str, str]:
    """Map each reviewed English term to its Sinhala rendering, keyed by the glossary's english field."""
    return MappingProxyType({entry.english: entry.sinhala for entry in load_sinhala_glossary().entries})


def build_language_guidance(message: str, preferred_language: str | None = None) -> dict[str, object]:
    """Build compact trusted guidance for the model's response language and terminology."""
    response_language = resolve_response_language(message, preferred_language)
    if response_language == "en":
        return {
            "response_language": "en",
            "style": "Use short, plain English suitable for WhatsApp.",
        }

    glossary = load_sinhala_glossary()
    return {
        "response_language": "si",
        "style": (
            "Use short, natural Sinhala suitable for WhatsApp. Preserve numbers, units, dates, "
            "source names, and URLs exactly. For a pending-review technical term, use the supplied "
            "Sinhala wording with its English term in parentheses. Do not invent translations. "
            f"Always write the product name as '{SINHALA_PRODUCT_NAME}'; never shorten it to "
            "'ගොවි මිතුර'."
        ),
        "glossary_review_status": glossary.review_status,
        "terminology": dict(sinhala_terms()),
    }
