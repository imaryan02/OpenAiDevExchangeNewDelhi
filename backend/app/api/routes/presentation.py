"""Authenticated, tenant-scoped, read-only conference observer."""

import asyncio
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.errors import ApiError
from app.repositories.memberships import list_active_memberships
from app.security.auth import Principal, get_current_principal
from app.voice.presentation import store

router = APIRouter()


async def authorize(
    organization_id: UUID,
    principal: Principal = Depends(get_current_principal),
) -> str:
    if not get_settings().presentation_enabled:
        raise ApiError(code="PRESENTATION_DISABLED", message="Live presentation is not enabled.",
                       status_code=503)
    memberships = await list_active_memberships(principal.user_id)
    if not any(m.organization_id == organization_id for m in memberships):
        raise ApiError(code="FORBIDDEN", message="Active organization membership is required.",
                       status_code=403)
    return str(organization_id)


@router.get("/presentation/calls")
async def calls(organization: str = Depends(authorize)) -> dict[str, object]:
    settings = get_settings()
    return {"calls": store.list_for(organization), "retention_seconds": 3600,
            "transport": "single_worker", "enrolled_callers_only": True,
            "observer": {
                "capture_enabled": settings.presentation_enabled,
                "enrolled_caller_count": len(settings.presentation_demo_callers),
                "voice_organization_matches": (
                    settings.voice_organization_id is not None
                    and str(settings.voice_organization_id) == organization
                ),
            }}


@router.get("/presentation/calls/{call_id}/events")
async def events(
    call_id: UUID, request: Request, after: int = Query(default=0, ge=0),
    organization: str = Depends(authorize),
) -> StreamingResponse:
    key = str(call_id)
    if store.get(key, organization) is None:
        raise ApiError(code="TRACE_NOT_FOUND", message="This call trace expired or is unavailable.",
                       status_code=404)

    async def stream() -> AsyncIterator[str]:
        cursor = after
        # Bounded connections force fresh authentication / membership checks.
        for _ in range(100):
            if await request.is_disconnected():
                return
            call = store.get(key, organization)
            if call is None:
                yield 'event: expired\ndata: {}\n\n'
                return
            rows = [e for e in call["events"] if e["sequence"] > cursor]
            if rows:
                if rows[0]["sequence"] > cursor + 1:
                    yield 'event: gap\ndata: {}\n\n'
                for event in rows:
                    yield f"id: {event['sequence']}\ndata: {json.dumps(event)}\n\n"
                    cursor = event["sequence"]
            else:
                yield ": heartbeat\n\n"
            if call["ended"]:
                yield 'event: complete\ndata: {}\n\n'
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no",
    })
