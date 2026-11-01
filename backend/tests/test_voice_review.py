"""Regression tests for opt-in text, content isolation, timing, and audited reads."""
import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Response

from app.api.routes import voice_observability as api
from app.core.config import Settings
from app.core.errors import ApiError
from app.observability import capture as capture_module
from app.observability.capture import VoiceCapture
from app.security.auth import Principal
from app.voice import presentation as p


@pytest.fixture
def capture(monkeypatch):
    monkeypatch.setattr(capture_module, "get_session_factory", lambda _: None)
    collector = VoiceCapture("unused")
    monkeypatch.setattr(capture_module, "capture", collector)
    return collector


def test_capture_is_opt_in_and_technical_events_never_include_text(capture):
    settings = Settings.model_construct(voice_organization_id=uuid4(),
                                        voice_transcript_capture_enabled=False)
    with p.presentation_scope(settings):
        p.start_call("private phone", "chained", "provider-id")
        p.dialogue("caller", "Private medical history")
    rows = list(capture._queue._queue)
    assert not any(row["action"] == "message" for row in rows)
    assert "Private medical history" not in str(rows)
    assert rows[0]["transcripts"] is False


def test_enabled_chat_is_separate_from_correlated_telemetry(capture):
    settings = Settings.model_construct(voice_organization_id=uuid4(),
                                        voice_transcript_capture_enabled=True)
    with p.presentation_scope(settings):
        p.start_call("private phone", "realtime", "provider-id")
        with p.tool_scope("lookup_caller_family", "backend"):
            p.emit("database_completed", "database", "Finished", query_id="query-1",
                   details={"duration_ms": 21}, arguments={"phone": "private phone"})
        p.dialogue("caller", "मुझे अपॉइंटमेंट चाहिए", source_id="item-1")
    rows = list(capture._queue._queue)
    message = next(row for row in rows if row["action"] == "message")
    assert message["content"] == "मुझे अपॉइंटमेंट चाहिए"
    assert message["evidence"] == "transcription"
    assert (message["expires_at"] - message["occurred_at"]).days == 7
    event = next(row for row in rows if row.get("kind") == "database_completed")
    assert event["metadata"]["tool_invocation_id"]
    assert event["metadata"]["query_id"] == "query-1"
    assert event["metadata"]["elapsed_ms"] >= 0
    assert event["occurred_at"].tzinfo is UTC
    assert "private phone" not in str(rows)
    assert not any("content" in row.get("metadata", {}) for row in rows)


@pytest.mark.asyncio
async def test_async_tool_correlations_are_isolated_and_chat_has_matching_source(capture):
    settings = Settings.model_construct(voice_organization_id=uuid4(),
                                        voice_transcript_capture_enabled=True)

    async def child(turn, response):
        with p.correlation_scope(caller_turn_id=turn, response_id=response,
                                 provider_tool_call_id=f"tool-{turn}", private_token="secret"):
            await asyncio.sleep(0)
            with p.tool_scope("search_availability", "engine"):
                p.emit("tool_started", "tools", "Searching")
            p.dialogue("assistant", "Test response")

    with p.presentation_scope(settings):
        p.start_call("not-a-phone", "realtime", "provider-id")
        await asyncio.gather(child(1, "response-a"), child(2, "response-b"))
        p.emit("identity_received", "identity", "Outside child tasks")
    rows = list(capture._queue._queue)
    tools = [row["metadata"] for row in rows if row.get("kind") == "tool_started"]
    assert {(row["caller_turn_id"], row["response_id"]) for row in tools} == {
        (1, "response-a"), (2, "response-b")}
    assert all(row["tool_invocation_id"] and row["provider_tool_call_id"] for row in tools)
    messages = [row for row in rows if row["action"] == "message"]
    dialogue = [row["metadata"] for row in rows if row.get("kind") == "dialogue"]
    assert {row["source_id"] for row in messages} == {
        row["message_source_id"] for row in dialogue}
    outside = next(row for row in rows if row.get("kind") == "identity_received")
    assert "response_id" not in outside["metadata"]
    assert "secret" not in str(rows)


def test_message_limits_and_unknown_attempts(capture):
    capture.message("call", "org", "caller", "x" * 17000, elapsed_ms=3,
                    source_id="stable-id", evidence="transcription", retention_days=7)
    row = capture._queue.get_nowait()
    assert len(row["content"]) == 16000 and row["truncated"] is True
    capture.attempt("org", "arbitrary-token")
    assert capture._queue.empty()


class Result:
    def __init__(self, *, first=None, scalar=None, rows=()):
        self.first_value, self.scalar_value, self.rows = first, scalar, rows

    def first(self):
        return self.first_value

    def scalar_one(self):
        return self.scalar_value

    def scalar_one_or_none(self):
        return self.scalar_value

    def __iter__(self):
        return iter(self.rows)


class Session:
    def __init__(self, results, *, fail_commit=False):
        self.results = iter(results)
        self.queries = []
        self.committed = False
        self.fail_commit = fail_commit

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def execute(self, sql, params=None):
        self.queries.append((str(sql), params))
        return next(self.results)

    async def commit(self):
        if self.fail_commit:
            raise RuntimeError("audit unavailable")
        self.committed = True


def setup_api(monkeypatch, session):
    monkeypatch.setattr(api, "get_settings", lambda: SimpleNamespace(database_url="unused", voice_transcript_capture_enabled=False))
    monkeypatch.setattr(api, "get_session_factory", lambda _: lambda: session)


@pytest.mark.asyncio
async def test_conversation_not_found_does_not_read_other_tenant(monkeypatch):
    session = Session([Result()])
    setup_api(monkeypatch, session)
    with pytest.raises(ApiError) as exc:
        await api.conversation(uuid4(), Response(), "tenant", Principal(uuid4(), None), 0, 100)
    assert exc.value.status_code == 404
    assert len(session.queries) == 1
    assert session.queries[0][1]["org"] == "tenant"


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_commit", [False, True])
async def test_text_read_is_expiry_filtered_paginated_and_audited(monkeypatch, fail_commit):
    def row(seq):
        return SimpleNamespace(_mapping={"sequence": seq, "content": "private text"})
    session = Session([Result(first=SimpleNamespace(capture_policy={"transcripts": True})),
                       Result(scalar=True), Result(rows=[row(2), row(3)]), Result()],
                      fail_commit=fail_commit)
    setup_api(monkeypatch, session)
    response = Response()
    args = (uuid4(), response, "tenant", Principal(uuid4(), None), 1, 1)
    if fail_commit:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            await api.conversation(*args)
    else:
        payload = await api.conversation(*args)
        assert session.committed
        assert response.headers["Cache-Control"] == "no-store"
        assert payload["next_sequence"] == 2
        assert len(payload["messages"]) == 1
    sql, params = session.queries[2]
    assert "expires_at > now()" in sql and "organization_id = :org" in sql
    assert "source_id" in sql
    assert params["after"] == 1 and params["limit"] == 2
    assert session.queries[3][1]["count"] == 1


@pytest.mark.asyncio
async def test_detail_reports_loaded_telemetry_delay_and_runtime_disagreement(monkeypatch):
    call = SimpleNamespace(provider_call_id="private-provider",
                           _mapping={"id": uuid4(), "provider_call_id": "private-provider",
                                     "status": "ACTIVE", "events_complete": True,
                                     "last_event_at": datetime(2026, 1, 1, tzinfo=UTC)})
    runtime = SimpleNamespace(id=uuid4(), status="ENDED")
    event = SimpleNamespace(_mapping={"sequence": 1, "event_type": "readback_failed",
                                      "stage": "consent", "metadata": {
                                          "ingestion_delay_ms": 12000,
                                          "response_id": "response", "trace_id": "trace"}})
    session = Session([Result(first=call), Result(first=runtime), Result(),
                       Result(rows=[event]), Result()])
    setup_api(monkeypatch, session)
    payload = await api.get_call(call._mapping["id"], Response(), "tenant", 0, 500)
    health = payload["collection_health"]
    assert health["max_loaded_ingestion_delay_ms"] == 12000
    assert health["lifecycle_status_disagrees"] is True
    assert health["event_page_partial"] is False
    assert health["loaded_event_count"] == 1
    assert payload["trace_available"] is True
    assert payload["events"][0]["metadata"] == {
        "ingestion_delay_ms": 12000, "response_id": "response"}
    assert "private-provider" not in str(payload)


@pytest.mark.asyncio
async def test_writer_retains_emission_time_and_monotonic_duration(monkeypatch, capture):
    session = Session([Result()])
    capture._factory = lambda: session
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    await capture._write_event({"action": "event", "id": "call", "organization_id": "org",
                               "kind": "call_ended", "stage": "caller",
                               "occurred_at": timestamp, "metadata": {"elapsed_ms": 15000}})
    stored = json.loads(session.queries[0][1]["rows"])[0]
    assert stored["occurred_at"] == timestamp.isoformat()
    assert stored["metadata"]["elapsed_ms"] == 15000
    assert stored["metadata"]["ingestion_delay_ms"] > 0



@pytest.mark.asyncio
async def test_writer_batches_events_without_crossing_message_boundaries(capture):
    persisted = []

    async def events(items):
        persisted.append([item["number"] for item in items if item is not None])

    async def message(item):
        persisted.append(item["number"])

    capture._write_events = events
    capture._write_message = message
    for number in range(70):
        capture.enqueue({"action": "event", "number": number})
    capture.enqueue({"action": "message", "number": "chat"})
    capture.enqueue({"action": "event", "number": 70})
    capture.start()
    await asyncio.wait_for(capture._queue.join(), timeout=2)
    await capture.stop()
    assert persisted == [list(range(64)), list(range(64, 70)), "chat", [70]]


@pytest.mark.asyncio
async def test_failed_batch_retries_and_marks_every_affected_call(capture):
    capture._write_events = AsyncMock(side_effect=RuntimeError("unavailable"))
    capture._mark_incomplete = AsyncMock()
    for call in ("a", "b"):
        capture.enqueue({"action": "event", "id": call})
    capture.start()
    await asyncio.wait_for(capture._queue.join(), timeout=2)
    await capture.stop()
    assert capture._write_events.await_count == 3
    assert [args.args[0]["id"] for args in capture._mark_incomplete.await_args_list] == ["a", "b"]


@pytest.mark.asyncio
async def test_bulk_writer_uses_one_transaction_and_preserves_occurrence_time(capture):
    session = Session([Result()])
    capture._factory = lambda: session
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    await capture._write_events([
        {"id": "call", "organization_id": "org", "kind": kind,
         "stage": "voice", "metadata": {"elapsed_ms": ms}, "occurred_at": timestamp}
        for kind, ms in (("speech_started", 20), ("call_ended", 15000))
    ])
    assert len(session.queries) == 1 and session.committed
    rows = json.loads(session.queries[0][1]["rows"])
    assert [row["position"] for row in rows] == [0, 1]
    assert rows[-1]["metadata"]["elapsed_ms"] == 15000
    assert rows[0]["occurred_at"] == timestamp.isoformat()


def test_trusted_caller_number_is_stored_only_on_summary(capture):
    number = "+919800000001"
    settings = Settings.model_construct(voice_organization_id=uuid4())
    with p.presentation_scope(settings):
        p.start_call(number, "chained", "trusted-call")
        p.emit("identity_received", "identity", "Identity", caller_number=number)
    rows = list(capture._queue._queue)
    assert rows[0]["caller_number"] == number
    assert all(number not in str(row["metadata"]) for row in rows if row["action"] == "event")


@pytest.mark.asyncio
async def test_caller_search_is_tenant_scoped_and_numbers_are_not_in_sql(monkeypatch):
    session = Session([Result()])
    setup_api(monkeypatch, session)
    response = Response()
    filters = api.CallSearch(phone_search="(+91) 98000-00001",
                             caller_number="+919800000001", offset=50)
    await api.search_calls(filters, response, "tenant-a")
    sql, params = session.queries[0]
    assert "history.organization_id = :org" in sql
    assert "where organization_id = :org" in sql
    assert "+919800000001" not in sql
    assert params["org"] == "tenant-a"
    assert params["caller_number"] == "+919800000001"
    assert params["phone_pattern"] == "%919800000001%"
    assert params["offset"] == 50
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("value", ["123", "unknown", "%", "1234 OR 1=1"])
def test_invalid_phone_search_does_not_match_every_caller(value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        api.CallSearch(phone_search=value)


@pytest.mark.asyncio
async def test_other_clinic_caller_history_is_denied(monkeypatch):
    own_org = uuid4()
    async def memberships(user_id):
        return [SimpleNamespace(organization_id=own_org, role="RECEPTIONIST")]
    monkeypatch.setattr(api, "list_active_memberships", memberships)
    with pytest.raises(ApiError) as exc:
        await api.authorize(uuid4(), Principal(uuid4(), None))
    assert exc.value.status_code == 403
