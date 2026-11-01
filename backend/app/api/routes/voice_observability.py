"""Tenant-authorized access to call summaries, conversation and technical evidence."""

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.session import get_session_factory
from app.observability.callers import phone_search_digits
from app.repositories.memberships import list_active_memberships
from app.security.auth import Principal, get_current_principal

router = APIRouter()


async def authorize(
    organization_id: UUID, principal: Principal = Depends(get_current_principal)
) -> str:
    memberships = await list_active_memberships(principal.user_id)
    if not any(m.organization_id == organization_id and m.role in {"ORG_ADMIN", "RECEPTIONIST"}
               for m in memberships):
        raise ApiError(
            code="FORBIDDEN", message="Reception staff access is required.", status_code=403
        )
    if not get_settings().database_url:
        raise ApiError(
            code="SERVICE_UNAVAILABLE", message="Call history is unavailable.", status_code=503
        )
    return str(organization_id)


async def _list_calls(
    organization: str,
    limit: int = 50,
    offset: int = 0,
    engine: Literal["CHAINED", "REALTIME"] | None = None,
    status: Literal["ACTIVE", "ENDED", "INTERRUPTED", "FAILED", "UNKNOWN"] | None = None,
    started_from: datetime | None = None,
    started_before: datetime | None = None,
    search: str = "",
    phone_search: str = "",
    caller_number: str | None = None,
) -> dict[str, object]:
    settings = get_settings()
    try:
        phone_digits = phone_search_digits(phone_search)
    except ValueError as error:
        raise ApiError("INVALID_PHONE_SEARCH", str(error), 422) from None
    async with get_session_factory(settings.database_url)() as session:
        result = await session.execute(text("""
            select id, provider, engine, status, started_at, ended_at, duration_ms,
                   event_count, events_complete, capture_policy,
                   caller_number, caller_number_source,
                   case when caller_number is null then null else
                     (select count(*) from public.voice_observability_calls history
                       where history.organization_id = :org
                         and history.caller_number = voice_observability_calls.caller_number)
                   end as caller_call_count,
                   (select count(*) from public.voice_operation_records o
                    join public.voice_call_sessions s on s.id = o.voice_call_session_id
                     and s.organization_id = o.organization_id
                    where o.organization_id = :org
                      and s.provider_call_id = voice_observability_calls.provider_call_id
                      and o.status = 'COMMITTED') as committed_count,
                   (select count(*) from public.voice_operation_records o
                    join public.voice_call_sessions s on s.id = o.voice_call_session_id
                     and s.organization_id = o.organization_id
                    where o.organization_id = :org
                      and s.provider_call_id = voice_observability_calls.provider_call_id
                      and o.status = 'FAILED') as failed_count
              from public.voice_observability_calls
             where organization_id = :org
               and (cast(:engine as text) is null or engine = :engine)
               and (cast(:status as text) is null or status = :status)
               and (cast(:started_from as timestamptz) is null or started_at >= :started_from)
               and (cast(:started_before as timestamptz) is null or started_at < :started_before)
               and (cast(id as text) like :search)
               and (:phone_digits = '' or caller_number like :phone_pattern)
               and (cast(:caller_number as text) is null or caller_number = :caller_number)
             order by started_at desc, id desc
             limit :limit offset :offset
        """), {"org": organization, "limit": limit, "offset": offset,
               "engine": engine, "status": status, "started_from": started_from,
               "started_before": started_before, "search": f"%{search.strip()}%",
               "phone_digits": phone_digits, "phone_pattern": f"%{phone_digits}%",
               "caller_number": caller_number})
        rows = [dict(row._mapping) for row in result]
    return {"calls": rows, "limit": limit, "offset": offset,
            "capture_policy": {"transcripts": settings.voice_transcript_capture_enabled,
                               "recordings": False, "caller_numbers": True}}


@router.get("/voice/calls")
async def list_calls(
    response: Response, organization: str = Depends(authorize),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    engine: Literal["CHAINED", "REALTIME"] | None = None,
    status: Literal["ACTIVE", "ENDED", "INTERRUPTED", "FAILED", "UNKNOWN"] | None = None,
    started_from: datetime | None = None, started_before: datetime | None = None,
    search: str = Query(default="", max_length=36),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    return await _list_calls(organization, limit, offset, engine, status,
                             started_from, started_before, search, "", None)


class CallSearch(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)
    engine: Literal["CHAINED", "REALTIME"] | None = None
    status: Literal["ACTIVE", "ENDED", "INTERRUPTED", "FAILED", "UNKNOWN"] | None = None
    started_from: datetime | None = None
    started_before: datetime | None = None
    search: str = Field(default="", max_length=36)
    phone_search: str = Field(default="", max_length=30)
    caller_number: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{7,14}$")

    @field_validator("phone_search")
    @classmethod
    def validate_phone_search(cls, value: str) -> str:
        return phone_search_digits(value)


@router.post("/voice/calls/search")
async def search_calls(filters: CallSearch, response: Response,
                       organization: str = Depends(authorize)) -> dict[str, object]:
    # Put phone filters in the body so normal application access logs don't expose numbers.
    response.headers["Cache-Control"] = "no-store"
    return await _list_calls(organization=organization, **filters.model_dump())


@router.get("/voice/calls/{call_id}")
async def get_call(call_id: UUID, response: Response, organization: str = Depends(authorize),
                   after_sequence: int = Query(default=0, ge=0),
                   limit: int = Query(default=500, ge=1, le=500)) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    settings = get_settings()
    async with get_session_factory(settings.database_url)() as session:
        result = await session.execute(text("""
            select id, provider, provider_call_id, engine, status, started_at, ended_at,
                   duration_ms, last_event_at,
                   event_count, events_complete, capture_policy, caller_number, caller_number_source
              from public.voice_observability_calls
             where id = :id and organization_id = :org
        """), {"id": call_id, "org": organization})
        call = result.first()
        if call is None:
            raise ApiError(
                code="CALL_NOT_FOUND", message="Call history record was not found.", status_code=404
            )
        runtime_result = await session.execute(text("""
            select id, status from public.voice_call_sessions
             where organization_id = :org and provider_call_id = :provider_call_id
             limit 1
        """), {"org": organization, "provider_call_id": call.provider_call_id})
        runtime = runtime_result.first()
        operations = []
        if runtime is not None:
            operation_result = await session.execute(text("""
                select operation_id, operation_type, status, created_at, updated_at, committed_at
                  from public.voice_operation_records
                 where organization_id = :org and voice_call_session_id = :session_id
                 order by created_at, operation_id
                 limit 100
            """), {"org": organization, "session_id": runtime.id})
            operations = [dict(row._mapping) for row in operation_result]
        event_result = await session.execute(text("""
            select sequence, event_type, stage, occurred_at, duration_ms, metadata
              from public.voice_observability_events
             where call_id = :id and organization_id = :org and sequence > :after
             order by sequence
             limit :limit
        """), {"id": call_id, "org": organization, "after": after_sequence, "limit": limit + 1})
        event_rows = [dict(row._mapping) for row in event_result]
        events = event_rows[:limit]
        next_sequence = events[-1]["sequence"] if len(event_rows) > limit else None
        usage_result = await session.execute(text("""
            select provider, engine, operation, model, request_id, identity_source,
                   usage_type, input_tokens, output_tokens, total_tokens,
                   input_audio_tokens, output_audio_tokens, cached_input_tokens,
                   duration_seconds, observed_at
              from public.voice_observability_usage
             where call_id = :id and organization_id = :org
             order by observed_at, id
             limit 500
        """), {"id": call_id, "org": organization})
        usage = [dict(row._mapping) for row in usage_result]
    trace_available = False
    for event in events:
        metadata = event.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
            event["metadata"] = metadata
        if isinstance(metadata, dict) and metadata.pop("trace_id", None):
            trace_available = True
    call_summary = dict(call._mapping)
    call_summary.pop("provider_call_id", None)
    delays = [event["metadata"].get("ingestion_delay_ms") for event in events
              if isinstance(event.get("metadata"), dict)]
    measured_delays = [delay for delay in delays if isinstance(delay, int)
                       and not isinstance(delay, bool) and delay >= 0]
    runtime_status = runtime.status if runtime is not None else None
    return {"call": call_summary, "events": events, "events_next_sequence": next_sequence,
            "trace_available": trace_available,
            "runtime_session_status": runtime_status,
            "collection_health": {
                "fetched_at": datetime.now(UTC).isoformat(),
                "last_persisted_event_occurred_at": call_summary.get("last_event_at"),
                "events_complete": call_summary.get("events_complete"),
                "loaded_event_count": len(events), "event_page_partial": next_sequence is not None,
                "max_loaded_ingestion_delay_ms": max(measured_delays) if measured_delays else None,
                "lifecycle_status_disagrees": (
                    runtime_status != call_summary.get("status") if runtime_status else None
                ),
            },
            "operations": operations, "usage": usage,
            "usage_status": "reported" if usage else "unknown",
            "cost_status": "not_calculated"}


@router.get("/voice/calls/{call_id}/conversation")
async def conversation(
    call_id: UUID, response: Response, organization: str = Depends(authorize),
    principal: Principal = Depends(get_current_principal),
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    async with get_session_factory(get_settings().database_url)() as session:
        call = (await session.execute(text("""
            select capture_policy from public.voice_observability_calls
             where id = :id and organization_id = :org
        """), {"id": call_id, "org": organization})).first()
        if call is None:
            raise ApiError("CALL_NOT_FOUND", "Call history record was not found.", 404)
        policy = call.capture_policy
        if isinstance(policy, str):
            policy = json.loads(policy)
        if not isinstance(policy, dict) or policy.get("transcripts") is not True:
            return {"messages": [], "status": "capture_disabled", "next_sequence": None}
        available = (await session.execute(text(
            "select to_regclass('public.voice_observability_messages') is not null"
        ))).scalar_one()
        if not available:
            return {"messages": [], "status": "migration_required", "next_sequence": None}
        result = await session.execute(text("""
            select sequence, speaker, content, evidence, occurred_at, elapsed_ms,
                   truncated, source_id
              from public.voice_observability_messages
             where call_id = :id and organization_id = :org
               and expires_at > now() and sequence > :after
             order by sequence limit :limit
        """), {"id": call_id, "org": organization, "after": after_sequence, "limit": limit + 1})
        rows = [dict(row._mapping) for row in result]
        messages = rows[:limit]
        # Never return conversation text unless the access audit commits successfully.
        await session.execute(text("""
            insert into public.voice_observability_content_access
                (organization_id, call_id, user_id, message_count)
            values (:org, :id, :user_id, :count)
        """), {"org": organization, "id": call_id, "user_id": principal.user_id,
               "count": len(messages)})
        await session.commit()
    return {"messages": messages, "status": "available" if messages else "unavailable",
            "next_sequence": messages[-1]["sequence"] if len(rows) > limit else None}


@router.get("/voice/connection-attempts")
async def connection_attempts(organization: str = Depends(authorize)) -> dict[str, object]:
    async with get_session_factory(get_settings().database_url)() as session:
        available = (await session.execute(text(
            "select to_regclass('public.voice_observability_attempts') is not null"
        ))).scalar_one()
        if not available:
            return {"attempts": [], "status": "migration_required"}
        result = await session.execute(text("""
            select id, status, occurred_at from public.voice_observability_attempts
             where organization_id = :org order by occurred_at desc limit 50
        """), {"org": organization})
        return {"attempts": [dict(row._mapping) for row in result], "status": "available"}
