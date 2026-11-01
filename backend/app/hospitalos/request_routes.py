"""Synthetic public request tracking and human receiving decisions."""

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.configuration import require_org_admin, require_org_member
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_db_session
from app.hospitalos.matching import Origin, Preference, Requirement, rank_facilities
from app.hospitalos.routes import require_demo
from app.hospitalos.supervisor import choose_task
from app.hospitalos.workflow import (
    append_event,
    authenticated_case,
    capacity_available,
    expire_due,
    request_snapshot,
    token_hash,
)
from app.security.auth import Principal, get_current_principal

router = APIRouter(prefix="/v1/hospitalos", tags=["HospitalOS demo requests"])
TOKEN_FIELD = Field(min_length=40, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class PublicCase(BaseModel):
    case_id: UUID
    tracking_token: str = TOKEN_FIELD


class CreateRequest(PublicCase):
    facility_slug: Literal["geeta-medicine"]
    origin: Origin
    preference: Preference = "ANY"
    requirement: Requirement = "GENERAL"
    audience: Literal["PATIENT", "AMBULANCE"] = "PATIENT"


class PublicEta(PublicCase):
    eta_minutes: int = Field(ge=1, le=240)


class Decision(BaseModel):
    organization_id: UUID
    expected_version: int = Field(ge=1)
    decision_key: UUID
    decision: Literal["ACCEPT", "DECLINE"]
    arrival_note: str | None = Field(default=None, max_length=240)


class OrgAction(BaseModel):
    organization_id: UUID


class TaskAction(OrgAction):
    kind: Literal["RESOURCE_RECHECK", "MATCHING_REVIEW", "COORDINATION_FOLLOWUP"]


FACILITY_SELECT = """select id,organization_id,slug,name,area,address,latitude,longitude,
       cost_category,emergency_open,ed_bays_ready,icu_beds_ready,ventilators_ready,
       ct_available,trauma_available,pediatric_available,obstetric_available,
       receiving_enabled,synthetic,verified_at,version
       from public.hospitalos_facilities where slug='geeta-medicine'"""


@router.post("/requests", status_code=201)
async def create_request(
    payload: CreateRequest,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_demo(settings)
    if payload.audience == "PATIENT" and payload.requirement != "GENERAL":
        raise ApiError(
            "REQUIREMENT_SOURCE_REQUIRED",
            "Patient mode cannot specify a clinical requirement.", 422,
        )
    async with session.begin():
        # One global demo lock bounds anonymous writes and serializes idempotent retries.
        await session.execute(text("select pg_advisory_xact_lock(904621001)"))
        existing = await session.execute(
            text("""select id from public.hospitalos_cases where id=:case_id"""),
            {"case_id": payload.case_id},
        )
        if existing.first() is not None:
            saved = await authenticated_case(session, payload.case_id, payload.tracking_token)
            if any(saved[key] != getattr(payload, key) for key in
                   ("origin", "preference", "requirement", "audience")):
                raise ApiError("CASE_REPLAY_MISMATCH", "This demo case has different filters.", 409)
            return await request_snapshot(session, payload.case_id)
        rate = await session.execute(
            text("""select count(*) from public.hospitalos_cases
                    where created_at>now()-interval '1 hour'""")
        )
        if rate.scalar_one() >= 100:
            raise ApiError("DEMO_RATE_LIMIT", "Demo request limit reached. Try again later.", 429)
        facility_result = await session.execute(text(FACILITY_SELECT + " for update"))
        facility = facility_result.mappings().one_or_none()
        if (
            facility is None or not facility["receiving_enabled"]
            or facility["organization_id"] is None
        ):
            raise ApiError("RECEIVING_DESK_UNAVAILABLE", "Geeta demo desk is unavailable.", 409)
        match = rank_facilities(
            [dict(facility)], origin=payload.origin, preference=payload.preference,
            requirement=payload.requirement,
        )[0]
        if not match.recommended:
            raise ApiError("RESOURCE_RECHECK_REQUIRED", "Demo resources need reconfirmation.", 409,
                           {"reason_codes": match.reason_codes})
        await session.execute(
            text("""insert into public.hospitalos_cases
                    (id,tracking_token_hash,origin,preference,requirement,audience)
                    values (:case_id,:token_hash,:origin,:preference,:requirement,:audience)"""),
            {"case_id": payload.case_id, "token_hash": token_hash(payload.tracking_token),
             "origin": payload.origin, "preference": payload.preference,
             "requirement": payload.requirement, "audience": payload.audience},
        )
        created = await session.execute(
            text("""insert into public.hospitalos_requests
                    (case_id,facility_id,organization_id,deadline_at)
                    values (:case_id,:facility,:org,
                            now()+make_interval(secs => :response_seconds))
                    returning id"""),
            {"case_id": payload.case_id, "facility": facility["id"],
             "org": facility["organization_id"],
             "response_seconds": settings.hospitalos_response_seconds},
        )
        request_id = created.scalar_one()
        await append_event(session, case_id=payload.case_id, request_id=request_id,
                           organization_id=facility["organization_id"],
                           event_type="CASE_CREATED", actor_type="PUBLIC")
        await append_event(session, case_id=payload.case_id, request_id=request_id,
                           organization_id=facility["organization_id"],
                           event_type="ACCEPTANCE_REQUESTED", actor_type="PUBLIC",
                           detail={"facility_slug": "geeta-medicine"})
        return await request_snapshot(session, payload.case_id)


@router.post("/tracking")
async def public_tracking(
    payload: PublicCase,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_demo(settings)
    async with session.begin():
        await authenticated_case(session, payload.case_id, payload.tracking_token)
        await expire_due(session, case_id=payload.case_id)
        return await request_snapshot(session, payload.case_id)


@router.post("/tracking/withdraw")
async def withdraw_request(
    payload: PublicCase,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_demo(settings)
    async with session.begin():
        await authenticated_case(session, payload.case_id, payload.tracking_token)
        await expire_due(session, case_id=payload.case_id)
        result = await session.execute(
            text("""update public.hospitalos_requests
                    set status='WITHDRAWN',version=version+1,updated_at=now()
                    where case_id=:case_id and status in ('PENDING','ACCEPTED')
                    returning id,organization_id"""),
            {"case_id": payload.case_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError("REQUEST_NOT_ACTIVE", "This demo request is no longer active.", 409)
        await session.execute(
            text("""update public.hospitalos_holds
                    set status='RELEASED',ended_at=now()
                    where request_id=:request_id and status='ACTIVE'"""),
            {"request_id": row["id"]},
        )
        await append_event(session, case_id=payload.case_id, request_id=row["id"],
                           organization_id=row["organization_id"],
                           event_type="REQUEST_WITHDRAWN", actor_type="PUBLIC")
        return await request_snapshot(session, payload.case_id)


@router.post("/tracking/eta")
async def update_eta(
    payload: PublicEta,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_demo(settings)
    async with session.begin():
        await authenticated_case(session, payload.case_id, payload.tracking_token)
        await expire_due(session, case_id=payload.case_id)
        result = await session.execute(
            text("""update public.hospitalos_cases c
                    set eta_minutes=:eta,updated_at=now()
                    where c.id=:case_id and exists
                      (select 1 from public.hospitalos_requests r
                       where r.case_id=c.id and
                         (r.status='ACCEPTED' or
                          (r.status='PENDING' and r.deadline_at>now())))
                    returning c.id"""),
            {"case_id": payload.case_id, "eta": payload.eta_minutes},
        )
        if result.first() is None:
            raise ApiError("REQUEST_NOT_ACTIVE", "ETA cannot be updated for this request.", 409)
        request = await session.execute(
            text("""select id,organization_id from public.hospitalos_requests
                    where case_id=:case_id"""), {"case_id": payload.case_id},
        )
        row = request.mappings().one()
        await append_event(session, case_id=payload.case_id, request_id=row["id"],
                           organization_id=row["organization_id"], event_type="ETA_UPDATED",
                           actor_type="PUBLIC", detail={"eta_minutes": payload.eta_minutes})
        return await request_snapshot(session, payload.case_id)


@router.get("/requests")
async def staff_inbox(
    organization_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    require_demo(settings)
    async with session.begin():
        await require_org_member(session, organization_id, principal.user_id)
        await expire_due(session, organization_id=organization_id)
        result = await session.execute(
            text("""select case_id from public.hospitalos_requests
                    where organization_id=:org order by created_at desc limit 30"""),
            {"org": organization_id},
        )
        case_ids = [row[0] for row in result]
        return [await request_snapshot(session, case_id) for case_id in case_ids]


@router.post("/requests/{request_id}/decision")
async def decide_request(
    request_id: UUID,
    payload: Decision,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_demo(settings)
    async with session.begin():
        await require_org_admin(session, payload.organization_id, principal.user_id)
        await expire_due(session, organization_id=payload.organization_id)
        result = await session.execute(
            text("""select id,case_id,facility_id,organization_id,status,version,
                           decision_key,deadline_at
                    from public.hospitalos_requests
                    where id=:request_id and organization_id=:org for update"""),
            {"request_id": request_id, "org": payload.organization_id},
        )
        request = result.mappings().one_or_none()
        if request is None:
            raise ApiError("REQUEST_NOT_FOUND", "Receiving request was not found.", 404)
        if request["decision_key"] == payload.decision_key and request["status"] in (
            "ACCEPTED", "DECLINED", "HOLD_CONFLICT"
        ):
            if (request["status"] == "DECLINED") != (payload.decision == "DECLINE"):
                raise ApiError(
                    "DECISION_REPLAY_MISMATCH", "Decision key was used for another action.", 409
                )
            return await request_snapshot(session, request["case_id"])
        if request["status"] != "PENDING" or request["version"] != payload.expected_version:
            raise ApiError("REQUEST_VERSION_CONFLICT", "Request changed. Refresh the inbox.", 409)
        # A deadline is checked in the write as well as the expiry transition.
        if payload.decision == "DECLINE":
            updated = await session.execute(
                text("""update public.hospitalos_requests
                        set status='DECLINED',version=version+1,updated_at=now(),
                            decided_at=now(),decided_by=:actor,decision_key=:decision_key
                        where id=:request_id and status='PENDING' and deadline_at>now()
                        returning id"""),
                {"request_id": request_id, "actor": principal.user_id,
                 "decision_key": payload.decision_key},
            )
            if updated.first() is None:
                await expire_due(session, case_id=request["case_id"])
                return await request_snapshot(session, request["case_id"])
            await append_event(session, case_id=request["case_id"], request_id=request_id,
                               organization_id=payload.organization_id,
                               event_type="REQUEST_DECLINED", actor_type="USER",
                               actor_id=principal.user_id)
            return await request_snapshot(session, request["case_id"])

        case_result = await session.execute(
            text("""select origin,preference,requirement from public.hospitalos_cases
                    where id=:case_id"""), {"case_id": request["case_id"]},
        )
        case = case_result.mappings().one()
        facility_result = await session.execute(
            text(FACILITY_SELECT + " for update")
        )
        facility = facility_result.mappings().one_or_none()
        if (
            facility is None or facility["id"] != request["facility_id"]
            or not facility["receiving_enabled"]
        ):
            raise ApiError("FACILITY_CHANGED", "Receiving facility is unavailable.", 409)
        match = rank_facilities(
            [dict(facility)], origin=case["origin"], preference=case["preference"],
            requirement=case["requirement"],
        )[0]
        await append_event(session, case_id=request["case_id"], request_id=request_id,
                           organization_id=payload.organization_id,
                           event_type="RESOURCE_REVALIDATED", actor_type="SYSTEM",
                           detail={"ready": match.recommended,
                                   "reason_codes": match.reason_codes,
                                   "resource_version": facility["version"]})
        if not match.recommended:
            return await request_snapshot(session, request["case_id"])
        occupied = await session.execute(
            text("""select coalesce(sum(ed_units),0) as ed,
                           coalesce(sum(icu_units),0) as icu
                    from public.hospitalos_holds
                    where facility_id=:facility and status='ACTIVE'
                      and expires_at>now()"""),
            {"facility": facility["id"]},
        )
        held = occupied.mappings().one()
        needs_icu = case["requirement"] == "ICU"
        if not capacity_available(
            ed_ready=facility["ed_bays_ready"], icu_ready=facility["icu_beds_ready"],
            ed_held=held["ed"], icu_held=held["icu"], needs_icu=needs_icu,
        ):
            conflict = await session.execute(
                text("""update public.hospitalos_requests
                        set status='HOLD_CONFLICT',version=version+1,updated_at=now(),
                            decided_at=now(),decided_by=:actor,decision_key=:decision_key
                        where id=:request_id and status='PENDING' and deadline_at>now()
                        returning id"""),
                {"request_id": request_id, "actor": principal.user_id,
                 "decision_key": payload.decision_key},
            )
            if conflict.first() is None:
                await expire_due(session, case_id=request["case_id"])
                return await request_snapshot(session, request["case_id"])
            await append_event(session, case_id=request["case_id"], request_id=request_id,
                               organization_id=payload.organization_id,
                               event_type="HOLD_CONFLICT", actor_type="USER",
                               actor_id=principal.user_id,
                               detail={"resource": "ED_AND_ICU" if needs_icu else "ED"})
            await append_event(session, case_id=request["case_id"], request_id=request_id,
                               organization_id=payload.organization_id,
                               event_type="HUMAN_REVIEW_REQUESTED", actor_type="SYSTEM",
                               detail={"reason": "CAPACITY_CONFLICT"})
            return await request_snapshot(session, request["case_id"])
        accepted = await session.execute(
            text("""update public.hospitalos_requests
                    set status='ACCEPTED',version=version+1,updated_at=now(),
                        decided_at=now(),decided_by=:actor,decision_key=:decision_key,
                        arrival_note=:arrival_note
                    where id=:request_id and status='PENDING' and deadline_at>now()
                    returning id"""),
            {"request_id": request_id, "actor": principal.user_id,
             "decision_key": payload.decision_key,
             "arrival_note": payload.arrival_note.strip() if payload.arrival_note else None},
        )
        if accepted.first() is None:
            await expire_due(session, case_id=request["case_id"])
            return await request_snapshot(session, request["case_id"])
        await append_event(session, case_id=request["case_id"], request_id=request_id,
                           organization_id=payload.organization_id,
                           event_type="HOSPITAL_ACCEPTED", actor_type="USER",
                           actor_id=principal.user_id)
        await session.execute(
            text("""insert into public.hospitalos_holds
                    (request_id,facility_id,icu_units,expires_at)
                    values (:request_id,:facility,:icu_units,
                            now()+make_interval(mins => :hold_minutes))"""),
            {"request_id": request_id, "facility": facility["id"],
             "icu_units": 1 if needs_icu else 0,
             "hold_minutes": settings.hospitalos_hold_minutes},
        )
        await append_event(session, case_id=request["case_id"], request_id=request_id,
                           organization_id=payload.organization_id,
                           event_type="HOLD_CREATED", actor_type="SYSTEM",
                           detail={"resource": "ED_AND_ICU" if needs_icu else "ED",
                                   "hold_minutes": settings.hospitalos_hold_minutes})
        return await request_snapshot(session, request["case_id"])


@router.post("/requests/{request_id}/tasks")
async def run_operational_task(
    request_id: UUID,
    payload: TaskAction,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Run a narrow, read-only specialist check and persist its actual outcome."""
    require_demo(settings)
    async with session.begin():
        await require_org_admin(session, payload.organization_id, principal.user_id)
        request_result = await session.execute(
            text("""select id,case_id,status,deadline_at from public.hospitalos_requests
                    where id=:request_id and organization_id=:org"""),
            {"request_id": request_id, "org": payload.organization_id},
        )
        request = request_result.mappings().one_or_none()
        if request is None:
            raise ApiError("REQUEST_NOT_FOUND", "Receiving request was not found.", 404)
        case_result = await session.execute(
            text("""select origin,preference,requirement from public.hospitalos_cases
                    where id=:case_id"""), {"case_id": request["case_id"]},
        )
        case = case_result.mappings().one()
        detail: dict[str, Any] = {"kind": payload.kind}
        if payload.kind == "COORDINATION_FOLLOWUP":
            detail["observed_status"] = request["status"]
            detail["next_action"] = (
                "HUMAN_REVIEW" if request["status"] in ("PENDING", "HOLD_CONFLICT")
                else "NO_FOLLOWUP_REQUIRED"
            )
        else:
            if payload.kind == "RESOURCE_RECHECK":
                statement = text(FACILITY_SELECT)
            else:
                statement = text("""select slug,name,area,address,latitude,longitude,
                           cost_category,emergency_open,ed_bays_ready,icu_beds_ready,
                           ventilators_ready,ct_available,trauma_available,
                           pediatric_available,obstetric_available,receiving_enabled,
                           synthetic,verified_at from public.hospitalos_facilities
                           where synthetic=true and slug in
                             ('geeta-medicine','north-demo-hospital','east-demo-medical-centre')""")
            rows_result = await session.execute(statement)
            ranked = rank_facilities(
                [dict(row) for row in rows_result.mappings()],
                origin=case["origin"], preference=case["preference"],
                requirement=case["requirement"],
            )
            detail["candidates"] = [
                {"slug": item.slug, "recommended": item.recommended,
                 "reason_codes": item.reason_codes} for item in ranked
            ]
        await append_event(session, case_id=request["case_id"], request_id=request_id,
                           organization_id=payload.organization_id,
                           event_type="TASK_COMPLETED", actor_type="USER",
                           actor_id=principal.user_id, detail=detail)
        return await request_snapshot(session, request["case_id"])


@router.post("/requests/{request_id}/supervisor")
async def suggest_operational_task(
    request_id: UUID,
    payload: OrgAction,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_demo(settings)
    async with session.begin():
        await require_org_admin(session, payload.organization_id, principal.user_id)
        result = await session.execute(
            text("""select r.case_id,r.status,r.version,c.requirement
                    from public.hospitalos_requests r
                    join public.hospitalos_cases c on c.id=r.case_id
                    where r.id=:request_id and r.organization_id=:org"""),
            {"request_id": request_id, "org": payload.organization_id},
        )
        request = result.mappings().one_or_none()
        if request is None:
            raise ApiError("REQUEST_NOT_FOUND", "Receiving request was not found.", 404)
        events_result = await session.execute(
            text("""select event_type from public.hospitalos_events
                    where case_id=:case_id order by id desc limit 8"""),
            {"case_id": request["case_id"]},
        )
        event_types = [row[0] for row in events_result]
        observed_version = request["version"]
        case_id = request["case_id"]
        status = request["status"]
        requirement = request["requirement"]
    choice = await choose_task(
        settings, status=status, requirement=requirement,
        recent_events=list(reversed(event_types)),
    )
    async with session.begin():
        await require_org_admin(session, payload.organization_id, principal.user_id)
        current = await session.execute(
            text("""select version from public.hospitalos_requests
                    where id=:request_id and organization_id=:org for update"""),
            {"request_id": request_id, "org": payload.organization_id},
        )
        if current.scalar_one_or_none() != observed_version:
            raise ApiError(
                "REQUEST_VERSION_CONFLICT", "Request changed during supervisor review.", 409
            )
        await append_event(
            session, case_id=case_id, request_id=request_id,
            organization_id=payload.organization_id,
            event_type=("HUMAN_REVIEW_REQUESTED" if choice.kind == "HUMAN_REVIEW"
                        else "AGENT_TASK_CREATED"),
            actor_type="SYSTEM", detail={"kind": choice.kind, "source": "AI_SUPERVISOR"},
        )
        return await request_snapshot(session, case_id)
