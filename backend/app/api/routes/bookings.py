from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.session import get_db_session
from app.security.auth import Principal, get_current_principal

router = APIRouter()


class HoldRequest(BaseModel):
    organization_id: UUID
    patient_id: UUID
    contact_id: UUID
    notification_phone_id: UUID | None = None
    assignment_id: UUID
    session_id: UUID
    slot_id: UUID | None = None
    source: str = Field(pattern="^(STAFF|AI_VOICE|AI_TEXT|WALK_IN)$")
    idempotency_key: str = Field(min_length=16, max_length=255)
    request_hash: str = Field(min_length=32)
    consent_confirmed: bool
    consent_language: str = Field(pattern="^(en|hi|en-IN|hi-IN)$")
    consent_channel: str = Field(pattern="^(STAFF_UI|AI_TEXT|AI_VOICE)$")


class CancelRequest(BaseModel):
    organization_id: UUID
    expected_version: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class VisitStatusRequest(BaseModel):
    organization_id: UUID
    expected_version: int = Field(gt=0)
    queue_status: str = Field(pattern="^(CHECKED_IN|CALLED|IN_CONSULTATION|SERVED|SKIPPED)$")


class RescheduleRequest(BaseModel):
    organization_id: UUID
    expected_version: int = Field(gt=0)
    new_session_id: UUID
    new_slot_id: UUID | None = None


class BookingIntakeRequest(BaseModel):
    organization_id: UUID
    booker_name: str = Field(min_length=1, max_length=160)
    phone_e164: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    patient_name: str = Field(min_length=1, max_length=160)
    relationship: Literal["SELF", "MOTHER", "FATHER", "SPOUSE", "CHILD", "OTHER"] = "SELF"


class PaymentConfirmRequest(BaseModel):
    payment_method: str = Field(pattern="^(CASH|UPI|CARD|ONLINE)$")


async def require_booking_staff(
    session: AsyncSession, organization_id: UUID, user_id: UUID
) -> None:
    membership = await session.execute(
        text(
            """select 1 from public.organization_users
            where organization_id=:org and auth_user_id=:user and active
              and role in ('ORG_ADMIN', 'RECEPTIONIST')"""
        ),
        {"org": organization_id, "user": user_id},
    )
    if membership.first() is None:
        raise ApiError(
            code="FORBIDDEN", message="Booking staff access is required.", status_code=403
        )


@router.get("/booking-options")
async def booking_options(
    organization_id: UUID,
    from_at: datetime = Query(alias="from"),
    to_at: datetime = Query(alias="to"),
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> list[dict[str, object]]:
    if to_at <= from_at:
        raise ApiError(
            code="INVALID_DATE_RANGE", message="The end must follow the start.", status_code=422
        )
    await require_booking_staff(session, organization_id, principal.user_id)
    sessions = await session.execute(
        text(
            """
            select s.id, s.assignment_id, s.booking_mode, s.starts_at, s.ends_at, s.max_patients,
                   s.next_token, assignment.display_name as doctor_name, location.name as location_name,
                   count(appointment.id) filter (
                     where appointment.status in ('PAYMENT_PENDING','CONFIRMED','COMPLETED','NO_SHOW')
                   ) as occupied
            from public.appointment_sessions s
            join public.doctor_assignments assignment
              on assignment.organization_id=s.organization_id and assignment.id=s.assignment_id
            join public.locations location
              on location.organization_id=assignment.organization_id and location.id=assignment.location_id
            left join public.appointments appointment
              on appointment.organization_id=s.organization_id and appointment.session_id=s.id
            where s.organization_id=:org and s.starts_at >= :from_at and s.starts_at < :to_at
              and s.status in ('SCHEDULED','OPEN')
            group by s.id, assignment.display_name, location.name
            order by s.starts_at
            """
        ),
        {"org": organization_id, "from_at": from_at, "to_at": to_at},
    )
    options: list[dict[str, object]] = []
    for row in sessions.mappings():
        option = dict(row)
        option["slots"] = []
        if row["booking_mode"] == "EXACT_TIME":
            slots = await session.execute(
                text(
                    """
                    select slot.id, slot.starts_at, slot.ends_at
                    from public.appointment_slots slot
                    where slot.organization_id=:org and slot.session_id=:session and slot.bookable
                      and not exists (
                        select 1 from public.appointments appointment
                        where appointment.organization_id=slot.organization_id and appointment.slot_id=slot.id
                          and appointment.status in ('PAYMENT_PENDING','CONFIRMED','COMPLETED','NO_SHOW')
                      )
                    order by slot.starts_at
                    """
                ),
                {"org": organization_id, "session": row["id"]},
            )
            option["slots"] = [dict(slot) for slot in slots.mappings()]
        options.append(option)
    return options


@router.post("/booking-intake")
async def create_booking_intake(
    payload: BookingIntakeRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        await require_booking_staff(session, payload.organization_id, principal.user_id)
        # Serialize identity resolution for this tenant/mobile pair. The partial unique
        # index remains the final database guard, while this prevents concurrent calls
        # from turning an ordinary retry into a uniqueness error.
        await session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:identity_key, 0))"),
            {"identity_key": f"{payload.organization_id}:{payload.phone_e164}"},
        )
        existing_phone = await session.execute(
            text(
                """
                select id, contact_id from public.contact_phones
                where organization_id=:org and phone_e164=:phone and status='ACTIVE'
                """
            ),
            {"org": payload.organization_id, "phone": payload.phone_e164},
        )
        phone_row = existing_phone.mappings().one_or_none()
        if phone_row is None:
            contact = await session.execute(
                text(
                    """
                    insert into public.contacts (organization_id, display_name, name_source)
                    values (:org, :name, 'STAFF_ENTERED') returning id
                    """
                ),
                {"org": payload.organization_id, "name": payload.booker_name.strip()},
            )
            contact_id = contact.scalar_one()
            phone = await session.execute(
                text(
                    """
                    insert into public.contact_phones (organization_id, contact_id, phone_e164)
                    values (:org, :contact, :phone) returning id
                    """
                ),
                {
                    "org": payload.organization_id,
                    "contact": contact_id,
                    "phone": payload.phone_e164,
                },
            )
            phone_id = phone.scalar_one()
            contact_created = True
        else:
            contact_id = phone_row["contact_id"]
            phone_id = phone_row["id"]
            contact_created = False

        existing_patient = await session.execute(
            text(
                """
                select patient.id, link.relationship
                from public.patients patient
                join public.patient_contacts link
                  on link.organization_id=patient.organization_id and link.patient_id=patient.id
                where patient.organization_id=:org and link.contact_id=:contact
                  and link.relationship_status='RECORDED' and patient.status='ACTIVE'
                  and lower(patient.display_name)=lower(:name)
                order by patient.created_at limit 1
                """
            ),
            {
                "org": payload.organization_id,
                "contact": contact_id,
                "name": payload.patient_name.strip(),
            },
        )
        patient_row = existing_patient.mappings().one_or_none()
        patient_id = patient_row["id"] if patient_row else None
        if patient_row and patient_row["relationship"] != payload.relationship:
            raise ApiError(
                code="RELATIONSHIP_CONFLICT",
                message=(
                    "This patient is already linked to this mobile as "
                    f"{str(patient_row['relationship']).lower()}. Review the family record "
                    "before changing the relationship."
                ),
                status_code=409,
            )

        if payload.relationship == "SELF" and patient_id is None:
            existing_self = await session.execute(
                text(
                    """
                    select patient.display_name
                    from public.patient_contacts link
                    join public.patients patient
                      on patient.organization_id=link.organization_id
                     and patient.id=link.patient_id
                    where link.organization_id=:org and link.contact_id=:contact
                      and link.relationship_status='RECORDED'
                      and link.relationship='SELF' and patient.status='ACTIVE'
                    limit 1
                    """
                ),
                {"org": payload.organization_id, "contact": contact_id},
            )
            self_name = existing_self.scalar_one_or_none()
            if self_name is not None:
                raise ApiError(
                    code="SELF_PATIENT_CONFLICT",
                    message=(
                        f"This mobile is already linked to {self_name} as self. "
                        "Choose the correct family relationship or update the existing record."
                    ),
                    status_code=409,
                )
        patient_created = patient_id is None
        if patient_created:
            patient = await session.execute(
                text(
                    """
                    insert into public.patients (organization_id, display_name)
                    values (:org, :name) returning id
                    """
                ),
                {"org": payload.organization_id, "name": payload.patient_name.strip()},
            )
            patient_id = patient.scalar_one()
            await session.execute(
                text(
                    """
                    insert into public.patient_contacts
                    (organization_id, patient_id, contact_id, relationship, recorded_by_auth_user_id)
                    values (:org, :patient, :contact, :relationship, :user)
                    """
                ),
                {
                    "org": payload.organization_id,
                    "patient": patient_id,
                    "contact": contact_id,
                    "relationship": payload.relationship.strip(),
                    "user": principal.user_id,
                },
            )
    return {
        "contact_id": contact_id,
        "phone_id": phone_id,
        "patient_id": patient_id,
        "contact_created": contact_created,
        "patient_created": patient_created,
    }


@router.get("/appointments")
async def list_appointments(
    organization_id: UUID,
    query: str = Query(default="", max_length=160),
    limit: int = Query(default=250, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    assignment_id: UUID | None = None,
    status: str | None = Query(
        default=None, pattern="^(PAYMENT_PENDING|CONFIRMED|CANCELLED|COMPLETED|NO_SHOW)$"
    ),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> list[dict[str, object]]:
    await require_booking_staff(session, organization_id, principal.user_id)
    normalized_query = query.strip()
    result = await session.execute(
        text(
            """
            select appointment.id, appointment.organization_id, appointment.booking_reference,
                   appointment.status, appointment.queue_status,
                   appointment.version, appointment.token_number, appointment.cancellation_reason,
                   appointment.fee_minor, appointment.currency, appointment.source,
                   patient.display_name as patient_name,
                   contact.display_name as booker_name, phone.phone_e164,
                   appointment_session.booking_mode,
                   coalesce(slot.starts_at, appointment_session.starts_at) as scheduled_at,
                   appointment_session.ends_at as session_ends_at,
                   assignment.display_name as doctor_name, assignment.id as assignment_id,
                   department.name as department_name, location.name as location_name,
                   payment.payment_method, payment.status as payment_status
            from public.appointments appointment
            join public.patients patient
              on patient.organization_id=appointment.organization_id
             and patient.id=appointment.patient_id
            left join public.contacts contact
              on contact.organization_id=appointment.organization_id
             and contact.id=appointment.booked_by_contact_id
            left join public.contact_phones phone
              on phone.organization_id=appointment.organization_id
             and phone.id=appointment.notification_contact_phone_id
            join public.appointment_sessions appointment_session
              on appointment_session.organization_id=appointment.organization_id
             and appointment_session.id=appointment.session_id
            left join public.appointment_slots slot
              on slot.organization_id=appointment.organization_id
             and slot.id=appointment.slot_id
            join public.doctor_assignments assignment
              on assignment.organization_id=appointment.organization_id
             and assignment.id=appointment.assignment_id
            join public.locations location
              on location.organization_id=assignment.organization_id
             and location.id=assignment.location_id
            join public.departments department
              on department.organization_id=assignment.organization_id
             and department.id=assignment.department_id
            left join lateral (
              select attempt.payment_method, attempt.status
              from public.payment_attempts attempt
              where attempt.organization_id=appointment.organization_id
                and attempt.appointment_id=appointment.id
              order by attempt.created_at desc
              limit 1
            ) payment on true
            where appointment.organization_id=:org
              and (cast(:assignment_id as uuid) is null
                   or appointment.assignment_id=cast(:assignment_id as uuid))
              and (cast(:status as text) is null
                   or appointment.status=cast(:status as text))
              and (cast(:from_at as timestamptz) is null
                   or coalesce(slot.starts_at, appointment_session.starts_at)
                      >= cast(:from_at as timestamptz))
              and (cast(:to_at as timestamptz) is null
                   or coalesce(slot.starts_at, appointment_session.starts_at)
                      < cast(:to_at as timestamptz))
              and (
                :query = ''
                or appointment.booking_reference ilike :search
                or patient.display_name ilike :search
                or contact.display_name ilike :search
                or phone.phone_e164 ilike :search
              )
            order by appointment.created_at desc, appointment.id desc
            limit :limit offset :offset
            """
        ),
        {
            "org": organization_id,
            "limit": limit,
            "offset": offset,
            "assignment_id": assignment_id,
            "status": status,
            "from_at": from_at,
            "to_at": to_at,
            "query": normalized_query,
            "search": f"%{normalized_query}%",
        },
    )
    return [dict(row) for row in result.mappings()]


@router.post("/appointments/{appointment_id}/visit-status")
async def update_visit_status(
    appointment_id: UUID,
    payload: VisitStatusRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    """Advance a confirmed visit through the reception queue with optimistic locking."""
    status_for_queue = {
        "CHECKED_IN": "CONFIRMED",
        "CALLED": "CONFIRMED",
        "IN_CONSULTATION": "CONFIRMED",
        "SERVED": "COMPLETED",
        "SKIPPED": "NO_SHOW",
    }
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        await require_booking_staff(session, payload.organization_id, principal.user_id)
        result = await session.execute(
            text(
                """update public.appointments
                   set queue_status=:queue_status, status=:status, version=version+1
                   where organization_id=:org and id=:appointment and version=:version
                     and status='CONFIRMED'
                   returning id, booking_reference, status, queue_status, version"""
            ),
            {
                "queue_status": payload.queue_status,
                "status": status_for_queue[payload.queue_status],
                "org": payload.organization_id,
                "appointment": appointment_id,
                "version": payload.expected_version,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(
                code="VISIT_STATE_CONFLICT",
                message="This visit was already updated. Refresh the appointment list.",
                status_code=409,
            )
        return dict(row)


@router.post("/appointments/holds")
async def create_hold(
    payload: HoldRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        result = await session.execute(
            text("""
            select * from public.create_simulated_appointment_hold(
              :org,:patient,:contact,:phone,:assignment,:appointment_session,:slot,:source,:key,:hash,
              :consent_confirmed,:consent_language,:consent_channel)
        """),
            {
                "org": payload.organization_id,
                "patient": payload.patient_id,
                "contact": payload.contact_id,
                "phone": payload.notification_phone_id,
                "assignment": payload.assignment_id,
                "appointment_session": payload.session_id,
                "slot": payload.slot_id,
                "source": payload.source,
                "key": payload.idempotency_key,
                "hash": payload.request_hash,
                "consent_confirmed": payload.consent_confirmed,
                "consent_language": payload.consent_language,
                "consent_channel": payload.consent_channel,
            },
        )
        return dict(result.mappings().one())


@router.post("/appointments/{appointment_id}/confirm")
async def confirm_hold(
    appointment_id: UUID,
    organization_id: UUID,
    payload: PaymentConfirmRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        appointment_source = (
            await session.execute(
                text(
                    """select source from public.appointments
                       where organization_id=:org and id=:appointment"""
                ),
                {"org": organization_id, "appointment": appointment_id},
            )
        ).scalar_one_or_none()
        if appointment_source is None:
            raise ApiError(code="NOT_FOUND", message="Appointment was not found.", status_code=404)
        manual_methods = {"CASH", "UPI", "CARD"}
        ai_methods = {"ONLINE", "UPI"}
        allowed_methods = (
            manual_methods if appointment_source in {"STAFF", "WALK_IN"} else ai_methods
        )
        if payload.payment_method not in allowed_methods:
            raise ApiError(
                code="INVALID_PAYMENT_METHOD",
                message=(
                    "Manual bookings support Cash, UPI, or Card."
                    if appointment_source in {"STAFF", "WALK_IN"}
                    else "AI bookings support Online or UPI."
                ),
                status_code=422,
            )
        await session.execute(
            text(
                """update public.payment_attempts
                   set payment_method=:method,
                       mode=case when :method='CASH' then 'PAY_AT_CLINIC' else 'SIMULATED' end
                   where organization_id=:org and appointment_id=:appointment
                     and status='SIMULATION_PENDING'"""
            ),
            {
                "method": payload.payment_method,
                "org": organization_id,
                "appointment": appointment_id,
            },
        )
        result = await session.execute(
            text("select * from public.confirm_simulated_appointment(:org,:appointment)"),
            {"org": organization_id, "appointment": appointment_id},
        )
        confirmed = dict(result.mappings().one())
        if payload.payment_method == "CASH":
            await session.execute(
                text(
                    """update public.payment_attempts set status='DUE_AT_CLINIC'
                       where organization_id=:org and appointment_id=:appointment
                         and payment_method='CASH'"""
                ),
                {"org": organization_id, "appointment": appointment_id},
            )
        confirmed["payment_method"] = payload.payment_method
        confirmed["payment_status"] = (
            "DUE_AT_CLINIC" if payload.payment_method == "CASH" else "SIMULATED_SUCCESS"
        )
        return confirmed


@router.post("/appointments/{appointment_id}/cancel")
async def cancel(
    appointment_id: UUID,
    payload: CancelRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        result = await session.execute(
            text("select * from public.cancel_appointment(:org,:appointment,:version,:reason)"),
            {
                "org": payload.organization_id,
                "appointment": appointment_id,
                "version": payload.expected_version,
                "reason": payload.reason,
            },
        )
        return dict(result.mappings().one())


@router.post("/appointments/{appointment_id}/reschedule")
async def reschedule(
    appointment_id: UUID,
    payload: RescheduleRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        result = await session.execute(
            text(
                "select * from public.reschedule_appointment(:org,:appointment,:version,:new_session,:new_slot)"
            ),
            {
                "org": payload.organization_id,
                "appointment": appointment_id,
                "version": payload.expected_version,
                "new_session": payload.new_session_id,
                "new_slot": payload.new_slot_id,
            },
        )
        return dict(result.mappings().one())
