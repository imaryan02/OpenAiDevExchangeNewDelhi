"""Public synthetic facility locator and staff-controlled Geeta resources."""

from typing import Any
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
from app.security.auth import Principal, get_current_principal

router = APIRouter(prefix="/v1/hospitalos", tags=["HospitalOS demo"])


class ResourceUpdate(BaseModel):
    organization_id: UUID
    expected_version: int = Field(ge=1)
    emergency_open: bool
    ed_bays_ready: int = Field(ge=0, le=1000)
    icu_beds_ready: int = Field(ge=0, le=1000)
    ventilators_ready: int = Field(ge=0, le=1000)
    ct_available: bool
    trauma_available: bool
    pediatric_available: bool
    obstetric_available: bool


def require_demo(settings: Settings) -> None:
    if not settings.hospitalos_demo_enabled:
        raise ApiError("HOSPITALOS_DEMO_DISABLED", "HospitalOS demo is not enabled.", 503)


@router.get("/facilities")
async def public_facilities(
    origin: Origin = "CENTRAL_DELHI",
    preference: Preference = "ANY",
    requirement: Requirement = "GENERAL",
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    require_demo(settings)
    result = await session.execute(
        text("""select slug,name,area,address,latitude,longitude,cost_category,
                       emergency_open,ed_bays_ready,icu_beds_ready,ventilators_ready,
                       ct_available,trauma_available,pediatric_available,
                       obstetric_available,receiving_enabled,synthetic,verified_at
                from public.hospitalos_facilities
                where synthetic=true and slug in
                    ('geeta-medicine','north-demo-hospital','east-demo-medical-centre')
                order by name""")
    )
    rows = [dict(row) for row in result.mappings()]
    return {
        "synthetic_demo": True,
        "origin": origin,
        "preference": preference,
        "requirement": requirement,
        "facilities": [
            item.model_dump(mode="json")
            for item in rank_facilities(rows, origin=origin, preference=preference,
                                        requirement=requirement)
        ],
    }


@router.get("/resources")
async def staff_resources(
    organization_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    require_demo(settings)
    await require_org_member(session, organization_id, principal.user_id)
    result = await session.execute(
        text("""select id,slug,name,area,location_id,cost_category,emergency_open,
                       ed_bays_ready,icu_beds_ready,ventilators_ready,ct_available,
                       trauma_available,pediatric_available,obstetric_available,
                       receiving_enabled,synthetic,verified_at,version
                from public.hospitalos_facilities
                where organization_id=:org order by name"""),
        {"org": organization_id},
    )
    return [dict(row) for row in result.mappings()]


@router.patch("/resources/{facility_id}")
async def update_resources(
    facility_id: UUID,
    payload: ResourceUpdate,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_demo(settings)
    async with session.begin():
        await require_org_admin(session, payload.organization_id, principal.user_id)
        updated = await session.execute(
            text("""update public.hospitalos_facilities
                    set emergency_open=:emergency_open,ed_bays_ready=:ed_bays_ready,
                        icu_beds_ready=:icu_beds_ready,ventilators_ready=:ventilators_ready,
                        ct_available=:ct_available,trauma_available=:trauma_available,
                        pediatric_available=:pediatric_available,
                        obstetric_available=:obstetric_available,
                        verified_at=now(),updated_at=now(),updated_by=:actor,version=version+1
                    where id=:facility and organization_id=:org and synthetic=true
                      and receiving_enabled=true and version=:expected_version
                    returning id,slug,name,emergency_open,ed_bays_ready,icu_beds_ready,
                              ventilators_ready,ct_available,trauma_available,
                              pediatric_available,obstetric_available,verified_at,version"""),
            {
                **payload.model_dump(),
                "facility": facility_id,
                "org": payload.organization_id,
                "actor": principal.user_id,
            },
        )
        row = updated.mappings().one_or_none()
        if row is None:
            raise ApiError(
                "RESOURCE_VERSION_CONFLICT",
                "Resource state changed or this facility is not editable. Refresh and try again.",
                409,
            )
        await session.execute(
            text("""insert into public.audit_events
                    (organization_id,actor_type,actor_id,action,entity_type,entity_id,
                     safe_change_summary)
                    values (:org,'USER',:actor,'HOSPITALOS_RESOURCE_UPDATED',
                            'hospitalos_facility',:facility,
                            jsonb_build_object('version',:new_version))"""),
            {
                "org": payload.organization_id,
                "actor": principal.user_id,
                "facility": facility_id,
                "new_version": row["version"],
            },
        )
    return dict(row)
