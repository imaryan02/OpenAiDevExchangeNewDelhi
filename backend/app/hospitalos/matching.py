"""Deterministic facility ranking over explicitly synthetic resource snapshots."""

from datetime import UTC, datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any, Literal

from pydantic import BaseModel

Origin = Literal["CENTRAL_DELHI", "NORTH_DELHI", "EAST_DELHI"]
Preference = Literal["ANY", "AFFORDABLE", "PRIVATE"]
Requirement = Literal["GENERAL", "ICU", "TRAUMA", "PEDIATRIC", "OBSTETRIC"]

ORIGINS: dict[Origin, tuple[float, float]] = {
    "CENTRAL_DELHI": (28.6328, 77.2197),
    "NORTH_DELHI": (28.6862, 77.2060),
    "EAST_DELHI": (28.6304, 77.2908),
}
MAX_RESOURCE_AGE = timedelta(hours=24)


class FacilityView(BaseModel):
    slug: str
    name: str
    area: str
    address: str
    cost_category: str
    synthetic: bool
    connected_receiving_desk: bool
    emergency_open: bool
    ed_bays_ready: int
    ed_bays_available: int
    ed_holds_active: int
    icu_beds_ready: int
    icu_beds_available: int
    icu_holds_active: int
    ventilators_ready: int
    pending_requests: int
    ct_available: bool
    trauma_available: bool
    pediatric_available: bool
    obstetric_available: bool
    verified_at: datetime
    distance_km: float
    recommended: bool
    reason_codes: list[str]


def _distance_km(start: tuple[float, float], end: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*start, *end))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(min(1.0, sqrt(a)))


def rank_facilities(
    rows: list[dict[str, Any]],
    *,
    origin: Origin,
    preference: Preference,
    requirement: Requirement,
    now: datetime | None = None,
) -> list[FacilityView]:
    """Only operational facts determine eligibility; preference orders eligible options."""
    current = now or datetime.now(UTC)
    results: list[FacilityView] = []
    for row in rows:
        reasons: list[str] = []
        ed_holds = int(row.get("ed_holds_active") or 0)
        icu_holds = int(row.get("icu_holds_active") or 0)
        ed_available = max(0, int(row["ed_bays_ready"]) - ed_holds)
        icu_available = max(0, int(row["icu_beds_ready"]) - icu_holds)
        verified_at = row["verified_at"]
        if verified_at.tzinfo is None:
            verified_at = verified_at.replace(tzinfo=UTC)
        if current - verified_at > MAX_RESOURCE_AGE or verified_at > current + timedelta(minutes=5):
            reasons.append("STATUS_NEEDS_RECONFIRMATION")
        if not row["emergency_open"]:
            reasons.append("EMERGENCY_SERVICE_NOT_OPEN")
        if ed_available <= 0:
            reasons.append("RECEIVING_SPACES_HELD" if ed_holds else "NO_READY_RECEIVING_SPACE")
        if requirement == "ICU" and icu_available <= 0:
            reasons.append("ICU_SPACES_HELD" if icu_holds else "ICU_RESOURCE_NOT_READY")
        if requirement == "TRAUMA" and not row["trauma_available"]:
            reasons.append("TRAUMA_CAPABILITY_NOT_LISTED")
        if requirement == "PEDIATRIC" and not row["pediatric_available"]:
            reasons.append("PEDIATRIC_CAPABILITY_NOT_LISTED")
        if requirement == "OBSTETRIC" and not row["obstetric_available"]:
            reasons.append("OBSTETRIC_CAPABILITY_NOT_LISTED")
        distance = _distance_km(
            ORIGINS[origin], (float(row["latitude"]), float(row["longitude"]))
        )
        results.append(
            FacilityView(
                slug=row["slug"],
                name=row["name"],
                area=row["area"],
                address=row["address"],
                cost_category=row["cost_category"],
                synthetic=bool(row["synthetic"]),
                connected_receiving_desk=bool(row["receiving_enabled"]),
                emergency_open=bool(row["emergency_open"]),
                ed_bays_ready=int(row["ed_bays_ready"]),
                ed_bays_available=ed_available,
                ed_holds_active=ed_holds,
                icu_beds_ready=int(row["icu_beds_ready"]),
                icu_beds_available=icu_available,
                icu_holds_active=icu_holds,
                ventilators_ready=int(row["ventilators_ready"]),
                pending_requests=int(row.get("pending_requests") or 0),
                ct_available=bool(row["ct_available"]),
                trauma_available=bool(row["trauma_available"]),
                pediatric_available=bool(row["pediatric_available"]),
                obstetric_available=bool(row["obstetric_available"]),
                verified_at=verified_at,
                distance_km=round(distance, 1),
                recommended=not reasons,
                reason_codes=reasons or ["CURRENT_DEMO_RESOURCES_MATCH"],
            )
        )

    def sort_key(item: FacilityView) -> tuple[int, float, str]:
        penalty = 0.0
        if preference == "AFFORDABLE" and item.cost_category == "PRIVATE":
            penalty = 4.0
        if preference == "PRIVATE" and item.cost_category != "PRIVATE":
            penalty = 4.0
        return (0 if item.recommended else 1, item.distance_km + penalty, item.name)

    return sorted(results, key=sort_key)
