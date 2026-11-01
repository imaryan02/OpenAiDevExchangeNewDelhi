import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.agent.tools import ToolExecutor
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_session_factory

router = APIRouter()


class CallerLookupRequest(BaseModel):
    phone_e164: str


class AvailabilityRequest(BaseModel):
    from_at: str
    to_at: str
    doctor_name: str | None = None


class PrepareBookingRequest(BaseModel):
    phone_e164: str
    caller_name: str | None = None
    patient_name: str
    relationship: str
    session_id: str
    slot_id: str | None = None
    payment_method: str = "ONLINE"
    language: str = "hi-IN"
    create_patient_if_missing: bool = False
    create_caller_if_missing: bool = False


class ConfirmBookingRequest(BaseModel):
    offer_token: str
    explicit_confirmation: bool = Field(
        description="True only after the caller accepts the complete spoken read-back"
    )
    interaction_id: str = Field(min_length=1, max_length=200)


def require_sarvam(
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> Settings:
    if not settings.sarvam_tools_configured:
        raise ApiError("SARVAM_NOT_CONFIGURED", "Sarvam tools are not configured.", 503)
    expected = f"Bearer {settings.sarvam_tool_secret}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise ApiError("SARVAM_UNAUTHORIZED", "Invalid Sarvam tool credential.", 401)
    return settings


async def run_tool(settings: Settings, name: str, arguments: dict[str, Any]) -> dict[str, object]:
    assert settings.database_url is not None
    assert settings.voice_organization_id is not None
    assert settings.voice_actor_id is not None
    factory = get_session_factory(settings.database_url)
    async with factory() as session:
        return await ToolExecutor(
            session,
            settings.voice_organization_id,
            actor_id=settings.voice_actor_id,
            settings=settings,
        ).execute(name, arguments)


@router.post("/caller-lookup")
async def caller_lookup(
    payload: CallerLookupRequest,
    settings: Settings = Depends(require_sarvam),
) -> dict[str, object]:
    return await run_tool(settings, "lookup_caller_family", payload.model_dump())


@router.post("/availability")
async def availability(
    payload: AvailabilityRequest,
    settings: Settings = Depends(require_sarvam),
) -> dict[str, object]:
    return await run_tool(settings, "search_availability", payload.model_dump())


@router.post("/booking/prepare")
async def prepare_booking(
    payload: PrepareBookingRequest,
    settings: Settings = Depends(require_sarvam),
) -> dict[str, object]:
    return await run_tool(settings, "prepare_booking_offer", payload.model_dump())


@router.post("/booking/confirm")
async def confirm_booking(
    payload: ConfirmBookingRequest,
    settings: Settings = Depends(require_sarvam),
) -> dict[str, object]:
    if not payload.explicit_confirmation:
        return {"ok": False, "error": "Explicit confirmation is required."}
    return await run_tool(
        settings,
        "confirm_booking_offer",
        {"offer_token": payload.offer_token, "interaction_id": payload.interaction_id},
    )
