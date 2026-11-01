# ruff: noqa: E501
from datetime import date, time, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.session import get_db_session
from app.security.auth import Principal, get_current_principal
from app.services.schedule_generation import rebuild_assignment_sessions

router = APIRouter()


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    organization_type: str = Field(pattern="^(CLINIC|HOSPITAL)$")


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(default="", max_length=500)


class LocationUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(default="", max_length=500)


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class DepartmentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    active: bool


class AssignmentCreate(BaseModel):
    doctor_name: str = Field(min_length=1, max_length=160)
    qualifications: list[str] = Field(default_factory=list, max_length=10)
    location_id: UUID
    department_id: UUID
    display_name: str = Field(min_length=1, max_length=160)
    fee_minor: int = Field(default=0, ge=0)
    currency: str = Field(default="INR", pattern="^[A-Z]{3}$")


class ScheduleRuleCreate(BaseModel):
    assignment_id: UUID
    weekday: int = Field(ge=0, le=6)
    local_starts_at: time
    local_ends_at: time
    booking_mode: str = Field(pattern="^SESSION_TOKEN$")
    slot_minutes: int | None = Field(default=None, ge=5, le=240)
    max_patients: int | None = Field(default=None, ge=1, le=1000)
    effective_from: date
    effective_until: date | None = None
    booking_cutoff_minutes: int = Field(default=30, ge=0, le=10080)


class ActiveUpdate(BaseModel):
    active: bool


class ScheduleExceptionCreate(BaseModel):
    assignment_id: UUID
    local_date: date
    exception_type: str = Field(pattern="^(CLOSED|REPLACEMENT_HOURS)$")
    local_starts_at: time | None = None
    local_ends_at: time | None = None
    reason: str = Field(default="", max_length=500)


class AssignmentUpdate(ActiveUpdate):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    fee_minor: int | None = Field(default=None, ge=0)
    location_id: UUID | None = None
    department_id: UUID | None = None


class ScheduleRuleUpdate(BaseModel):
    weekday: int = Field(ge=0, le=6)
    local_starts_at: time
    local_ends_at: time
    booking_mode: str = Field(pattern="^SESSION_TOKEN$")
    slot_minutes: int | None = Field(default=None, ge=5, le=240)
    max_patients: int | None = Field(default=None, ge=1, le=1000)
    active: bool


async def require_org_admin(session: AsyncSession, organization_id: UUID, user_id: UUID) -> None:
    membership = await session.execute(
        text(
            """select 1 from public.organization_users
               where organization_id=:org and auth_user_id=:user and active
                 and role='ORG_ADMIN'"""
        ),
        {"org": organization_id, "user": user_id},
    )
    if membership.first() is None:
        raise ApiError(
            code="FORBIDDEN",
            message="Organization administrator access is required.",
            status_code=403,
        )


async def require_org_member(session: AsyncSession, organization_id: UUID, user_id: UUID) -> None:
    membership = await session.execute(
        text(
            """select 1 from public.organization_users
               where organization_id=:org and auth_user_id=:user and active"""
        ),
        {"org": organization_id, "user": user_id},
    )
    if membership.first() is None:
        raise ApiError(
            code="FORBIDDEN",
            message="Organization membership is required.",
            status_code=403,
        )


async def set_actor(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        text("select set_config('request.jwt.claim.sub', :user, true)"), {"user": str(user_id)}
    )


async def ensure_schedule_does_not_overlap(
    session: AsyncSession,
    organization_id: UUID,
    assignment_id: UUID,
    weekday: int,
    local_starts_at: time,
    local_ends_at: time,
    effective_from: date,
    effective_until: date | None,
    exclude_rule_id: UUID | None = None,
) -> None:
    overlap = await session.execute(
        text(
            """select 1
               from public.schedule_rules existing
               join public.doctor_assignments existing_assignment
                 on existing_assignment.organization_id=existing.organization_id
                and existing_assignment.id=existing.assignment_id
               join public.doctor_assignments requested_assignment
                 on requested_assignment.organization_id=existing.organization_id
                and requested_assignment.id=:assignment
               where existing.organization_id=:org
                 and existing.active
                 and existing_assignment.doctor_id=requested_assignment.doctor_id
                 and existing.weekday=:weekday
                 and existing.local_starts_at < :ends
                 and existing.local_ends_at > :starts
                 and existing.effective_from <= coalesce(cast(:effective_until as date), 'infinity'::date)
                 and coalesce(existing.effective_until, 'infinity'::date) >= :effective_from
                 and (cast(:exclude_rule as uuid) is null
                      or existing.id <> cast(:exclude_rule as uuid))
               limit 1"""
        ),
        {
            "org": organization_id,
            "assignment": assignment_id,
            "weekday": weekday,
            "starts": local_starts_at,
            "ends": local_ends_at,
            "effective_from": effective_from,
            "effective_until": effective_until,
            "exclude_rule": exclude_rule_id,
        },
    )
    if overlap.first() is not None:
        raise ApiError(
            code="SCHEDULE_OVERLAP",
            message="This doctor already has overlapping weekly hours for that date range.",
            status_code=409,
        )


@router.get("")
async def get_configuration(
    organization_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    await require_org_member(session, organization_id, principal.user_id)
    organization = await session.execute(
        text(
            "select id, name, organization_type, timezone, status from public.organizations where id=:org"
        ),
        {"org": organization_id},
    )
    org = organization.mappings().one_or_none()
    if org is None:
        raise ApiError(code="NOT_FOUND", message="Organization was not found.", status_code=404)
    locations = await session.execute(
        text(
            "select id, name, address, timezone, active from public.locations where organization_id=:org order by name"
        ),
        {"org": organization_id},
    )
    departments = await session.execute(
        text(
            "select id, name, active from public.departments where organization_id=:org order by name"
        ),
        {"org": organization_id},
    )
    assignments = await session.execute(
        text(
            """select a.id, a.display_name, a.fee_minor, a.currency, a.active,
                      d.id as doctor_id, d.canonical_name as doctor_name, d.qualifications,
                      a.location_id, a.department_id,
                      l.name as location_name, dept.name as department_name
               from public.doctor_assignments a
               join public.doctors d on d.id=a.doctor_id
               join public.locations l on l.organization_id=a.organization_id and l.id=a.location_id
               join public.departments dept on dept.organization_id=a.organization_id and dept.id=a.department_id
               where a.organization_id=:org order by a.display_name"""
        ),
        {"org": organization_id},
    )
    rules = await session.execute(
        text(
            """select id, assignment_id, weekday, local_starts_at, local_ends_at, booking_mode,
                      slot_minutes, max_patients, effective_from, effective_until, active
               from public.schedule_rules where organization_id=:org order by weekday, local_starts_at"""
        ),
        {"org": organization_id},
    )
    exceptions = await session.execute(
        text(
            """select id, assignment_id, local_date, exception_type, local_starts_at,
                      local_ends_at, reason, active
               from public.schedule_exceptions
               where organization_id=:org and active order by local_date"""
        ),
        {"org": organization_id},
    )
    return {
        "organization": dict(org),
        "locations": [dict(row) for row in locations.mappings()],
        "departments": [dict(row) for row in departments.mappings()],
        "assignments": [dict(row) for row in assignments.mappings()],
        "schedule_rules": [dict(row) for row in rules.mappings()],
        "schedule_exceptions": [dict(row) for row in exceptions.mappings()],
    }


@router.patch("/organization")
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        result = await session.execute(
            text(
                """update public.organizations set name=:name, organization_type=:kind where id=:org returning id, name, organization_type, timezone, status"""
            ),
            {
                "name": payload.name.strip(),
                "kind": payload.organization_type,
                "org": organization_id,
            },
        )
        return dict(result.mappings().one())


@router.post("/locations", status_code=201)
async def create_location(
    organization_id: UUID,
    payload: LocationCreate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        timezone = (
            await session.execute(
                text("select timezone from public.organizations where id=:org"),
                {"org": organization_id},
            )
        ).scalar_one()
        try:
            result = await session.execute(
                text(
                    """insert into public.locations (organization_id, name, address, timezone) values (:org,:name,:address,:timezone) returning id,name,address,timezone,active"""
                ),
                {
                    "org": organization_id,
                    "name": payload.name.strip(),
                    "address": payload.address.strip(),
                    "timezone": timezone,
                },
            )
        except IntegrityError as exc:
            raise ApiError(
                code="DUPLICATE_LOCATION",
                message="A location with that name already exists.",
                status_code=409,
            ) from exc
        return dict(result.mappings().one())


@router.post("/departments", status_code=201)
async def create_department(
    organization_id: UUID,
    payload: DepartmentCreate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        try:
            result = await session.execute(
                text(
                    "insert into public.departments (organization_id, name) values (:org,:name) returning id,name,active"
                ),
                {"org": organization_id, "name": payload.name.strip()},
            )
        except IntegrityError as exc:
            raise ApiError(
                code="DUPLICATE_DEPARTMENT",
                message="A department with that name already exists.",
                status_code=409,
            ) from exc
        return dict(result.mappings().one())


@router.patch("/locations/{location_id}")
async def update_location(
    location_id: UUID,
    organization_id: UUID,
    payload: LocationUpdate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        result = await session.execute(
            text(
                """update public.locations set name=:name, address=:address
                   where organization_id=:org and id=:location
                   returning id, name, address, timezone, active"""
            ),
            {
                "name": payload.name.strip(),
                "address": payload.address.strip(),
                "org": organization_id,
                "location": location_id,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(code="NOT_FOUND", message="Clinic site was not found.", status_code=404)
        return dict(row)


@router.post("/assignments", status_code=201)
async def create_assignment(
    organization_id: UUID,
    payload: AssignmentCreate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        doctor = await session.execute(
            text(
                "insert into public.doctors (canonical_name, qualifications) values (:name,:qualifications) returning id,canonical_name"
            ),
            {"name": payload.doctor_name.strip(), "qualifications": payload.qualifications},
        )
        doctor_row = doctor.mappings().one()
        try:
            assignment = await session.execute(
                text(
                    """insert into public.doctor_assignments (organization_id, doctor_id, location_id, department_id, display_name, fee_minor, currency) values (:org,:doctor,:location,:department,:display,:fee,:currency) returning id,display_name,fee_minor,currency,active"""
                ),
                {
                    "org": organization_id,
                    "doctor": doctor_row["id"],
                    "location": payload.location_id,
                    "department": payload.department_id,
                    "display": payload.display_name.strip(),
                    "fee": payload.fee_minor,
                    "currency": payload.currency,
                },
            )
        except IntegrityError as exc:
            raise ApiError(
                code="INVALID_ASSIGNMENT",
                message="Choose an active clinic location and department; this doctor assignment must be unique.",
                status_code=422,
            ) from exc
        result = dict(assignment.mappings().one())
        result.update({"doctor_id": doctor_row["id"], "doctor_name": doctor_row["canonical_name"]})
        return result


@router.post("/schedule-rules", status_code=201)
async def create_schedule_rule(
    organization_id: UUID,
    payload: ScheduleRuleCreate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    if payload.local_ends_at <= payload.local_starts_at:
        raise ApiError(
            code="INVALID_TIME_WINDOW",
            message="The schedule end time must be after the start time.",
            status_code=422,
        )
    if payload.max_patients is None or payload.slot_minutes is not None:
        raise ApiError(
            code="INVALID_BOOKING_MODE",
            message="Availability windows need a patient capacity.",
            status_code=422,
        )
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        await ensure_schedule_does_not_overlap(
            session,
            organization_id,
            payload.assignment_id,
            payload.weekday,
            payload.local_starts_at,
            payload.local_ends_at,
            payload.effective_from,
            payload.effective_until,
        )
        try:
            result = await session.execute(
                text(
                    """insert into public.schedule_rules (organization_id,assignment_id,weekday,local_starts_at,local_ends_at,booking_mode,slot_minutes,max_patients,effective_from,effective_until,booking_cutoff_minutes) values (:org,:assignment,:weekday,:starts,:ends,:mode,:slot_minutes,:max_patients,:effective_from,:effective_until,:cutoff) returning id,assignment_id,weekday,local_starts_at,local_ends_at,booking_mode,slot_minutes,max_patients,effective_from,effective_until,active"""
                ),
                {
                    "org": organization_id,
                    "assignment": payload.assignment_id,
                    "weekday": payload.weekday,
                    "starts": payload.local_starts_at,
                    "ends": payload.local_ends_at,
                    "mode": payload.booking_mode,
                    "slot_minutes": payload.slot_minutes,
                    "max_patients": payload.max_patients,
                    "effective_from": payload.effective_from,
                    "effective_until": payload.effective_until,
                    "cutoff": payload.booking_cutoff_minutes,
                },
            )
        except IntegrityError as exc:
            raise ApiError(
                code="INVALID_SCHEDULE",
                message="The selected doctor assignment is not available for this organization.",
                status_code=422,
            ) from exc
        created = dict(result.mappings().one())
        await rebuild_assignment_sessions(
            session,
            str(organization_id),
            str(payload.assignment_id),
            date.today() + timedelta(days=14),
        )
    return created


@router.post("/schedule-exceptions", status_code=201)
async def create_schedule_exception(
    organization_id: UUID,
    payload: ScheduleExceptionCreate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    replacement = payload.exception_type == "REPLACEMENT_HOURS"
    has_window = payload.local_starts_at is not None and payload.local_ends_at is not None
    if replacement != has_window:
        raise ApiError(
            code="INVALID_EXCEPTION",
            message="Replacement hours require start and end times.",
            status_code=422,
        )
    if (
        replacement
        and payload.local_starts_at is not None
        and payload.local_ends_at is not None
        and payload.local_ends_at <= payload.local_starts_at
    ):
        raise ApiError(
            code="INVALID_TIME_WINDOW",
            message="The end time must follow the start time.",
            status_code=422,
        )
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        try:
            result = await session.execute(
                text(
                    """insert into public.schedule_exceptions
                       (organization_id, assignment_id, local_date, exception_type,
                        local_starts_at, local_ends_at, reason)
                       values (:org,:assignment,:local_date,:kind,:starts,:ends,:reason)
                       returning id, assignment_id, local_date, exception_type,
                                 local_starts_at, local_ends_at, reason, active"""
                ),
                {
                    "org": organization_id,
                    "assignment": payload.assignment_id,
                    "local_date": payload.local_date,
                    "kind": payload.exception_type,
                    "starts": payload.local_starts_at,
                    "ends": payload.local_ends_at,
                    "reason": payload.reason.strip(),
                },
            )
        except IntegrityError as exc:
            raise ApiError(
                code="DUPLICATE_EXCEPTION",
                message="That doctor already has an exception for this date.",
                status_code=409,
            ) from exc
        created = dict(result.mappings().one())
        await session.execute(
            text(
                """update public.appointment_sessions
                   set status='CLOSED'
                   where organization_id=:org and assignment_id=:assignment
                     and (starts_at at time zone timezone)::date=:local_date
                     and status in ('SCHEDULED','OPEN')"""
            ),
            {
                "org": organization_id,
                "assignment": payload.assignment_id,
                "local_date": payload.local_date,
            },
        )
        await rebuild_assignment_sessions(
            session,
            str(organization_id),
            str(payload.assignment_id),
            date.today() + timedelta(days=14),
        )
    return created


@router.patch("/departments/{department_id}")
async def update_department(
    department_id: UUID,
    organization_id: UUID,
    payload: DepartmentUpdate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        result = await session.execute(
            text(
                """update public.departments set active=:active, name=:name
                   where organization_id=:org and id=:department
                   returning id, name, active"""
            ),
            {
                "active": payload.active,
                "name": payload.name.strip(),
                "org": organization_id,
                "department": department_id,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(code="NOT_FOUND", message="Department was not found.", status_code=404)
        return dict(row)


@router.patch("/assignments/{assignment_id}")
async def update_assignment(
    assignment_id: UUID,
    organization_id: UUID,
    payload: AssignmentUpdate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        result = await session.execute(
            text(
                """update public.doctor_assignments
                   set active=:active,
                       display_name=coalesce(:display_name, display_name),
                       fee_minor=coalesce(:fee_minor, fee_minor),
                       location_id=coalesce(cast(:location_id as uuid), location_id),
                       department_id=coalesce(cast(:department_id as uuid), department_id)
                   where organization_id=:org and id=:assignment
                   returning id, display_name, fee_minor, currency, active"""
            ),
            {
                "active": payload.active,
                "display_name": payload.display_name.strip() if payload.display_name else None,
                "fee_minor": payload.fee_minor,
                "location_id": payload.location_id,
                "department_id": payload.department_id,
                "org": organization_id,
                "assignment": assignment_id,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(
                code="NOT_FOUND", message="Doctor assignment was not found.", status_code=404
            )
        updated = dict(row)
        if not payload.active:
            await session.execute(
                text(
                    """update public.appointment_sessions set status='CLOSED'
                       where organization_id=:org and assignment_id=:assignment
                         and starts_at >= now() and status in ('SCHEDULED','OPEN')"""
                ),
                {"org": organization_id, "assignment": assignment_id},
            )
        await rebuild_assignment_sessions(
            session, str(organization_id), str(assignment_id), date.today() + timedelta(days=14)
        )
    return updated


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: UUID,
    organization_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    """Permanently remove an unbooked doctor assignment and its schedule."""
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        assignment = (
            await session.execute(
                text(
                    """select id, doctor_id, display_name from public.doctor_assignments
                       where organization_id=:org and id=:assignment"""
                ),
                {"org": organization_id, "assignment": assignment_id},
            )
        ).mappings().one_or_none()
        if assignment is None:
            raise ApiError(
                code="NOT_FOUND", message="Doctor assignment was not found.", status_code=404
            )
        appointment_count = (
            await session.execute(
                text(
                    """select count(*) from public.appointments
                       where organization_id=:org and assignment_id=:assignment"""
                ),
                {"org": organization_id, "assignment": assignment_id},
            )
        ).scalar_one()
        if appointment_count:
            raise ApiError(
                code="DOCTOR_HAS_APPOINTMENTS",
                message=(
                    "This doctor has appointment history and cannot be deleted. "
                    "Pause bookings instead."
                ),
                status_code=409,
            )
        for statement in (
            "delete from public.schedule_exceptions where organization_id=:org and assignment_id=:assignment",
            "delete from public.schedule_rules where organization_id=:org and assignment_id=:assignment",
            "delete from public.appointment_slots where organization_id=:org and assignment_id=:assignment",
            "delete from public.appointment_sessions where organization_id=:org and assignment_id=:assignment",
            "delete from public.doctor_assignments where organization_id=:org and id=:assignment",
        ):
            await session.execute(
                text(statement), {"org": organization_id, "assignment": assignment_id}
            )
        await session.execute(
            text(
                """delete from public.doctors doctor
                   where doctor.id=:doctor
                     and not exists (
                         select 1 from public.doctor_assignments assignment
                         where assignment.doctor_id=doctor.id
                     )"""
            ),
            {"doctor": assignment["doctor_id"]},
        )
    return {
        "deleted": True,
        "assignment_id": str(assignment_id),
        "doctor_name": assignment["display_name"],
    }


@router.patch("/schedule-rules/{rule_id}")
async def update_schedule_rule(
    rule_id: UUID,
    organization_id: UUID,
    payload: ScheduleRuleUpdate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    if payload.local_ends_at <= payload.local_starts_at:
        raise ApiError(
            code="INVALID_TIME_WINDOW",
            message="The schedule end time must be after the start time.",
            status_code=422,
        )
    if payload.max_patients is None or payload.slot_minutes is not None:
        raise ApiError(
            code="INVALID_BOOKING_MODE",
            message="Availability windows need a patient capacity.",
            status_code=422,
        )
    async with session.begin():
        await set_actor(session, principal.user_id)
        await require_org_admin(session, organization_id, principal.user_id)
        existing_rule = (
            await session.execute(
                text(
                    """select assignment_id, effective_from, effective_until
                       from public.schedule_rules
                       where organization_id=:org and id=:rule"""
                ),
                {"org": organization_id, "rule": rule_id},
            )
        ).mappings().one_or_none()
        if existing_rule is None:
            raise ApiError(
                code="NOT_FOUND", message="Schedule rule was not found.", status_code=404
            )
        if payload.active:
            await ensure_schedule_does_not_overlap(
                session,
                organization_id,
                existing_rule["assignment_id"],
                payload.weekday,
                payload.local_starts_at,
                payload.local_ends_at,
                existing_rule["effective_from"],
                existing_rule["effective_until"],
                rule_id,
            )
        result = await session.execute(
            text(
                """update public.schedule_rules
                   set active=:active, weekday=:weekday, local_starts_at=:starts,
                       local_ends_at=:ends, booking_mode=:mode,
                       slot_minutes=:slot_minutes, max_patients=:max_patients
                   where organization_id=:org and id=:rule
                   returning id, assignment_id, weekday, local_starts_at, local_ends_at,
                             booking_mode, slot_minutes, max_patients, active"""
            ),
            {
                "active": payload.active,
                "weekday": payload.weekday,
                "starts": payload.local_starts_at,
                "ends": payload.local_ends_at,
                "mode": payload.booking_mode,
                "slot_minutes": payload.slot_minutes,
                "max_patients": payload.max_patients,
                "org": organization_id,
                "rule": rule_id,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(
                code="NOT_FOUND", message="Schedule rule was not found.", status_code=404
            )
        updated = dict(row)
        await rebuild_assignment_sessions(
            session,
            str(organization_id),
            str(updated["assignment_id"]),
            date.today() + timedelta(days=14),
        )
    return updated
