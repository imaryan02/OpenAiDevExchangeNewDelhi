"""Bounded persistence with separate identity, conversation and safe telemetry records."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.db.session import get_session_factory
from app.observability.callers import valid_caller_number

logger = logging.getLogger(__name__)

# Intentionally excludes arbitrary text, patient fields, phone numbers and tool arguments.
_SAFE_METADATA = {
    "tool", "origin", "result_count", "status", "duration_ms", "engine", "boundary", "chunks",
    "operation_id", "caller_turn_id", "generation_id", "playback_segment_id", "error_code",
    "queued_ms", "audio_ms", "queue_depth", "approval_candidate", "transcript_chars",
    "filler_played", "first_audio_latency_ms", "tts_first_audio_ms", "playback_duration_ms",
    "operation_type", "operation_status", "actual_engine",
    "trace_id",
    "elapsed_ms", "tool_invocation_id", "direction", "speaker", "response_id", "query_id",
    "caller_item_id", "assistant_item_id", "provider_tool_call_id", "message_source_id",
    "proposal_id", "durable_operation_id", "failure_type", "failure_reason",
}


class VoiceCapture:
    def __init__(self, database_url: str, max_queue: int = 2048) -> None:
        self._factory = get_session_factory(database_url)
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=max_queue)
        self._worker: asyncio.Task[None] | None = None
        self._dropped: dict[str, int] = {}

    def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run(), name="voice-observability-writer")

    def enqueue(self, item: dict[str, Any]) -> None:
        organization_id = str(item.get("organization_id", "unknown"))
        if item.get("action") == "event" and self._dropped.get(organization_id):
            item["incomplete"] = True
        try:
            self._queue.put_nowait(item)
            if item.get("incomplete"):
                self._dropped[organization_id] = 0
        except asyncio.QueueFull:
            self._dropped[organization_id] = self._dropped.get(organization_id, 0) + 1
            logger.error(
                "voice_observability_queue_full", extra={"organization_id": organization_id}
            )

    def start_call(self, organization_id: str, provider_call_id: str, engine: str,
                   *, transcripts: bool = False, caller_number: str | None = None) -> str:
        call_id = str(uuid4())
        self.enqueue({"action": "start", "id": call_id, "organization_id": organization_id,
                      "provider_call_id": provider_call_id[:255], "engine": engine.upper(),
                      "occurred_at": datetime.now(UTC), "transcripts": transcripts,
                      "caller_number": valid_caller_number(caller_number)})
        return call_id

    def event(self, call_id: str, organization_id: str, kind: str, stage: str,
              data: dict[str, Any]) -> None:
        candidates = dict(data)
        details = candidates.get("details")
        if isinstance(details, dict):
            candidates.update(details)
        metadata: dict[str, Any] = {}
        for key, value in candidates.items():
            if key not in _SAFE_METADATA:
                continue
            if key in {
                "duration_ms", "caller_turn_id", "generation_id", "queued_ms", "audio_ms",
                "queue_depth", "transcript_chars", "first_audio_latency_ms", "tts_first_audio_ms",
                "playback_duration_ms", "result_count", "chunks", "elapsed_ms",
            }:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    continue
            elif key in {"approval_candidate", "filler_played"}:
                if not isinstance(value, bool):
                    continue
            elif not isinstance(value, str):
                continue
            metadata[key] = value[:100] if isinstance(value, str) else value
        self.enqueue({"action": "event", "id": call_id, "organization_id": organization_id,
                      "kind": kind[:80], "stage": stage[:40], "metadata": metadata,
                      "occurred_at": datetime.now(UTC)})

    def message(self, call_id: str, organization_id: str, speaker: str, content: str, *,
                elapsed_ms: int, source_id: str | None, evidence: str,
                retention_days: int) -> None:
        if speaker not in {"caller", "assistant"} or not content.strip():
            return
        if evidence not in {"transcription", "generated_text", "generated_audio_transcript"}:
            return
        now = datetime.now(UTC)
        self.enqueue({"action": "message", "id": call_id, "organization_id": organization_id,
                      "speaker": speaker, "content": content.strip()[:16000],
                      "truncated": len(content.strip()) > 16000,
                      "elapsed_ms": elapsed_ms, "source_id": (source_id or str(uuid4()))[:255],
                      "evidence": evidence, "occurred_at": now,
                      "expires_at": now + timedelta(days=retention_days)})

    def attempt(self, organization_id: str, status: str) -> None:
        if status not in {"ACCEPTED", "CONFIGURATION_INCOMPLETE", "INVALID_TOKEN", "FAILED"}:
            return
        self.enqueue({"action": "attempt", "organization_id": organization_id,
                      "status": status, "occurred_at": datetime.now(UTC)})

    def usage(self, call_id: str, organization_id: str, record: dict[str, Any]) -> None:
        """Queue provider-reported usage after applying a strict value allowlist."""
        allowed = {
            "provider", "engine", "operation", "model", "request_id", "identity_source",
            "usage_type", "input_tokens", "output_tokens", "total_tokens",
            "input_audio_tokens", "output_audio_tokens", "cached_input_tokens", "duration_seconds",
        }
        safe: dict[str, Any] = {}
        for key, value in record.items():
            if key not in allowed:
                continue
            if key in {
                "provider", "engine", "operation", "model", "request_id", "identity_source",
                "usage_type",
            }:
                if isinstance(value, str):
                    safe[key] = value[:120]
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                safe[key] = value
        if not safe.get("request_id") or not safe.get("model") or not safe.get("usage_type"):
            return
        self.enqueue({"action": "usage", "id": call_id, "organization_id": organization_id,
                      "record": safe})

    async def stop(self) -> None:
        if self._worker is None:
            return
        try:
            await asyncio.wait_for(self._queue.join(), timeout=3)
        except TimeoutError:
            logger.warning("voice_observability_shutdown_timeout")
            worker = self._worker
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
            self._worker = None
            return
        await self._queue.put(None)
        try:
            await asyncio.wait_for(self._worker, timeout=3)
        except TimeoutError:
            self._worker.cancel()
        self._worker = None

    async def _run(self) -> None:
        pending: dict[str, Any] | None = None
        while True:
            item = pending if pending is not None else await self._queue.get()
            pending = None
            batch = [item]
            if item is not None and item["action"] == "event":
                # Drain only adjacent events. Identity, messages and usage retain
                # their queue order; no batching delay is added to quiet calls.
                while len(batch) < 64:
                    try:
                        following = self._queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if following is None:
                        batch.append(None)
                        break
                    if following["action"] != "event":
                        pending = following
                        break
                    batch.append(following)
            try:
                if item is None:
                    return
                for attempt in range(3):
                    try:
                        if item["action"] == "start":
                            await self._write_start(item)
                        elif item["action"] == "usage":
                            await self._write_usage(item)
                        elif item["action"] == "message":
                            await self._write_message(item)
                        elif item["action"] == "attempt":
                            await self._write_attempt(item)
                        else:
                            await self._write_events(batch)
                        if batch[-1] is None:
                            return
                        break
                    except Exception:
                        # Database exceptions can embed bound transcript parameters.
                        logger.warning("voice_observability_write_failed",
                                       extra={"attempt": attempt + 1, "action": item["action"]})
                        if attempt == 2:
                            if item["action"] in {"event", "message"}:
                                for failed in batch:
                                    if failed is not None:
                                        await self._mark_incomplete(failed)
                        else:
                            await asyncio.sleep(0.1 * (attempt + 1))
                if batch[-1] is None:
                    return
            finally:
                for _ in batch:
                    self._queue.task_done()

    async def _write_events(self, items: list[dict[str, Any] | None]) -> None:
        """Allocate per-call sequences and persist a bounded batch atomically."""
        now = datetime.now(UTC)
        rows = []
        for position, item in enumerate(items):
            if item is None:
                continue
            metadata = dict(item["metadata"])
            metadata["ingestion_delay_ms"] = max(
                0, round((now - item["occurred_at"]).total_seconds() * 1000)
            )
            rows.append({"position": position, "id": item["id"],
                         "org": item["organization_id"], "kind": item["kind"],
                         "stage": item["stage"], "metadata": metadata,
                         "incomplete": item.get("incomplete", False),
                         "occurred_at": item["occurred_at"].isoformat()})
        async with self._factory() as session:
            await session.execute(text("""
                with incoming as (
                    select * from jsonb_to_recordset(cast(:rows as jsonb)) as x(
                        position integer, id uuid, org uuid, kind text, stage text,
                        metadata jsonb, incomplete boolean, occurred_at timestamptz)
                ), grouped as (
                    select id, org, count(*)::integer as count,
                           max(occurred_at) as latest_at, bool_or(incomplete) as incomplete,
                           max(occurred_at) filter (where kind = 'call_ended') as ended_at,
                           (array_agg(metadata->>'status' order by position desc)
                               filter (where kind = 'call_ended'))[1] as status,
                           (array_agg((metadata->>'elapsed_ms')::integer order by position desc)
                               filter (where kind = 'call_ended'))[1] as elapsed_ms
                      from incoming group by id, org
                ), updated as (
                    update public.voice_observability_calls c
                       set event_count = c.event_count + g.count,
                           last_event_at = greatest(c.last_event_at, g.latest_at),
                           events_complete = c.events_complete and not g.incomplete,
                           status = case when g.ended_at is not null
                               then coalesce(g.status, 'ENDED') else c.status end,
                           ended_at = coalesce(g.ended_at, c.ended_at),
                           duration_ms = case when g.ended_at is not null
                               then coalesce(g.elapsed_ms, greatest(0,
                                   (extract(epoch from (g.ended_at-c.started_at))*1000)::integer))
                               else c.duration_ms end
                      from grouped g where c.id=g.id and c.organization_id=g.org
                    returning c.id, c.organization_id, c.event_count
                ), numbered as (
                    select i.*, row_number() over (
                        partition by id, org order by position) as ordinal
                      from incoming i
                )
                insert into public.voice_observability_events
                    (organization_id, call_id, sequence, event_type, stage,
                     duration_ms, metadata, occurred_at)
                select n.org, n.id, u.event_count-g.count+n.ordinal, n.kind, n.stage,
                       (n.metadata->>'duration_ms')::integer, n.metadata, n.occurred_at
                  from numbered n join updated u on u.id=n.id and u.organization_id=n.org
                  join grouped g on g.id=n.id and g.org=n.org
            """), {"rows": json.dumps(rows)})
            await session.commit()

    async def _mark_incomplete(self, item: dict[str, Any]) -> None:
        try:
            async with self._factory() as session:
                await session.execute(text("""
                    update public.voice_observability_calls set events_complete = false
                     where id = :id and organization_id = :org
                """), {"id": item["id"], "org": item["organization_id"]})
                await session.commit()
        except Exception:
            logger.exception("voice_observability_incomplete_marker_failed")

    async def _write_start(self, item: dict[str, Any]) -> None:
        async with self._factory() as session:
            await session.execute(text("""
                insert into public.voice_observability_calls
                    (id, organization_id, provider, provider_call_id, engine, status,
                     started_at, capture_policy, caller_number, caller_number_source)
                values (:id, :org, 'VOICELINK', :provider_call_id, :engine, 'ACTIVE',
                        :occurred_at, cast(:policy as jsonb), :caller_number,
                        case when cast(:caller_number as text) is not null then 'CARRIER' end)
                on conflict (organization_id, provider, provider_call_id) do nothing
            """), {"id": item["id"], "org": item["organization_id"],
                   "provider_call_id": item["provider_call_id"], "engine": item["engine"],
                   "occurred_at": item["occurred_at"], "caller_number": item.get("caller_number"),
                   "policy": json.dumps({
                       "transcripts": item["transcripts"], "recordings": False,
                       "caller_number": bool(item.get("caller_number"))})})
            await session.commit()

    async def _write_event(self, item: dict[str, Any]) -> None:
        await self._write_events([item])

    async def _write_message(self, item: dict[str, Any]) -> None:
        async with self._factory() as session:
            await session.execute(text("""
                insert into public.voice_observability_messages
                    (organization_id, call_id, speaker, content, evidence, source_id,
                     occurred_at, elapsed_ms, expires_at, truncated)
                select :organization_id, :id, :speaker, :content, :evidence, :source_id,
                       :occurred_at, :elapsed_ms, :expires_at, :truncated
                 where exists (select 1 from public.voice_observability_calls
                                where id = :id and organization_id = :organization_id
                                  and capture_policy ->> 'transcripts' = 'true')
                on conflict (organization_id, call_id, speaker, source_id) do nothing
            """), item)
            await session.commit()

    async def _write_attempt(self, item: dict[str, Any]) -> None:
        async with self._factory() as session:
            await session.execute(text("""
                insert into public.voice_observability_attempts
                    (organization_id, status, occurred_at)
                values (:organization_id, :status, :occurred_at)
            """), item)
            await session.commit()

    async def _write_usage(self, item: dict[str, Any]) -> None:
        record = item["record"]
        async with self._factory() as session:
            params = {key: record.get(key) for key in (
                "provider", "engine", "operation", "model", "request_id", "identity_source",
                "usage_type", "input_tokens", "output_tokens", "total_tokens",
                "input_audio_tokens", "output_audio_tokens", "cached_input_tokens",
                "duration_seconds",
            )}
            await session.execute(text("""
                insert into public.voice_observability_usage
                    (organization_id, call_id, provider, engine, operation, model,
                     request_id, identity_source, usage_type, input_tokens, output_tokens,
                     total_tokens, input_audio_tokens, output_audio_tokens,
                     cached_input_tokens, duration_seconds)
                select :org, :call_id, :provider, :engine, :operation, :model,
                       :request_id, :identity_source, :usage_type, :input_tokens,
                       :output_tokens, :total_tokens, :input_audio_tokens,
                       :output_audio_tokens, :cached_input_tokens, :duration_seconds
                 where exists (select 1 from public.voice_observability_calls
                                where id = :call_id and organization_id = :org)
                on conflict (organization_id, call_id, provider, request_id) do nothing
            """), {"org": item["organization_id"], "call_id": item["id"], **params})
            await session.commit()


capture: VoiceCapture | None = None


def configure(database_url: str | None) -> VoiceCapture | None:
    global capture
    capture = VoiceCapture(database_url) if database_url else None
    if capture:
        capture.start()
    return capture
