from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.session import get_db_session
from app.security.auth import Principal, get_current_principal

router = APIRouter()

RELATIONSHIPS = ("SELF", "MOTHER", "FATHER", "SPOUSE", "CHILD", "OTHER")


class PatientUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    disambiguation: str = Field(default="", max_length=160)
    status: str = Field(pattern="^(ACTIVE|ARCHIVED)$")


class PatientContactUpdate(BaseModel):
    contact_name: str = Field(min_length=1, max_length=160)
    phone_e164: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    relationship: str = Field(pattern="^(SELF|MOTHER|FATHER|SPOUSE|CHILD|OTHER)$")


async def require_booking_staff(
    session: AsyncSession, organization_id: UUID, user_id: UUID
) -> None:
    allowed = await session.execute(
        text(
            """select 1 from public.organization_users
               where organization_id=:org and auth_user_id=:user and active
                 and role in ('ORG_ADMIN', 'RECEPTIONIST')"""
        ),
        {"org": organization_id, "user": user_id},
    )
    if allowed.first() is None:
        raise ApiError(
            code="FORBIDDEN",
            message="Booking staff access is required.",
            status_code=403,
        )


async def require_organization_admin(
    session: AsyncSession, organization_id: UUID, user_id: UUID
) -> None:
    allowed = await session.execute(
        text(
            """select 1 from public.organization_users
               where organization_id=:org and auth_user_id=:user and active and role='ORG_ADMIN'"""
        ),
        {"org": organization_id, "user": user_id},
    )
    if allowed.first() is None:
        raise ApiError(
            code="FORBIDDEN",
            message="Only an organization administrator can permanently delete records.",
            status_code=403,
        )


@router.get("/patients")
async def list_patients(
    organization_id: UUID,
    query: str = Query(default="", max_length=160),
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> list[dict[str, object]]:
    await require_booking_staff(session, organization_id, principal.user_id)
    result = await session.execute(
        text(
            """with contact_rollup as (
                 select pc.organization_id, pc.patient_id,
                        jsonb_agg(
                          jsonb_build_object(
                            'contact_id', c.id,
                            'contact_name', c.display_name,
                            'relationship', pc.relationship,
                            'phone_e164', phone.phone_e164
                          )
                          order by pc.recorded_at desc
                        ) as contacts
                 from public.patient_contacts pc
                 join public.contacts c
                   on c.organization_id=pc.organization_id and c.id=pc.contact_id
                 left join lateral (
                   select cp.phone_e164
                   from public.contact_phones cp
                   where cp.organization_id=pc.organization_id
                     and cp.contact_id=pc.contact_id and cp.status='ACTIVE'
                   order by cp.created_at desc
                   limit 1
                 ) phone on true
                 where pc.organization_id=:org and pc.relationship_status='RECORDED'
                 group by pc.organization_id, pc.patient_id
               ),
               appointment_rollup as (
                 select a.organization_id, a.patient_id,
                        count(*) as appointment_count,
                        max(coalesce(slot.starts_at, appointment_session.starts_at))
                          as last_appointment_at,
                        min(coalesce(slot.starts_at, appointment_session.starts_at)) filter (
                          where coalesce(slot.starts_at, appointment_session.starts_at) >= now()
                            and a.status='CONFIRMED'
                        ) as next_appointment_at
                 from public.appointments a
                 join public.appointment_sessions appointment_session
                   on appointment_session.organization_id=a.organization_id
                  and appointment_session.id=a.session_id
                 left join public.appointment_slots slot
                   on slot.organization_id=a.organization_id and slot.id=a.slot_id
                 where a.organization_id=:org
                 group by a.organization_id, a.patient_id
               )
               select p.id, p.display_name, p.disambiguation, p.status, p.created_at,
                      coalesce(ar.appointment_count, 0) as appointment_count,
                      ar.last_appointment_at,
                      ar.next_appointment_at,
                      coalesce(cr.contacts, '[]'::jsonb) as contacts
               from public.patients p
               left join contact_rollup cr
                 on cr.organization_id=p.organization_id and cr.patient_id=p.id
               left join appointment_rollup ar
                 on ar.organization_id=p.organization_id and ar.patient_id=p.id
               where p.organization_id=:org
                 and (
                   cast(:query as text)=''
                   or p.display_name ilike '%' || cast(:query as text) || '%'
                   or exists (
                     select 1
                     from public.patient_contacts search_link
                     join public.contacts search_contact
                       on search_contact.organization_id=search_link.organization_id
                      and search_contact.id=search_link.contact_id
                     left join public.contact_phones search_phone
                       on search_phone.organization_id=search_link.organization_id
                      and search_phone.contact_id=search_link.contact_id
                      and search_phone.status='ACTIVE'
                     where search_link.organization_id=p.organization_id
                       and search_link.patient_id=p.id
                       and search_link.relationship_status='RECORDED'
                       and (
                         search_contact.display_name ilike
                           '%' || cast(:query as text) || '%'
                         or search_phone.phone_e164 ilike
                           '%' || cast(:query as text) || '%'
                       )
                   )
                 )
               order by p.status, p.display_name"""
        ),
        {"org": organization_id, "query": query.strip()},
    )
    return [dict(row) for row in result.mappings()]


@router.get("/caller-profile")
async def get_caller_profile(
    organization_id: UUID,
    phone_e164: str = Query(pattern=r"^\+[1-9][0-9]{7,14}$"),
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    """Resolve one unique mobile to its caller and permitted patient profiles.

    This is the deterministic identity context used by future agent tools. Caller-ID
    recognition may select this profile, but disclosure and mutations still require
    the verification policy defined by the conversation layer.
    """
    await require_booking_staff(session, organization_id, principal.user_id)
    result = await session.execute(
        text(
            """
            select c.id as contact_id, c.display_name as contact_name,
                   cp.id as phone_id, cp.phone_e164, cp.last_verified_at,
                   coalesce(
                     jsonb_agg(
                       jsonb_build_object(
                         'patient_id', p.id,
                         'patient_name', p.display_name,
                         'disambiguation', p.disambiguation,
                         'relationship', link.relationship
                       ) order by
                         case link.relationship
                           when 'SELF' then 0 when 'MOTHER' then 1
                           when 'FATHER' then 2 when 'SPOUSE' then 3
                           when 'CHILD' then 4 else 5 end,
                         p.display_name
                     ) filter (where p.id is not null),
                     '[]'::jsonb
                   ) as patients
            from public.contact_phones cp
            join public.contacts c
              on c.organization_id=cp.organization_id and c.id=cp.contact_id
            left join public.patient_contacts link
              on link.organization_id=c.organization_id and link.contact_id=c.id
             and link.relationship_status='RECORDED'
            left join public.patients p
              on p.organization_id=link.organization_id and p.id=link.patient_id
             and p.status='ACTIVE'
            where cp.organization_id=:org and cp.phone_e164=:phone
              and cp.status='ACTIVE' and c.status='ACTIVE'
            group by c.id, c.display_name, cp.id, cp.phone_e164, cp.last_verified_at
            """
        ),
        {"org": organization_id, "phone": phone_e164},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise ApiError(
            code="CALLER_NOT_FOUND",
            message="Mobile number is not registered.",
            status_code=404,
        )
    return dict(row)


@router.patch("/patients/{patient_id}")
async def update_patient(
    patient_id: UUID,
    organization_id: UUID,
    payload: PatientUpdate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        await require_booking_staff(session, organization_id, principal.user_id)
        result = await session.execute(
            text(
                """update public.patients
                   set display_name=:name, disambiguation=:disambiguation, status=:status
                   where organization_id=:org and id=:patient
                   returning id, display_name, disambiguation, status"""
            ),
            {
                "name": payload.display_name.strip(),
                "disambiguation": payload.disambiguation.strip(),
                "status": payload.status,
                "org": organization_id,
                "patient": patient_id,
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(code="NOT_FOUND", message="Patient was not found.", status_code=404)
        return dict(row)


@router.patch("/patients/{patient_id}/contacts/{contact_id}")
async def update_patient_contact(
    patient_id: UUID,
    contact_id: UUID,
    organization_id: UUID,
    payload: PatientContactUpdate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        await require_booking_staff(session, organization_id, principal.user_id)
        relationship = await session.execute(
            text(
                """update public.patient_contacts set relationship=:relationship
                   where organization_id=:org and patient_id=:patient and contact_id=:contact
                     and relationship_status='RECORDED'
                   returning patient_id"""
            ),
            {
                "relationship": payload.relationship.strip().upper(),
                "org": organization_id,
                "patient": patient_id,
                "contact": contact_id,
            },
        )
        if relationship.first() is None:
            raise ApiError(
                code="NOT_FOUND",
                message="Patient relationship was not found.",
                status_code=404,
            )
        await session.execute(
            text(
                """update public.contacts set display_name=:name
                   where organization_id=:org and id=:contact"""
            ),
            {"name": payload.contact_name.strip(), "org": organization_id, "contact": contact_id},
        )
        try:
            phone = await session.execute(
                text(
                    """update public.contact_phones set phone_e164=:phone, version=version+1
                       where organization_id=:org and contact_id=:contact and status='ACTIVE'
                       returning id"""
                ),
                {"phone": payload.phone_e164, "org": organization_id, "contact": contact_id},
            )
        except IntegrityError as exc:
            raise ApiError(
                code="PHONE_IN_USE",
                message="That mobile number is already assigned to another caller.",
                status_code=409,
            ) from exc
        if phone.first() is None:
            await session.execute(
                text(
                    """insert into public.contact_phones
                       (organization_id, contact_id, phone_e164)
                       values (:org, :contact, :phone)"""
                ),
                {"phone": payload.phone_e164, "org": organization_id, "contact": contact_id},
            )
    return {"patient_id": patient_id, "contact_id": contact_id, "updated": True}


@router.delete("/patients/{patient_id}")
async def delete_patient(
    patient_id: UUID,
    organization_id: UUID,
    hard_delete: bool = Query(
        default=False,
        description="If true, permanently deletes the patient, links, and appointments.",
    ),
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        await require_booking_staff(session, organization_id, principal.user_id)

        patient_row = (
            await session.execute(
                text(
                    "select id, display_name from public.patients where organization_id=:org and id=:patient"
                ),
                {"org": organization_id, "patient": patient_id},
            )
        ).mappings().one_or_none()

        if patient_row is None:
            raise ApiError(code="NOT_FOUND", message="Patient was not found.", status_code=404)

        if hard_delete:
            await require_organization_admin(session, organization_id, principal.user_id)
            links = list(
                (
                    await session.execute(
                        text(
                            """select contact_id, relationship
                               from public.patient_contacts
                               where organization_id=:org and patient_id=:patient
                                 and relationship_status='RECORDED'"""
                        ),
                        {"org": organization_id, "patient": patient_id},
                    )
                ).mappings()
            )
            self_contact_ids = [
                row["contact_id"] for row in links if row["relationship"] == "SELF"
            ]
            patient_ids = [patient_id]
            contact_ids: list[UUID] = []
            if self_contact_ids:
                # Deleting a SELF profile is a deliberate caller-profile purge. Include
                # only relatives who are not linked to any other caller.
                contact_ids = self_contact_ids
                patient_ids = list(
                    (
                        await session.execute(
                            text(
                                """select distinct link.patient_id
                                   from public.patient_contacts link
                                   where link.organization_id=:org
                                     and link.contact_id = any(cast(:contacts as uuid[]))
                                     and not exists (
                                         select 1
                                         from public.patient_contacts other_link
                                         where other_link.organization_id=link.organization_id
                                           and other_link.patient_id=link.patient_id
                                           and other_link.contact_id <> all(cast(:contacts as uuid[]))
                                     )"""
                            ),
                            {"org": organization_id, "contacts": contact_ids},
                        )
                    ).scalars()
                )

            appointment_ids = list(
                (
                    await session.execute(
                        text(
                            """select id from public.appointments
                               where organization_id=:org
                                 and patient_id = any(cast(:patients as uuid[]))
                                 or (
                                     organization_id=:org
                                     and :purge_caller
                                     and booked_by_contact_id = any(cast(:contacts as uuid[]))
                                 )"""
                        ),
                        {
                            "org": organization_id,
                            "patients": patient_ids,
                            "contacts": contact_ids,
                            "purge_caller": bool(contact_ids),
                        },
                    )
                ).scalars()
            )
            phone_ids: list[UUID] = []
            if contact_ids:
                phone_ids = list(
                    (
                        await session.execute(
                            text(
                                """select id from public.contact_phones
                                   where organization_id=:org
                                     and contact_id = any(cast(:contacts as uuid[]))"""
                            ),
                            {"org": organization_id, "contacts": contact_ids},
                        )
                    ).scalars()
                )

            if appointment_ids:
                await session.execute(
                    text(
                        """update public.appointments set supersedes_appointment_id=null
                           where organization_id=:org
                             and supersedes_appointment_id = any(cast(:appointments as uuid[]))"""
                    ),
                    {"org": organization_id, "appointments": appointment_ids},
                )
                for statement in (
                    """delete from public.appointment_contact_permissions
                       where organization_id=:org
                         and appointment_id = any(cast(:appointments as uuid[]))""",
                    """delete from public.payment_attempts where organization_id=:org
                       and appointment_id = any(cast(:appointments as uuid[]))""",
                    """update public.idempotency_records set response_appointment_id=null
                       where organization_id=:org
                         and response_appointment_id = any(cast(:appointments as uuid[]))""",
                    """delete from public.outbox_jobs where organization_id=:org
                       and aggregate_id = any(cast(:appointments as uuid[]))""",
                    """delete from public.appointments where organization_id=:org
                       and id = any(cast(:appointments as uuid[]))""",
                ):
                    await session.execute(
                        text(statement),
                        {"org": organization_id, "appointments": appointment_ids},
                    )

            if phone_ids:
                await session.execute(
                    text(
                        """delete from public.verification_challenges
                           where organization_id=:org
                             and contact_phone_id = any(cast(:phones as uuid[]))"""
                    ),
                    {"org": organization_id, "phones": phone_ids},
                )
            await session.execute(
                text(
                    """delete from public.patient_contacts
                       where organization_id=:org
                         and patient_id = any(cast(:patients as uuid[]))"""
                ),
                {"org": organization_id, "patients": patient_ids},
            )
            await session.execute(
                text(
                    """delete from public.patients where organization_id=:org
                       and id = any(cast(:patients as uuid[]))"""
                ),
                {"org": organization_id, "patients": patient_ids},
            )
            if contact_ids:
                await session.execute(
                    text(
                        """delete from public.contact_phones where organization_id=:org
                           and contact_id = any(cast(:contacts as uuid[]))"""
                    ),
                    {"org": organization_id, "contacts": contact_ids},
                )
                await session.execute(
                    text(
                        """delete from public.contacts contact
                           where contact.organization_id=:org
                             and contact.id = any(cast(:contacts as uuid[]))
                             and not exists (
                                 select 1 from public.patient_contacts link
                                 where link.organization_id=contact.organization_id
                                   and link.contact_id=contact.id
                             )"""
                    ),
                    {"org": organization_id, "contacts": contact_ids},
                )
            return {
                "deleted": True,
                "hard_delete": True,
                "patient_id": str(patient_id),
                "patient_name": patient_row["display_name"],
                "caller_profile_purged": bool(contact_ids),
                "deleted_patient_count": len(patient_ids),
            }
        else:
            await session.execute(
                text(
                    """
                    update public.patient_contacts
                    set relationship_status='REVOKED', revoked_at=now()
                    where organization_id=:org and patient_id=:patient
                    """
                ),
                {"org": organization_id, "patient": patient_id},
            )
            await session.execute(
                text(
                    "update public.patients set status='ARCHIVED' where organization_id=:org and id=:patient"
                ),
                {"org": organization_id, "patient": patient_id},
            )
            return {
                "deleted": True,
                "hard_delete": False,
                "status": "ARCHIVED",
                "patient_id": str(patient_id),
                "patient_name": patient_row["display_name"],
            }


@router.delete("/patients/{patient_id}/contacts/{contact_id}")
async def unlink_patient_contact(
    patient_id: UUID,
    contact_id: UUID,
    organization_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, object]:
    async with session.begin():
        await session.execute(
            text("select set_config('request.jwt.claim.sub', :user, true)"),
            {"user": str(principal.user_id)},
        )
        await require_booking_staff(session, organization_id, principal.user_id)
        res = await session.execute(
            text(
                """
                delete from public.patient_contacts
                where organization_id=:org and patient_id=:patient and contact_id=:contact
                returning patient_id
                """
            ),
            {"org": organization_id, "patient": patient_id, "contact": contact_id},
        )
        if res.first() is None:
            raise ApiError(code="NOT_FOUND", message="Patient link was not found.", status_code=404)
    return {"unlinked": True, "patient_id": str(patient_id), "contact_id": str(contact_id)}
