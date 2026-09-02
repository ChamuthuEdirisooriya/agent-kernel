"""Source-backed weather and market information tools for Govi Mithura."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

import httpx

from farmer_profile import COLOMBO_TZ, normalize_district, normalized, now_iso
from language import SINHALA_PATTERN, sinhala_terms

DATA_DIR = Path(__file__).parent / "data"
DISTRICTS_PATH = DATA_DIR / "districts.json"
MARKET_PRICES_PATH = DATA_DIR / "market_prices.json"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_CLIENTS_BY_LOOP: WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = WeakKeyDictionary()
SRI_LANKA_LATITUDE_RANGE = (5.8, 10.0)
SRI_LANKA_LONGITUDE_RANGE = (79.5, 82.0)
# Open-Meteo daily field -> (result key exposed to the agent, minimum, maximum).
DAILY_WEATHER_FIELDS: dict[str, tuple[str, float, float]] = {
    "temperature_2m_max": ("temperature_max_c", -50.0, 60.0),
    "temperature_2m_min": ("temperature_min_c", -50.0, 60.0),
    "precipitation_sum": ("precipitation_mm", 0.0, 2000.0),
    "precipitation_probability_max": ("precipitation_probability_percent", 0.0, 100.0),
    "wind_speed_10m_max": ("wind_speed_max_kmh", 0.0, 500.0),
}
UNAVAILABLE_MARKET_ALIASES = {
    "pettah": "Pettah",
    "පිටකොටුව": "Pettah",
    "colombo": "Colombo",
    "කොළඹ": "Colombo",
}
UNAVAILABLE_COMMODITY_ALIASES = {
    "paddy": "paddy",
    "rice": "paddy",
    "වී": "paddy",
}
# Dataset unit codes mapped to the glossary's English term, so the reviewed Sinhala wording in
# data/sinhala_glossary.json stays the single source for the rendering itself.
UNIT_GLOSSARY_TERMS = {"kg": "per kilogram"}
# Bare classifiers used inside a parenthetical, not the glossary's "wholesale price" noun phrase.
SINHALA_PRICE_TYPE_NAMES = {"wholesale": "තොග", "retail": "සිල්ලර"}


def _sinhala_market_names() -> dict[str, str]:
    """Derive each market's Sinhala name from the snapshot's own market_aliases.

    Uncached like _market_alias_tables: _load_json already avoids the parse, and a second cache
    over the same file would need its own invalidation.
    """
    names: dict[str, str] = {}
    for record in _load_json(MARKET_PRICES_PATH)["records"]:
        for alias in record.get("market_aliases", []):
            if SINHALA_PATTERN.search(alias):
                names.setdefault(record["market"], alias)
    return names


def _sinhala_term(english: str, fallback: str) -> str:
    """Render one reviewed glossary term, falling back to English when it has no entry."""
    return sinhala_terms().get(english, fallback)


def _normalise(value: str) -> str:
    """Shared comparison form, plus the hyphen fold that market and district aliases need."""
    return normalized(value.replace("-", " "))


def _contains_alias(text: str, alias: str) -> bool:
    """Match a normalized alias as a complete word or phrase, never inside another word."""
    if SINHALA_PATTERN.search(alias):
        # Sinhala case suffixes attach directly to nouns (for example, මිරිස්වල and දඹුල්ලේ).
        return alias in text
    return re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text) is not None


@lru_cache(maxsize=None)
def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


def _district_index() -> dict[str, dict[str, Any]]:
    records = _load_json(DISTRICTS_PATH)["districts"]
    return {_normalise(record["district"]): record for record in records}


def _weather_error(status: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "source": "Open-Meteo Forecast API",
        "source_url": "https://open-meteo.com/en/docs",
        "as_of": now_iso(),
    }


def _location_error(status: str, message: str) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "source": "Open-Meteo Geocoding API",
        "source_url": "https://open-meteo.com/en/docs/geocoding-api",
        "as_of": now_iso(),
    }


def _is_finite_number(value: object, *, minimum: float, maximum: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    numeric_value = float(value)
    return math.isfinite(numeric_value) and minimum <= numeric_value <= maximum


def _valid_daily_weather(daily: dict[str, Any]) -> bool:
    dates = daily.get("time")
    if not isinstance(dates, list) or len(dates) != 7 or not all(isinstance(value, str) for value in dates):
        return False
    try:
        parsed_dates = [date.fromisoformat(value) for value in dates]
    except ValueError:
        return False
    if any((current - previous).days != 1 for previous, current in zip(parsed_dates, parsed_dates[1:])):
        return False

    for field, (_, minimum, maximum) in DAILY_WEATHER_FIELDS.items():
        values = daily.get(field)
        if not isinstance(values, list) or len(values) != len(dates):
            return False
        if not all(_is_finite_number(value, minimum=minimum, maximum=maximum) for value in values):
            return False
    return all(minimum <= maximum for minimum, maximum in zip(daily["temperature_2m_min"], daily["temperature_2m_max"]))


def _canonical_admin_district(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    district_name = re.sub(r"\s+district$", "", value.strip(), flags=re.IGNORECASE)
    try:
        return normalize_district(district_name)
    except ValueError:
        return district_name or None


def _geocoded_location(requested_location: str, payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return None

    candidates: list[dict[str, Any]] = []
    for record in payload["results"]:
        if not isinstance(record, dict) or record.get("country_code") != "LK":
            continue
        latitude = record.get("latitude")
        longitude = record.get("longitude")
        name = record.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if not _is_finite_number(
            latitude,
            minimum=SRI_LANKA_LATITUDE_RANGE[0],
            maximum=SRI_LANKA_LATITUDE_RANGE[1],
        ) or not _is_finite_number(
            longitude,
            minimum=SRI_LANKA_LONGITUDE_RANGE[0],
            maximum=SRI_LANKA_LONGITUDE_RANGE[1],
        ):
            continue
        candidates.append(record)

    if not candidates:
        return None

    requested_key = _normalise(requested_location)
    selected = next((record for record in candidates if _normalise(record["name"]) == requested_key), candidates[0])
    resolved_name = selected["name"].strip()
    return {
        "requested_location": requested_location,
        "resolved_location": resolved_name,
        "district": _canonical_admin_district(selected.get("admin2")),
        "representative_location": resolved_name,
        "coordinates": {
            "latitude": float(selected["latitude"]),
            "longitude": float(selected["longitude"]),
        },
        "location_resolution": "Open-Meteo coordinates for the named locality",
        "location_source": "Open-Meteo Geocoding API",
        "location_source_url": "https://open-meteo.com/en/docs/geocoding-api",
        "limitation": (
            "Forecast using coordinates returned for the named locality by Open-Meteo geocoding; "
            "conditions can differ within the surrounding area."
        ),
    }


async def _resolve_weather_location(
    location: str,
    *,
    client: httpx.AsyncClient,
    request_timeout: float,
) -> dict[str, Any]:
    requested_location = " ".join(location.strip().split())
    if not requested_location or len(requested_location) > 100:
        return _location_error("invalid_location", "Provide a Sri Lankan town, village, locality, or district.")

    districts = _district_index()
    try:
        canonical_district = normalize_district(requested_location)
    except ValueError:
        canonical_district = ""

    if canonical_district:
        district_record = districts[_normalise(canonical_district)]
        return {
            "status": "ok",
            "requested_location": requested_location,
            "resolved_location": district_record["representative_location"],
            "district": district_record["district"],
            "representative_location": district_record["representative_location"],
            "coordinates": {
                "latitude": district_record["latitude"],
                "longitude": district_record["longitude"],
            },
            "location_resolution": "bundled representative coordinates for the district",
            "location_source": "Bundled Sri Lankan district dataset",
            "limitation": (
                "District-level forecast using representative-location coordinates; "
                "conditions can differ within the district."
            ),
        }

    try:
        response = await client.get(
            OPEN_METEO_GEOCODING_URL,
            params={
                "name": requested_location,
                "count": 5,
                "language": "en",
                "format": "json",
                "countryCode": "LK",
            },
            timeout=request_timeout,
        )
        response.raise_for_status()
        geocoded = _geocoded_location(requested_location, response.json())
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return _location_error(
            "location_lookup_error",
            "The location service is temporarily unavailable. Please try again later.",
        )

    if geocoded is None:
        return _location_error(
            "invalid_location",
            "That Sri Lankan location could not be found. Check the spelling or provide a nearby town.",
        )
    return {"status": "ok", **geocoded}


def parse_weather_response(location: dict[str, Any], payload: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Convert an Open-Meteo response into the stable result exposed to the agent."""
    daily = payload.get("daily")
    if payload.get("timezone") != "Asia/Colombo" or not isinstance(daily, dict) or not _valid_daily_weather(daily):
        return _weather_error("malformed_response", "The weather service returned an unexpected response.")

    dates = daily["time"]
    forecast = [
        {"date": forecast_date, **{key: daily[field][index] for field, (key, _, _) in DAILY_WEATHER_FIELDS.items()}}
        for index, forecast_date in enumerate(dates)
    ]

    return {
        "status": "ok",
        **{key: value for key, value in location.items() if key != "status"},
        "timezone": payload["timezone"],
        "forecast": forecast,
        "source": "Open-Meteo Forecast API",
        "source_url": "https://open-meteo.com/en/docs",
        "as_of": as_of,
    }


def _shared_client() -> httpx.AsyncClient:
    """Return an Open-Meteo client scoped to the current event loop.

    AsyncClient connection pools are loop-bound. Reusing one client inside a server loop preserves
    its DNS/TCP/TLS benefit, while a later ``asyncio.run`` receives a fresh compatible client.
    """
    loop = asyncio.get_running_loop()
    client = _CLIENTS_BY_LOOP.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient()
        _CLIENTS_BY_LOOP[loop] = client
    return client


async def fetch_weather_forecast(
    location: str,
    *,
    client: httpx.AsyncClient | None = None,
    request_timeout: float = 10.0,
) -> dict[str, Any]:
    """Fetch a seven-day forecast for a Sri Lankan locality or district."""
    resolved_client = client or _shared_client()
    resolved = await _resolve_weather_location(
        location,
        client=resolved_client,
        request_timeout=request_timeout,
    )
    if resolved["status"] != "ok":
        return resolved

    params = {
        "latitude": resolved["coordinates"]["latitude"],
        "longitude": resolved["coordinates"]["longitude"],
        "daily": ",".join(DAILY_WEATHER_FIELDS),
        "timezone": "Asia/Colombo",
        "forecast_days": 7,
    }
    try:
        response = await resolved_client.get(OPEN_METEO_URL, params=params, timeout=request_timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return _weather_error("malformed_response", "The weather service returned an unexpected response.")
        return parse_weather_response(resolved, payload, now_iso())
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return _weather_error("upstream_error", "Live weather is temporarily unavailable. Please try again later.")


async def get_weather_forecast(location: str) -> str:
    """Get a source-attributed forecast for a Sri Lankan town, village, locality, or district."""
    raw_timeout = os.getenv("WEATHER_REQUEST_TIMEOUT_SECONDS", "10")
    try:
        timeout = max(float(raw_timeout), 1.0)
    except ValueError:
        timeout = 10.0
    return json.dumps(await fetch_weather_forecast(location, request_timeout=timeout), ensure_ascii=False)


def query_market_prices(
    commodity: str,
    market: str = "",
    *,
    as_of_date: str | None = None,
    stale_after_days: int = 7,
) -> dict[str, Any]:
    """Query the bundled, provenance-preserving HARTI market-price snapshot."""
    dataset = _load_json(MARKET_PRICES_PATH)
    requested_commodity = _normalise(commodity)
    requested_market = _normalise(market)
    records = dataset["records"]

    def matches_commodity(record: dict[str, Any]) -> bool:
        return requested_commodity in {_normalise(record["commodity"]), *map(_normalise, record.get("aliases", []))}

    commodity_records = [record for record in records if matches_commodity(record)]
    available_commodities = sorted({record["commodity"] for record in records})
    if not commodity_records:
        return {
            "status": "not_found",
            "message": "No verified price record is available for that commodity.",
            "available_commodities": available_commodities,
            **dataset["source"],
            "as_of": dataset["data_date"],
        }

    matched_records = commodity_records
    if requested_market:
        matched_records = [
            record
            for record in commodity_records
            if requested_market in {_normalise(record["market"]), *map(_normalise, record.get("market_aliases", []))}
        ]
        if not matched_records:
            return {
                "status": "not_found",
                "message": "No verified record exists for that exact market; no substitute was used.",
                "available_markets": sorted(record["market"] for record in commodity_records),
                **dataset["source"],
                "as_of": dataset["data_date"],
            }

    reference_date = date.fromisoformat(as_of_date) if as_of_date else datetime.now(COLOMBO_TZ).date()
    matched_dates = [date.fromisoformat(record.get("data_date", dataset["data_date"])) for record in matched_records]
    effective_data_date = min(matched_dates)
    age_days = max((reference_date - effective_data_date).days, 0)
    return {
        "status": "ok",
        "commodity": matched_records[0]["commodity"],
        "records": [
            {key: value for key, value in record.items() if key not in {"aliases", "market_aliases"}}
            for record in matched_records
        ],
        "stale": age_days > stale_after_days,
        "data_age_days": age_days,
        "stale_after_days": stale_after_days,
        **dataset["source"],
        "as_of": dataset["data_date"],
        "oldest_record_date": effective_data_date.isoformat(),
        "limitation": "Indicative market price ranges, not a guaranteed farm-gate or transaction price.",
    }


def _market_stale_after_days() -> int:
    raw_threshold = os.getenv("MARKET_PRICE_STALE_AFTER_DAYS", "7")
    try:
        return max(int(raw_threshold), 0)
    except ValueError:
        return 7


def get_market_prices(commodity: str, market: str = "") -> str:
    """Get verified HARTI wholesale price ranges without substituting unavailable markets."""
    return json.dumps(
        query_market_prices(commodity, market, stale_after_days=_market_stale_after_days()),
        ensure_ascii=False,
    )


def _market_alias_tables() -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Build the longest-alias-first commodity and market lookup tables from the cached snapshot.

    Deliberately uncached: _load_json already avoids the parse, and a second cache over the same
    file would need its own invalidation.
    """
    dataset = _load_json(MARKET_PRICES_PATH)
    commodity_aliases: dict[str, str] = dict(UNAVAILABLE_COMMODITY_ALIASES)
    market_aliases: dict[str, str] = dict(UNAVAILABLE_MARKET_ALIASES)
    for record in dataset["records"]:
        for alias in [record["commodity"], *record.get("aliases", [])]:
            commodity_aliases[_normalise(alias)] = record["commodity"]
        for alias in [record["market"], *record.get("market_aliases", [])]:
            market_aliases[_normalise(alias)] = record["market"]

    def ordered(aliases: dict[str, str]) -> tuple[tuple[str, str], ...]:
        return tuple((alias, aliases[alias]) for alias in sorted(aliases, key=len, reverse=True))

    return ordered(commodity_aliases), ordered(market_aliases)


def resolve_market_price_request(message: str) -> tuple[str, str] | None:
    """Resolve supported and explicitly unsupported market-price names from a farmer message."""
    commodity_aliases, market_aliases = _market_alias_tables()
    normalized = _normalise(message)

    commodity = next((name for alias, name in commodity_aliases if _contains_alias(normalized, alias)), None)
    if commodity is None:
        return None
    market = next((name for alias, name in market_aliases if _contains_alias(normalized, alias)), "")
    return commodity, market


def _price_line(record: dict[str, Any], sinhala: bool) -> str:
    """Render one market's price row, preserving the record's own unit and price type."""
    price_range = f"{record['price_min_lkr']}–{record['price_max_lkr']}"
    if not sinhala:
        return (
            f"- **{record['market']}:** LKR {price_range} per "
            f"{record['unit']} ({record['price_type']}; data date: {record['data_date']})"
        )
    market_name = _sinhala_market_names().get(record["market"], record["market"])
    unit_name = _sinhala_term(UNIT_GLOSSARY_TERMS.get(record["unit"], record["unit"]), record["unit"])
    price_type_name = SINHALA_PRICE_TYPE_NAMES.get(record["price_type"], record["price_type"])
    return f"- **{market_name}:** {unit_name} රු. {price_range} ({price_type_name}; දත්ත දිනය: {record['data_date']})"


def grounded_market_price_reply(message: str, *, sinhala: bool) -> str:
    """Render a market answer directly from the verified local snapshot."""
    resolved = resolve_market_price_request(message)
    if resolved is None:
        if sinhala:
            return "තහවුරු කළ මිලක් ලබා දීමට භාණ්ඩය සහ වෙළඳපොළ පැහැදිලිව සඳහන් කරන්න."
        return "Please name the commodity and market so I can return a verified price."

    commodity, market = resolved
    result = query_market_prices(commodity, market, stale_after_days=_market_stale_after_days())
    attribution = f"{result['source']} ({result['source_url']})"
    as_of = result["as_of"]

    if result["status"] != "ok":
        if sinhala:
            subject = f"{market} වෙළඳපොළ සඳහා " if market else ""
            return (
                f"{subject}එම භාණ්ඩයට තහවුරු කළ මිල වාර්තාවක් නොමැති නිසා වෙනත් වෙළඳපොළක "
                f"මිලක් ආදේශ කළේ නැහැ.\n\n**දත්ත දිනය:** {as_of}\n**මූලාශ්‍රය:** {attribution}"
            )
        subject = f" for {market}" if market else ""
        return (
            f"No verified price record is available for that commodity{subject}; no other market was substituted.\n\n"
            f"**Data date:** {as_of}\n**Source:** {attribution}"
        )

    lines = "\n".join(_price_line(record, sinhala) for record in result["records"])
    if sinhala:
        heading = f"**{_sinhala_term(result['commodity'], result['commodity'])} මිල:**"
        dated_source = f"**බුලටින් දිනය:** {as_of}\n**මූලාශ්‍රය:** {attribution}"
        stale = f"\n**පරණ දත්ත අනතුරු ඇඟවීම:** පැරණිතම ගැළපෙන දත්ත දින {result['data_age_days']}ක් පැරණියි."
        limitation = "\n**සීමාව:** මෙය යොමු වෙළඳපොළ මිල පරාසයක් පමණක් වන අතර සහතික කළ ගොවිපළ හෝ ගනුදෙනු මිලක් නොවේ."
    else:
        heading = f"**{result['commodity'].title()} prices:**"
        dated_source = f"**Bulletin date:** {as_of}\n**Source:** {attribution}"
        stale = f"\n**Stale-data warning:** The oldest matched record is {result['data_age_days']} days old."
        limitation = "\n**Limitation:** Indicative market ranges, not a guaranteed farm-gate or transaction price."
    return f"{heading}\n\n{lines}\n\n{dated_source}" + (stale if result["stale"] else "") + limitation
