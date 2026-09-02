"""Farmer profile schema, normalization, and session-cache persistence."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

PROFILE_CACHE_KEY = "govi_mithura.farmer_profile"
COLOMBO_TZ = ZoneInfo("Asia/Colombo")
MAX_REMEMBERED_TOPICS = 10
MAX_LOCATION_LENGTH = 100

DISTRICTS = (
    "Ampara",
    "Anuradhapura",
    "Badulla",
    "Batticaloa",
    "Colombo",
    "Galle",
    "Gampaha",
    "Hambantota",
    "Jaffna",
    "Kalutara",
    "Kandy",
    "Kegalle",
    "Kilinochchi",
    "Kurunegala",
    "Mannar",
    "Matale",
    "Matara",
    "Monaragala",
    "Mullaitivu",
    "Nuwara Eliya",
    "Polonnaruwa",
    "Puttalam",
    "Ratnapura",
    "Trincomalee",
    "Vavuniya",
)

DISTRICT_ALIASES = {district.casefold(): district for district in DISTRICTS}
DISTRICT_ALIASES.update(
    {
        "moneragala": "Monaragala",
        "nuwaraeliya": "Nuwara Eliya",
        "nuwara-eliya": "Nuwara Eliya",
        "trinco": "Trincomalee",
        "අම්පාර": "Ampara",
        "අනුරාධපුර": "Anuradhapura",
        "බදුල්ල": "Badulla",
        "මඩකලපුව": "Batticaloa",
        "කොළඹ": "Colombo",
        "ගාල්ල": "Galle",
        "ගම්පහ": "Gampaha",
        "හම්බන්තොට": "Hambantota",
        "යාපනය": "Jaffna",
        "කළුතර": "Kalutara",
        "මහනුවර": "Kandy",
        "කෑගල්ල": "Kegalle",
        "කිලිනොච්චිය": "Kilinochchi",
        "කුරුණෑගල": "Kurunegala",
        "මන්නාරම": "Mannar",
        "මාතලේ": "Matale",
        "මාතර": "Matara",
        "මොනරාගල": "Monaragala",
        "මුලතිව්": "Mullaitivu",
        "නුවරඑළිය": "Nuwara Eliya",
        "පොළොන්නරුව": "Polonnaruwa",
        "පුත්තලම": "Puttalam",
        "රත්නපුර": "Ratnapura",
        "ත්‍රිකුණාමලය": "Trincomalee",
        "වවුනියාව": "Vavuniya",
    }
)

CROP_ALIASES = {
    "chili": "chili",
    "chilli": "chili",
    "chilies": "chili",
    "chillies": "chili",
    "මිරිස්": "chili",
    "paddy": "paddy",
    "rice": "paddy",
    "වී": "paddy",
    "වී වගාව": "paddy",
}


class PreferredLanguage(StrEnum):
    """Languages accepted in the current farmer profile."""

    ENGLISH = "en"
    SINHALA = "si"


LANGUAGE_ALIASES = {
    "en": PreferredLanguage.ENGLISH,
    "english": PreferredLanguage.ENGLISH,
    "si": PreferredLanguage.SINHALA,
    "sinhala": PreferredLanguage.SINHALA,
    "sinhalese": PreferredLanguage.SINHALA,
    "සිංහල": PreferredLanguage.SINHALA,
}


class Cache(Protocol):
    """Subset of Agent Kernel KeyValueCache used by the profile store."""

    def get(self, key: str, default: object = None) -> object: ...

    def set(self, key: str, value: object) -> None: ...


def normalized(value: str) -> str:
    """Casefold and collapse whitespace: the single comparison form all term tables assume."""
    return " ".join(value.casefold().split())


def now_iso() -> str:
    """Return an ISO timestamp in the farmer-facing timezone."""
    return datetime.now(COLOMBO_TZ).isoformat(timespec="seconds")


class FarmerProfile(BaseModel):
    """Minimal, non-sensitive context remembered for a farmer."""

    schema_version: int = 1
    name: str | None = None
    location: str | None = None
    district: str | None = None
    crops: list[str] = Field(default_factory=list)
    planting_dates: dict[str, str] = Field(default_factory=dict)
    preferred_language: PreferredLanguage | None = None
    last_topics: list[str] = Field(default_factory=list, max_length=MAX_REMEMBERED_TOPICS)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def has_context(self) -> bool:
        """Return whether the profile contains useful personalization data."""
        return bool(self.name or self.location or self.district or self.crops or self.preferred_language)


def normalize_district(value: str) -> str:
    """Resolve a district alias to one of Sri Lanka's canonical 25 districts."""
    key = normalized(value)
    district = DISTRICT_ALIASES.get(key)
    if district is None:
        raise ValueError(f"Unsupported or unrecognized Sri Lankan district: {value}")
    return district


def normalize_location(value: str) -> str:
    """Validate a farmer-provided town, village, or locality without inferring its district."""
    location = " ".join(value.strip().split())
    if not location:
        raise ValueError("Location cannot be empty.")
    if len(location) > MAX_LOCATION_LENGTH:
        raise ValueError(f"Location must be at most {MAX_LOCATION_LENGTH} characters.")
    return location


def normalize_crop(value: str) -> str:
    """Resolve an MVP crop alias to its canonical identifier."""
    key = normalized(value)
    crop = CROP_ALIASES.get(key)
    if crop is None:
        raise ValueError(f"Unsupported MVP crop: {value}. Supported crops are chili and paddy.")
    return crop


def normalize_language(value: str) -> PreferredLanguage:
    """Resolve a language name or code to the stored preference."""
    key = normalized(value)
    language = LANGUAGE_ALIASES.get(key)
    if language is None:
        raise ValueError(f"Unsupported language preference: {value}")
    return language


def normalize_planting_date(value: str) -> str:
    """Validate and normalize an explicit ISO planting date."""
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise ValueError("Planting date must use YYYY-MM-DD format.") from exc


def update_profile(
    profile: FarmerProfile,
    *,
    name: str = "",
    location: str = "",
    district: str = "",
    crop: str = "",
    planting_date: str = "",
    preferred_language: str = "",
) -> FarmerProfile:
    """Return a validated profile with only explicitly supplied fields changed."""
    updated = profile.model_copy(deep=True)

    if name.strip():
        updated.name = " ".join(name.strip().split())[:100]
    if location.strip():
        updated.location = normalize_location(location)
        if not district.strip():
            updated.district = None
    if district.strip():
        updated.district = normalize_district(district)
        if not location.strip():
            updated.location = None
    canonical_crop = normalize_crop(crop) if crop.strip() else ""
    if canonical_crop and canonical_crop not in updated.crops:
        updated.crops.append(canonical_crop)
    if planting_date.strip():
        if not canonical_crop:
            raise ValueError("A crop is required when storing a planting date.")
        updated.planting_dates[canonical_crop] = normalize_planting_date(planting_date)
    if preferred_language.strip():
        updated.preferred_language = normalize_language(preferred_language)

    updated.updated_at = now_iso()
    return updated


def load_profile(cache: Cache) -> FarmerProfile:
    """Load and validate a profile, returning an empty profile when absent."""
    raw = cache.get(PROFILE_CACHE_KEY)
    if raw is None:
        return FarmerProfile()
    return FarmerProfile.model_validate(raw)


def save_profile(cache: Cache, profile: FarmerProfile) -> None:
    """Persist a JSON-serializable profile in Agent Kernel memory."""
    cache.set(PROFILE_CACHE_KEY, profile.model_dump(mode="json"))


def language_preference(profile: FarmerProfile) -> str | None:
    """Return the stored reply-language code, or None when the farmer has not chosen one."""
    return profile.preferred_language.value if profile.preferred_language else None


def remember_topic(profile: FarmerProfile, topic: str) -> FarmerProfile:
    """Return a profile with one bounded, de-duplicated internal topic identifier remembered."""
    updated = profile.model_copy(deep=True)
    kept = [value for value in updated.last_topics if value != topic]
    updated.last_topics = (kept + [topic])[-MAX_REMEMBERED_TOPICS:]
    updated.updated_at = now_iso()
    return updated


def record_topic(cache: Cache, topic: str) -> FarmerProfile:
    """Remember one topic for this conversation and persist the updated profile."""
    profile = remember_topic(load_profile(cache), topic)
    save_profile(cache, profile)
    return profile


def calculate_age_days(planting_date: str, as_of_date: str) -> int:
    """Calculate crop age deterministically from two ISO dates."""
    planted = date.fromisoformat(planting_date)
    as_of = date.fromisoformat(as_of_date)
    age = (as_of - planted).days
    if age < 0:
        raise ValueError("Planting date cannot be after the requested as-of date.")
    return age
