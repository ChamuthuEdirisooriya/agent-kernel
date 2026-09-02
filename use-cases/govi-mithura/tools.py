"""Agent Kernel tools for farmer profile memory and deterministic calculations."""

from __future__ import annotations

import json
from datetime import datetime

from agentkernel.core import ToolContext

from farmer_profile import COLOMBO_TZ, calculate_age_days, load_profile, save_profile, update_profile


def get_farmer_profile() -> str:
    """Return the current farmer profile stored in this conversation's session-scoped cache."""
    cache = ToolContext.get().session.get_non_volatile_cache()
    profile = load_profile(cache)
    return profile.model_dump_json(indent=2)


def update_farmer_profile(
    name: str = "",
    location: str = "",
    district: str = "",
    crop: str = "",
    planting_date: str = "",
    preferred_language: str = "",
) -> str:
    """Store farmer details that the user explicitly provided or confirmed.

    Store a farmer-provided town, village, or locality in location; do not infer a district.
    Transliteration without changing the place is allowed. Use an ISO YYYY-MM-DD planting_date and
    include crop whenever a planting date is set. Omit fields the farmer did not provide.
    Supported crops are chili and paddy.
    """
    cache = ToolContext.get().session.get_non_volatile_cache()
    profile = update_profile(
        load_profile(cache),
        name=name,
        location=location,
        district=district,
        crop=crop,
        planting_date=planting_date,
        preferred_language=preferred_language,
    )
    save_profile(cache, profile)
    return json.dumps(
        {
            "status": "saved",
            "profile": profile.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )


def calculate_crop_age(planting_date: str, as_of_date: str = "") -> str:
    """Calculate crop age in days and weeks from ISO YYYY-MM-DD dates."""
    resolved_as_of = as_of_date or datetime.now(COLOMBO_TZ).date().isoformat()
    days = calculate_age_days(planting_date, resolved_as_of)
    return json.dumps(
        {
            "planting_date": planting_date,
            "as_of_date": resolved_as_of,
            "age_days": days,
            "age_weeks": round(days / 7, 1),
        }
    )
