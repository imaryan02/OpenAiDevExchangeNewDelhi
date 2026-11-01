from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.session import get_db_session
from app.security.auth import Principal, get_current_principal
from app.services.schedule_generation import generate_sessions

router = APIRouter()


@router.get("/availability")
async def list_availability(
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
    membership = await session.execute(
        text(
            "select 1 from public.organization_users where organization_id=:org and auth_user_id=:user and active"
        ),
        {"org": organization_id, "user": principal.user_id},
    )
    if membership.first() is None:
        raise ApiError(
            code="FORBIDDEN", message="You cannot access this organization.", status_code=403
        )
    result = await session.execute(
        text("""
        select s.id, s.booking_mode, s.starts_at, s.ends_at, s.max_patients, s.next_token,
               count(a.id) filter (where a.status in ('PAYMENT_PENDING','CONFIRMED','COMPLETED','NO_SHOW')) as occupied
        from public.appointment_sessions s
        left join public.appointments a on a.organization_id=s.organization_id and a.session_id=s.id
        where s.organization_id=:org and s.starts_at >= :from_at and s.starts_at < :to_at
          and s.status in ('SCHEDULED','OPEN')
        group by s.id order by s.starts_at
        """),
        {"org": organization_id, "from_at": from_at, "to_at": to_at},
    )
    return [dict(row._mapping) for row in result]


@router.post("/schedule/generate")
async def generate_schedule(
    organization_id: UUID,
    through: date,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, int]:
    async with session.begin():
        membership = await session.execute(
            text("""select 1 from public.organization_users
            where organization_id=:org and auth_user_id=:user and active and role='ORG_ADMIN'"""),
            {"org": organization_id, "user": principal.user_id},
        )
        if membership.first() is None:
            raise ApiError(
                code="FORBIDDEN", message="Organization admin access is required.", status_code=403
            )
        if through < date.today():
            raise ApiError(
                code="INVALID_DATE_RANGE",
                message="The target date must be today or later.",
                status_code=422,
            )
        created = await generate_sessions(session, str(organization_id), through)
    return {"sessions_created": created}
