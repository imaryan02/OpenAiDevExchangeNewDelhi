from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_session_factory
from app.personal_agent.config import PersonalSettings, get_personal_settings
from app.personal_agent.domain import utcnow
from app.personal_agent.repository import PersonalRepository
from app.personal_agent.schemas import (
    FollowupAction,
    ModeInput,
    ProfileInput,
    ReminderInput,
    TaskInput,
    TaskUpdate,
)
from app.security.auth import Principal, get_current_principal

router = APIRouter(prefix="/v1/personal-agent", tags=["personal agent"])


async def personal_owner(
    principal: Principal = Depends(get_current_principal),
    config: PersonalSettings = Depends(get_personal_settings),
) -> UUID:
    if config.owner_id is None:
        raise ApiError("PERSONAL_OWNER_NOT_CONFIGURED", "Configure the personal demo owner.", 503)
    if principal.user_id != config.owner_id:
        raise ApiError(
            "PERSONAL_ACCESS_DENIED", "This personal workspace belongs to its owner.", 403
        )
    if not config.enabled:
        raise ApiError("PERSONAL_DISABLED", "Personal AI is disabled on this backend.", 503)
    return principal.user_id


async def repository(
    owner: UUID = Depends(personal_owner),
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[PersonalRepository]:
    if not settings.database_url:
        raise ApiError("DATABASE_NOT_CONFIGURED", "Database is not configured.", 503)
    async with get_session_factory(settings.database_url)() as session:
        try:
            yield PersonalRepository(session, owner)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Commit/rollback completes before sending a success response.
Repo = Annotated[PersonalRepository, Depends(repository, scope="function")]


@router.get("/readiness")
async def readiness(
    principal: Principal = Depends(get_current_principal),
    config: PersonalSettings = Depends(get_personal_settings),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if config.owner_id is not None and principal.user_id != config.owner_id:
        raise ApiError(
            "PERSONAL_ACCESS_DENIED", "This personal workspace belongs to its owner.", 403
        )
    from app.personal_agent.twilio_callbacks import configured

    callback_configured = (
        configured(settings)
        if config.callback_provider == "twilio"
        else bool(config.voicelink_api_token)
    )
    return {
        "enabled": config.enabled,
        "owner_configured": config.owner_id is not None,
        "current_user_id": str(principal.user_id),
        "registered_phone": (
            config.registered_phone if config.owner_id == principal.user_id else None
        ),
        "database_configured": bool(settings.database_url),
        "voice_configured": settings.realtime_configured and settings.voicelink_voice_configured,
        "voice_routing_implemented": True,
        "callback_implemented": True,
        "callback_provider": config.callback_provider,
        "callback_configured": callback_configured,
        "voicelink_outbound_configured": bool(config.voicelink_api_token),
        "scheduler_enabled": config.scheduler_enabled,
        "whatsapp_configured": settings.twilio_whatsapp_configured,
        "whatsapp_fallback_configured": bool(config.whatsapp_content_sid),
        "whatsapp_sandbox": (settings.twilio_whatsapp_from or "").removeprefix("whatsapp:")
        == "+14155238886",
        "outbound_enabled": config.outbound_enabled,
        "whatsapp_enabled": config.whatsapp_enabled,
        "demo_controls_enabled": config.demo_controls_enabled,
        "provider_acceptance_verified": False,
        "server_time": utcnow(),
    }


@router.get("/profile")
async def profile(repo: Repo) -> dict[str, Any]:
    return await repo.profile()


@router.put("/profile")
async def save_profile(data: ProfileInput, repo: Repo) -> dict[str, Any]:
    return await repo.save_profile(data)


@router.put("/mode")
async def mode(
    data: ModeInput,
    repo: Repo,
    settings: Settings = Depends(get_settings),
    config: PersonalSettings = Depends(get_personal_settings),
) -> dict[str, Any]:
    if data.mode == "personal_agent":
        if not settings.realtime_configured or not settings.voicelink_voice_configured:
            raise ApiError(
                "PERSONAL_VOICE_NOT_CONFIGURED", "Configure personal voice dependencies.", 503
            )
        profile = await repo.profile(lock=True)
        if config.registered_phone and profile["phone_e164"] != config.registered_phone:
            raise ApiError(
                "PERSONAL_PHONE_MISMATCH", "Save the configured registered phone first.", 409
            )
    return await repo.set_mode(data.mode)


@router.get("/snapshot")
async def snapshot(repo: Repo) -> dict[str, Any]:
    return {
        "profile": await repo.profile(),
        "tasks": await repo.tasks(),
        "followups": await repo.collections("followups"),
        "calls": await repo.collections("calls"),
        "attempts": await repo.collections("attempts"),
        "messages": await repo.collections("messages"),
        "events": await repo.collections("events"),
        "server_time": utcnow(),
        "limit": 50,
        "tasks_limit": 200,
    }


@router.get("/tasks")
async def tasks(repo: Repo, today_only: bool = False) -> dict[str, Any]:
    return {"tasks": await repo.tasks(today_only=today_only), "limit": 200}


@router.post("/tasks", status_code=201)
async def create_task(data: TaskInput, repo: Repo) -> dict[str, Any]:
    return await repo.create_task(data)


@router.put("/tasks/{task_id}")
async def update_task(task_id: UUID, data: TaskUpdate, repo: Repo) -> dict[str, Any]:
    return await repo.update_task(task_id, data)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: UUID, repo: Repo, version: int = Query(ge=1)) -> dict[str, bool]:
    await repo.delete_task(task_id, version)
    return {"deleted": True}


@router.post("/followups", status_code=201)
async def create_followup(
    data: ReminderInput,
    repo: Repo,
    config: PersonalSettings = Depends(get_personal_settings),
) -> dict[str, Any]:
    event = await repo.create_followup(data)
    return {
        **event,
        "execution_enabled": config.scheduler_enabled and config.outbound_enabled,
        "execution_note": "Saved. Callback scheduling follows the current backend settings.",
    }


@router.post("/followups/{event_id}/action")
async def followup_action(event_id: UUID, data: FollowupAction, repo: Repo) -> dict[str, Any]:
    return await repo.followup_action(event_id, data.version, data.action, data.delay_seconds)


@router.get("/events")
async def events(repo: Repo, before: int | None = Query(default=None, ge=1)) -> dict[str, Any]:
    rows = await repo.collections("events", before=before, limit=51)
    return {"events": rows[:50], "next_before": rows[49]["id"] if len(rows) > 50 else None}


@router.get("/memory")
async def memory(repo: Repo) -> dict[str, Any]:
    rows = await repo.collections("memory", limit=50)
    await repo.activity("memory_accessed", "Owner reviewed recent conversation memory")
    return {"memory": rows, "limit": 50}


def require_demo_controls(config: PersonalSettings) -> None:
    if not config.demo_controls_enabled:
        raise ApiError("DEMO_CONTROLS_DISABLED", "Demo seed/reset controls are disabled.", 403)


@router.post("/demo/seed")
async def seed(
    repo: Repo, config: PersonalSettings = Depends(get_personal_settings)
) -> dict[str, int]:
    require_demo_controls(config)
    return {"created": await repo.seed()}


@router.post("/demo/reset")
async def reset(
    repo: Repo,
    config: PersonalSettings = Depends(get_personal_settings),
) -> dict[str, bool]:
    require_demo_controls(config)
    await repo.reset()
    # Cancel only personal queued work. In-flight provider actions are rejected above.
    for table in ("attempts", "messages"):
        await repo.session.execute(
            text(
                f"update public.personal_agent_{table} set status='canceled',updated_at=now() "
                "where owner_id=:owner and status='queued'"
            ),
            {"owner": repo.owner_id},
        )
    return {"reset": True}
