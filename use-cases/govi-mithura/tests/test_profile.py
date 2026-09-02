"""Tests for farmer-profile normalization and persistence."""

import pytest
from agentkernel.core import KeyValueCache

from farmer_profile import (
    FarmerProfile,
    PreferredLanguage,
    calculate_age_days,
    load_profile,
    normalize_crop,
    normalize_district,
    normalize_location,
    save_profile,
    update_profile,
)


def test_profile_normalizes_supported_farmer_context() -> None:
    profile = update_profile(
        FarmerProfile(),
        name="  Nimal   Perera ",
        district="monaragala",
        crop="chilli",
        planting_date="2026-06-03",
        preferred_language="Sinhala",
    )

    assert profile.name == "Nimal Perera"
    assert profile.district == "Monaragala"
    assert profile.crops == ["chili"]
    assert profile.planting_dates == {"chili": "2026-06-03"}
    assert profile.preferred_language is PreferredLanguage.SINHALA


def test_profile_stores_farmer_locality_without_inventing_a_district() -> None:
    profile = update_profile(FarmerProfile(), location="  Wellawaya  ", crop="chili")

    assert profile.location == "Wellawaya"
    assert profile.district is None
    assert profile.has_context() is True


def test_new_location_and_district_inputs_replace_stale_location_context() -> None:
    locality = update_profile(FarmerProfile(district="Kandy"), location="Wellawaya")
    district = update_profile(locality, district="Badulla")

    assert locality.location == "Wellawaya"
    assert locality.district is None
    assert district.location is None
    assert district.district == "Badulla"


def test_profile_rejects_unsupported_values() -> None:
    with pytest.raises(ValueError, match="district"):
        normalize_district("Not a district")
    with pytest.raises(ValueError, match="Supported crops"):
        normalize_crop("tea")
    with pytest.raises(ValueError, match="language"):
        update_profile(FarmerProfile(), preferred_language="Tamil")
    with pytest.raises(ValueError, match="at most"):
        normalize_location("x" * 101)


def test_profiles_are_isolated_by_cache() -> None:
    first_cache = KeyValueCache()
    second_cache = KeyValueCache()
    first_profile = update_profile(FarmerProfile(), district="Kandy", crop="paddy")
    save_profile(first_cache, first_profile)

    assert load_profile(first_cache).district == "Kandy"
    assert load_profile(second_cache).district is None


def test_crop_age_is_deterministic() -> None:
    assert calculate_age_days("2026-06-03", "2026-07-11") == 38
    with pytest.raises(ValueError, match="after"):
        calculate_age_days("2026-07-12", "2026-07-11")


@pytest.mark.parametrize(
    ("sinhala", "canonical"),
    [
        ("අම්පාර", "Ampara"),
        ("අනුරාධපුර", "Anuradhapura"),
        ("බදුල්ල", "Badulla"),
        ("මඩකලපුව", "Batticaloa"),
        ("කොළඹ", "Colombo"),
        ("ගාල්ල", "Galle"),
        ("ගම්පහ", "Gampaha"),
        ("හම්බන්තොට", "Hambantota"),
        ("යාපනය", "Jaffna"),
        ("කළුතර", "Kalutara"),
        ("මහනුවර", "Kandy"),
        ("කෑගල්ල", "Kegalle"),
        ("කිලිනොච්චිය", "Kilinochchi"),
        ("කුරුණෑගල", "Kurunegala"),
        ("මන්නාරම", "Mannar"),
        ("මාතලේ", "Matale"),
        ("මාතර", "Matara"),
        ("මොනරාගල", "Monaragala"),
        ("මුලතිව්", "Mullaitivu"),
        ("නුවරඑළිය", "Nuwara Eliya"),
        ("පොළොන්නරුව", "Polonnaruwa"),
        ("පුත්තලම", "Puttalam"),
        ("රත්නපුර", "Ratnapura"),
        ("ත්‍රිකුණාමලය", "Trincomalee"),
        ("වවුනියාව", "Vavuniya"),
    ],
)
def test_all_districts_have_sinhala_aliases(sinhala: str, canonical: str) -> None:
    assert normalize_district(sinhala) == canonical
