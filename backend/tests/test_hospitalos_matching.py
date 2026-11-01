from datetime import UTC, datetime, timedelta

from app.hospitalos.matching import rank_facilities

NOW = datetime(2026, 11, 1, 12, tzinfo=UTC)


def facility(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "slug": "geeta-medicine", "name": "Geeta Medicine", "area": "Demo area",
        "address": "Synthetic location", "latitude": 28.633, "longitude": 77.219,
        "cost_category": "CHARITABLE", "synthetic": True, "receiving_enabled": True,
        "emergency_open": True, "ed_bays_ready": 2, "icu_beds_ready": 1,
        "ventilators_ready": 1, "ct_available": True, "trauma_available": True,
        "pediatric_available": False, "obstetric_available": False,
        "verified_at": NOW,
    }
    row.update(changes)
    return row


def rank(*rows: dict[str, object], requirement: str = "GENERAL", preference: str = "ANY"):
    return rank_facilities(list(rows), origin="CENTRAL_DELHI", preference=preference, requirement=requirement, now=NOW)  # type: ignore[arg-type]


def test_closed_or_stale_facility_is_not_recommended() -> None:
    result = rank(facility(emergency_open=False), facility(slug="stale", verified_at=NOW - timedelta(hours=25)))
    assert not any(item.recommended for item in result)
    assert "EMERGENCY_SERVICE_NOT_OPEN" in result[0].reason_codes
    assert "STATUS_NEEDS_RECONFIRMATION" in result[1].reason_codes


def test_resource_requirement_changes_eligibility() -> None:
    no_icu = rank(facility(icu_beds_ready=0), requirement="ICU")[0]
    assert not no_icu.recommended
    assert "ICU_RESOURCE_NOT_READY" in no_icu.reason_codes
    assert rank(facility(icu_beds_ready=1), requirement="ICU")[0].recommended


def test_eligible_facility_precedes_nearer_unavailable_facility() -> None:
    near_unavailable = facility(slug="near", name="Near", ed_bays_ready=0)
    farther_ready = facility(slug="far", name="Far", latitude=28.68)
    result = rank(near_unavailable, farther_ready)
    assert [item.slug for item in result] == ["far", "near"]


def test_preference_orders_eligible_results_without_overriding_readiness() -> None:
    near_private = facility(slug="private", name="Private", cost_category="PRIVATE")
    farther_charitable = facility(slug="charitable", name="Charitable", latitude=28.65)
    assert rank(near_private, farther_charitable, preference="AFFORDABLE")[0].slug == "charitable"
    assert rank(near_private, farther_charitable, preference="PRIVATE")[0].slug == "private"
