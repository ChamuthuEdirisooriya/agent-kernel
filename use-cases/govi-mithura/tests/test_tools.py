"""Tests for deterministic Agent Kernel tools."""

import json
from datetime import datetime as RealDatetime

import pytest

import tools as tools_module
from farmer_profile import COLOMBO_TZ
from tools import calculate_crop_age


def test_crop_age_default_date_uses_colombo_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class FakeDatetime:
        @classmethod
        def now(cls, timezone: object) -> RealDatetime:
            observed["timezone"] = timezone
            return RealDatetime(2026, 9, 1, 0, 5, tzinfo=COLOMBO_TZ)

    monkeypatch.setattr(tools_module, "datetime", FakeDatetime)

    result = json.loads(calculate_crop_age("2026-08-01"))

    assert observed["timezone"] is COLOMBO_TZ
    assert result["as_of_date"] == "2026-09-01"
    assert result["age_days"] == 31
