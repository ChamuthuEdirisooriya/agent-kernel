"""Tests for weather and market tools without depending on live upstream services."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import httpx
import pytest

import field_tools
from farmer_profile import DISTRICTS
from field_tools import (
    DISTRICTS_PATH,
    OPEN_METEO_GEOCODING_URL,
    OPEN_METEO_URL,
    fetch_weather_forecast,
    grounded_market_price_reply,
    query_market_prices,
    resolve_market_price_request,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "open_meteo_forecast.json"


def _fixture() -> dict[str, object]:
    with FIXTURE_PATH.open(encoding="utf-8") as handle:
        result: dict[str, object] = json.load(handle)
    return result


@pytest.mark.asyncio
async def test_weather_without_injected_client_uses_the_shared_offline_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=_fixture()))
    async with httpx.AsyncClient(transport=transport) as client:
        monkeypatch.setattr(field_tools, "_shared_client", lambda: client)
        result = await fetch_weather_forecast("Kandy")

    assert result["status"] == "ok"


def test_shared_weather_client_is_reused_only_within_its_event_loop() -> None:
    field_tools._CLIENTS_BY_LOOP.clear()

    async def capture_client() -> httpx.AsyncClient:
        first = field_tools._shared_client()
        assert field_tools._shared_client() is first
        await first.aclose()
        return first

    first_loop_client = asyncio.run(capture_client())
    second_loop_client = asyncio.run(capture_client())

    assert second_loop_client is not first_loop_client
    field_tools._CLIENTS_BY_LOOP.clear()


@pytest.mark.asyncio
async def test_weather_forecast_is_structured_and_attributed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(OPEN_METEO_URL)
        assert request.url.params["forecast_days"] == "7"
        assert request.url.params["timezone"] == "Asia/Colombo"
        return httpx.Response(200, json=_fixture())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_weather_forecast("  kurunegala ", client=client)

    assert result["status"] == "ok"
    assert result["district"] == "Kurunegala"
    assert result["location_resolution"] == "bundled representative coordinates for the district"
    assert "_" not in result["location_resolution"]
    assert result["source"] == "Open-Meteo Forecast API"
    assert result["forecast"][0] == {
        "date": "2026-07-11",
        "temperature_max_c": 30.1,
        "temperature_min_c": 23.2,
        "precipitation_mm": 4.2,
        "precipitation_probability_percent": 65,
        "wind_speed_max_kmh": 15.1,
    }
    assert "representative-location" in result["limitation"]


@pytest.mark.asyncio
async def test_weather_geocodes_a_sri_lankan_locality_before_fetching_forecast() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url).startswith(OPEN_METEO_GEOCODING_URL):
            assert request.url.params["name"] == "Wellawaya"
            assert request.url.params["countryCode"] == "LK"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Wellawaya",
                            "latitude": 6.73694,
                            "longitude": 81.10279,
                            "country_code": "LK",
                            "admin2": "Moneragala District",
                        }
                    ]
                },
            )
        assert str(request.url).startswith(OPEN_METEO_URL)
        assert request.url.params["latitude"] == "6.73694"
        assert request.url.params["longitude"] == "81.10279"
        return httpx.Response(200, json=_fixture())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_weather_forecast("Wellawaya", client=client)

    assert len(requests) == 2
    assert result["status"] == "ok"
    assert result["requested_location"] == "Wellawaya"
    assert result["resolved_location"] == "Wellawaya"
    assert result["district"] == "Monaragala"
    assert result["coordinates"] == {"latitude": 6.73694, "longitude": 81.10279}
    assert result["location_resolution"] == "Open-Meteo coordinates for the named locality"
    assert "_" not in result["location_resolution"]
    assert result["location_source"] == "Open-Meteo Geocoding API"
    assert "named locality" in result["limitation"]


@pytest.mark.asyncio
async def test_weather_rejects_unknown_location_after_sri_lanka_geocoding_lookup() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url).startswith(OPEN_METEO_GEOCODING_URL)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_weather_forecast("Atlantis", client=client)

    assert result["status"] == "invalid_location"
    assert calls == 1


@pytest.mark.asyncio
async def test_weather_rejects_geocoding_results_outside_sri_lanka() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "London",
                        "latitude": 51.5074,
                        "longitude": -0.1278,
                        "country_code": "GB",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_weather_forecast("London", client=client)

    assert result["status"] == "invalid_location"


@pytest.mark.asyncio
async def test_weather_reports_location_lookup_timeout_without_forecast_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url).startswith(OPEN_METEO_GEOCODING_URL)
        raise httpx.ReadTimeout("geocoding timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_weather_forecast("Wellawaya", client=client)

    assert calls == 1
    assert result["status"] == "location_lookup_error"
    assert "temporarily unavailable" in result["message"]


@pytest.mark.asyncio
async def test_weather_handles_upstream_failure() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_weather_forecast("Matale", client=client)

    assert result["status"] == "upstream_error"
    assert "temporarily unavailable" in result["message"]


@pytest.mark.asyncio
async def test_weather_handles_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("forecast timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_weather_forecast("Galle", client=client)

    assert result["status"] == "upstream_error"


@pytest.mark.asyncio
async def test_weather_rejects_malformed_daily_arrays() -> None:
    payload = _fixture()
    assert isinstance(payload["daily"], dict)
    payload["daily"]["temperature_2m_max"] = []
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_weather_forecast("Kandy", client=client)

    assert result["status"] == "malformed_response"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("time", "not-a-date"),
        ("temperature_2m_max", "hot"),
        ("temperature_2m_min", None),
        ("precipitation_sum", -50),
        ("precipitation_probability_max", 999),
        ("wind_speed_10m_max", "fast"),
    ],
)
async def test_weather_rejects_invalid_daily_types_and_ranges(field: str, invalid_value: object) -> None:
    payload = _fixture()
    assert isinstance(payload["daily"], dict)
    payload["daily"][field][0] = invalid_value
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_weather_forecast("Kandy", client=client)

    assert result["status"] == "malformed_response"


@pytest.mark.asyncio
async def test_weather_rejects_unexpected_timezone() -> None:
    payload = _fixture()
    payload["timezone"] = "UTC"
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_weather_forecast("Kandy", client=client)

    assert result["status"] == "malformed_response"


def test_all_25_sri_lankan_districts_are_configured() -> None:
    with DISTRICTS_PATH.open(encoding="utf-8") as handle:
        dataset = json.load(handle)
    districts = dataset["districts"]

    assert dataset["coordinate_system"] == "WGS 84 decimal degrees"
    assert len(districts) == 25
    assert [record["district"] for record in districts] == list(DISTRICTS)
    assert len({(record["latitude"], record["longitude"]) for record in districts}) == 25

    for record in districts:
        assert set(record) == {
            "district",
            "representative_location",
            "latitude",
            "longitude",
        }
        assert isinstance(record["representative_location"], str)
        assert record["representative_location"].strip()
        assert 5.8 <= record["latitude"] <= 10.0
        assert 79.5 <= record["longitude"] <= 82.0


def test_coordinate_dataset_cannot_claim_review_without_evidence() -> None:
    with DISTRICTS_PATH.open(encoding="utf-8") as handle:
        dataset = json.load(handle)

    assert dataset["review_status"] in {
        "pending_independent_coordinate_review",
        "independently_verified",
    }
    if dataset["review_status"] == "independently_verified":
        assert dataset["reviewed_by"].strip()
        assert date.fromisoformat(dataset["reviewed_at"])
        assert dataset["review_source"].strip()


def test_market_price_returns_exact_dambulla_record() -> None:
    result = query_market_prices("green chillies", "Dambulla", as_of_date="2026-08-29")

    assert result["status"] == "ok"
    assert result["stale"] is False
    assert result["records"] == [
        {
            "commodity": "green chili",
            "market": "Dambulla",
            "price_min_lkr": 450,
            "price_max_lkr": 500,
            "unit": "kg",
            "price_type": "wholesale",
            "data_date": "2026-08-29",
            "source_document": "HARTI Daily Food Commodities Bulletin, 29 August 2026",
        }
    ]
    assert result["source"] == "HARTI Daily Food Commodities Bulletin"


def test_market_price_marks_old_snapshot_stale() -> None:
    result = query_market_prices("chili", as_of_date="2026-09-08", stale_after_days=7)

    assert result["status"] == "ok"
    assert result["stale"] is True
    assert result["data_age_days"] == 11


def test_market_price_does_not_substitute_pettah() -> None:
    result = query_market_prices("chili", "Pettah", as_of_date="2026-08-29")

    assert result["status"] == "not_found"
    assert "no substitute was used" in result["message"]
    assert result["available_markets"] == ["Dambulla", "Meegoda", "Peliyagoda"]


def test_market_price_reports_unsupported_commodity() -> None:
    result = query_market_prices("paddy", as_of_date="2026-08-29")

    assert result["status"] == "not_found"
    assert result["available_commodities"] == ["green chili"]


def test_market_request_does_not_match_rice_inside_price() -> None:
    assert resolve_market_price_request("What is the price?") is None
    assert resolve_market_price_request("What is the price of tomato in Dambulla?") is None


def test_multi_market_reply_displays_each_records_data_date() -> None:
    reply = grounded_market_price_reply("green chili wholesale price", sinhala=False)

    assert "Peliyagoda" in reply and "data date: 2026-08-29" in reply
    assert "Meegoda" in reply and "data date: 2026-08-28" in reply
    assert "Bulletin date:** 2026-08-29" in reply


def test_market_price_does_not_substitute_colombo_for_peliyagoda() -> None:
    result = query_market_prices("chili", "Colombo", as_of_date="2026-08-29")

    assert result["status"] == "not_found"
    assert "no substitute was used" in result["message"]


def test_sinhala_weather_and_market_arguments_are_normalized() -> None:
    market = query_market_prices("අමු මිරිස්", "දඹුල්ල", as_of_date="2026-08-29")

    assert market["status"] == "ok"
    assert market["records"][0]["market"] == "Dambulla"


@pytest.mark.parametrize(
    "message",
    [
        "What is the chilli price in Dambulla?",
        "දඹුල්ලේ මිරිස්වල මිල කීයද?",
        "මිරිස්වලට මිල කීයද?",
    ],
)
def test_market_request_resolves_common_english_and_sinhala_inflections(message: str) -> None:
    resolved = resolve_market_price_request(message)

    assert resolved is not None
    assert resolved[0] == "green chili"


def test_market_reply_renders_dataset_commodity_unit_and_price_type(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = {
        "data_date": "2026-08-29",
        "source": {"source": "Test bulletin", "source_url": "https://example.test/bulletin"},
        "records": [
            {
                "commodity": "pumpkin",
                "aliases": ["pumpkin"],
                "market": "Dambulla",
                "market_aliases": ["දඹුල්ල"],
                "price_min_lkr": 100,
                "price_max_lkr": 120,
                "unit": "each",
                "price_type": "retail",
                "data_date": "2026-08-29",
                "source_document": "Test bulletin",
            }
        ],
    }
    monkeypatch.setattr(field_tools, "_load_json", lambda path: dataset)

    english = grounded_market_price_reply("pumpkin price in Dambulla", sinhala=False)
    sinhala = grounded_market_price_reply("දඹුල්ල pumpkin මිල", sinhala=True)

    assert "Pumpkin prices" in english
    assert "per each (retail" in english
    assert "Green chili" not in english
    assert "pumpkin මිල" in sinhala
    assert "each" in sinhala and "සිල්ලර" in sinhala
    assert "කිලෝග්‍රෑමයකට" not in sinhala


def test_static_market_dataset_is_cached() -> None:
    field_tools._load_json.cache_clear()

    first = field_tools._load_json(field_tools.MARKET_PRICES_PATH)
    second = field_tools._load_json(field_tools.MARKET_PRICES_PATH)

    assert first is second


@pytest.mark.asyncio
async def test_sinhala_district_argument_is_normalized_without_model_translation() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=_fixture()))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await fetch_weather_forecast("කුරුණෑගල", client=client)

    assert result["status"] == "ok"
    assert result["district"] == "Kurunegala"
