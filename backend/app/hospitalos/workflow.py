"""Database-backed synthetic receiving workflow; no patient identity is stored."""

import hashlib
import json
import secrets
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def capacity_available(
    *, ed_ready: int, icu_ready: int, ed_held: int, icu_held: int,
    needs_icu: bool,
) -> bool:
    return ed_held < ed_ready and (not needs_icu or icu_held < icu_ready)


async def append_event(
    session: AsyncSession,
    *,
    case_id: UUID,
    request_id: UUID | None,
    organization_id: UUID | None,
    event_type: str,
    actor_type: str,
    actor_id: UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    await session.execute(
        text("""insert into public.hospitalos_events
                (case_id,request_id,organization_id,event_type,actor_type,actor_id,detail)
                values (:case_id,:request_id,:org,:event_type,:actor_type,:actor_id,
                        cast(:detail as jsonb))"""),
        {
            "case_id": case_id, "request_id": request_id, "org": organization_id,
            "event_type": event_type, "actor_type": actor_type, "actor_id": actor_id,
            "detail": json.dumps(detail or {}),
        },
    )


async def expire_due(
    session: AsyncSession, *, case_id: UUID | None = None,
    organization_id: UUID | None = None,
) -> None:
    predicate = ""
    params: dict[str, UUID] = {}
    if case_id is not None:
        predicate = " and case_id=:case_id"
        params["case_id"] = case_id
    elif organization_id is not None:
        predicate = " and organization_id=:org"
        params["org"] = organization_id
    await session.execute(
        text("""with expired as (
                    update public.hospitalos_requests
                    set status='EXPIRED',version=version+1,updated_at=now()
                    where status='PENDING' and deadline_at<=now()""" + predicate + """
                    returning id,case_id,organization_id,deadline_at
                )
                insert into public.hospitalos_events
                    (case_id,request_id,organization_id,event_type,actor_type,detail)
                select case_id,id,organization_id,'REQUEST_EXPIRED','SYSTEM',
                       jsonb_build_object('deadline_at',deadline_at)
                from expired"""),
        params,
    )


async def authenticated_case(
    session: AsyncSession, case_id: UUID, tracking_token: str,
) -> dict[str, Any]:
    result = await session.execute(
        text("""select id,origin,preference,requirement,audience,eta_minutes,
                       tracking_token_hash
                from public.hospitalos_cases where id=:case_id"""),
        {"case_id": case_id},
    )
    row = result.mappings().one_or_none()
    if row is None or not secrets.compare_digest(
        row["tracking_token_hash"], token_hash(tracking_token)
    ):
        raise ApiError("CASE_NOT_FOUND", "Demo case was not found.", 404)
    return dict(row)


async def request_snapshot(session: AsyncSession, case_id: UUID) -> dict[str, Any]:
    result = await session.execute(
        text("""select r.id,r.case_id,r.organization_id,r.status,r.version,
                       r.deadline_at,r.created_at,r.decided_at,c.eta_minutes,
                       case when r.status='ACCEPTED' then r.arrival_note end as arrival_note,
                       c.origin,c.requirement,c.audience,f.name as facility_name,
                       f.slug as facility_slug,
                       h.status as hold_state,h.expires_at as hold_expires_at
                from public.hospitalos_requests r
                join public.hospitalos_cases c on c.id=r.case_id
                join public.hospitalos_facilities f on f.id=r.facility_id
                left join public.hospitalos_holds h on h.request_id=r.id
                where r.case_id=:case_id"""),
        {"case_id": case_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise ApiError("CASE_NOT_FOUND", "Demo case was not found.", 404)
    events = await session.execute(
        text("""select id,event_type,actor_type,detail,occurred_at
                from public.hospitalos_events where case_id=:case_id order by id"""),
        {"case_id": case_id},
    )
    view = dict(row)
    if view["hold_state"] == "ACTIVE" and view["hold_expires_at"] <= datetime.now(
        view["hold_expires_at"].tzinfo
    ):
        view["hold_state"] = "EXPIRED"
    view["events"] = [dict(event) for event in events.mappings()]
    view["synthetic_demo"] = True
    return view
