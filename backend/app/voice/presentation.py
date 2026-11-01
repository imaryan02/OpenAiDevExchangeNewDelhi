"""Opt-in conference telemetry. Never awaits, stores audio, or changes a call.

The bounded process-local store matches the single-worker deployment. A restart
intentionally clears traces. Only explicitly enrolled demo callers are captured.
"""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.core.config import Settings

TOOLS = {
    "lookup_caller_family": "Looking up caller context",
    "search_availability": "Checking available sessions",
    "suggest_department": "Finding a department",
    "get_clinic_information": "Reading clinic information",
    "prepare_booking_offer": "Preparing appointment details",
    "confirm_booking_offer": "Confirming the appointment",
    "list_upcoming_appointments": "Finding existing appointments",
    "cancel_appointment": "Checking cancellation",
    "reschedule_appointment": "Checking a new session",
    "start_phone_verification": "Starting verification",
    "verify_phone_code": "Checking verification",
    "prepare_cancel_appointment": "Preparing cancellation preview",
    "prepare_reschedule_appointment": "Preparing reschedule preview",
}
MUTATIONS = {"confirm_booking_offer", "cancel_appointment", "reschedule_appointment"}


def redact(value: str) -> str:
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email hidden]", value)
    value = re.sub(r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b", "[ID hidden]", value)
    value = re.sub(r"\+?\d[\d\s().-]{5,}\d", "[number hidden]", value)
    return value[:700]


class PresentationStore:
    def __init__(self, max_calls: int = 20, max_events: int = 600, ttl: float = 3600) -> None:
        self.calls: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.max_calls, self.max_events, self.ttl = max_calls, max_events, ttl

    def prune(self) -> None:
        cutoff = time.time() - self.ttl
        for key in list(self.calls):
            if self.calls[key]["updated_at"] < cutoff:
                del self.calls[key]

    def start(self, organization_id: str, engine: str) -> str:
        self.prune()
        key = str(uuid4())
        self.calls[key] = {
            "id": key, "organization_id": organization_id, "engine": engine,
            "started_at": time.time(), "updated_at": time.time(),
            "ended": False, "events": [], "sequence": 0,
        }
        while len(self.calls) > self.max_calls:
            self.calls.popitem(last=False)
        return key

    def append(self, key: str, kind: str, stage: str, title: str, **data: Any) -> None:
        call = self.calls.get(key)
        if call is None:
            return
        now = time.time()
        call["sequence"] += 1
        call["updated_at"] = now
        call["events"].append({
            "sequence": call["sequence"], "at_ms": round((now - call["started_at"]) * 1000),
            "kind": kind, "stage": stage, "title": title, **data,
        })
        del call["events"][:-self.max_events]
        if kind == "call_ended":
            call["ended"] = True

    def list_for(self, organization_id: str) -> list[dict[str, Any]]:
        self.prune()
        return [
            {k: v for k, v in call.items() if k not in {"events", "organization_id"}}
            for call in reversed(self.calls.values()) if call["organization_id"] == organization_id
        ]

    def get(self, key: str, organization_id: str) -> dict[str, Any] | None:
        self.prune()
        call = self.calls.get(key)
        return call if call and call["organization_id"] == organization_id else None


store = PresentationStore()


@dataclass
class Scope:
    settings: Settings
    key: str | None = None
    call_id: str | None = None
    organization_id: str | None = None
    terminal_status: str = "ENDED"
    trace_manager: Any = None
    transfer_times: dict[str, float] = field(default_factory=dict)
    transfer_counts: dict[str, int] = field(default_factory=dict)
    response_text: str = ""
    engine: str = "CHAINED"
    started_monotonic: float = field(default_factory=time.monotonic)


current: ContextVar[Scope | None] = ContextVar("conference_trace", default=None)
tool_context: ContextVar[tuple[str, str]] = ContextVar("conference_tool", default=("", "engine"))
operation_context: ContextVar[str] = ContextVar("conference_operation", default="")
correlation_context: ContextVar[dict[str, str | int] | None] = ContextVar(
    "voice_correlation", default=None
)
CORRELATION_KEYS = {
    "caller_turn_id", "caller_item_id", "assistant_item_id", "response_id",
    "provider_tool_call_id", "generation_id", "playback_segment_id", "proposal_id",
    "durable_operation_id",
}


@contextmanager
def correlation_scope(**fields: Any) -> Iterator[None]:
    """Propagate captured identifiers into async children without cross-task mutation."""
    values = dict(correlation_context.get() or {})
    for key, value in fields.items():
        if key not in CORRELATION_KEYS:
            continue
        if value is None:
            values.pop(key, None)
        elif key in {"caller_turn_id", "generation_id"}:
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                values[key] = value
        elif isinstance(value, str) and value:
            values[key] = value[:100]
    token = correlation_context.set(values)
    try:
        yield
    finally:
        correlation_context.reset(token)


@contextmanager
def tool_scope(name: str, origin: str) -> Iterator[None]:
    safe_name = name if name in TOOLS else "controlled_tool"
    safe_origin = origin if origin in {"backend", "engine", "voice"} else "other"
    token = tool_context.set((safe_name, safe_origin))
    operation_token = operation_context.set(uuid4().hex[:12])
    try:
        from app.observability.telemetry import span_scope
        with span_scope("voice.tool", {"tool.name": safe_name, "tool.origin": safe_origin}):
            yield
    finally:
        operation_context.reset(operation_token)
        tool_context.reset(token)


@contextmanager
def presentation_scope(settings: Settings) -> Iterator[None]:
    scope = Scope(settings)
    token = current.set(scope)
    try:
        yield
    except BaseException:
        scope.terminal_status = "INTERRUPTED"
        raise
    finally:
        emit("call_ended", "caller", "Call ended", status=scope.terminal_status)
        if scope.trace_manager is not None:
            from app.observability.telemetry import finish_voice_call
            finish_voice_call(scope.terminal_status)
            scope.trace_manager.__exit__(None, None, None)
        current.reset(token)


def start_call(caller: str, engine: str, provider_call_id: str | None = None) -> None:
    scope = current.get()
    if scope is None or scope.key or scope.call_id or scope.trace_manager is not None:
        return
    scope.engine = engine.upper()
    if scope.settings.voice_organization_id and provider_call_id:
        from app.observability.telemetry import start_voice_call
        scope.trace_manager = start_voice_call(engine)
        scope.trace_manager.__enter__()
    if not scope.call_id and scope.settings.voice_organization_id and provider_call_id:
        from app.observability.capture import capture
        if capture:
            scope.call_id = capture.start_call(
                str(scope.settings.voice_organization_id), provider_call_id, engine,
                transcripts=scope.settings.voice_transcript_capture_enabled, caller_number=caller,
            )
            scope.started_monotonic = time.monotonic()
            scope.organization_id = str(scope.settings.voice_organization_id)
    if (not scope.settings.presentation_enabled
            or caller not in scope.settings.presentation_demo_callers
            or scope.settings.voice_organization_id is None):
        if scope.call_id:
            from app.observability.telemetry import current_trace_id
            emit("call_started", "carrier", "Authenticated call connected",
                 trace_id=current_trace_id())
        return
    scope.key = store.start(str(scope.settings.voice_organization_id), engine)
    from app.observability.telemetry import current_trace_id
    emit("call_started", "carrier", "Authenticated call connected", trace_id=current_trace_id())
    emit("identity_received", "identity", "Mobile identity received from VoiceLink",
         details={"mobile": "Enrolled mobile · hidden", "source": "Authenticated carrier metadata"})


def record_usage(record: dict[str, Any]) -> None:
    scope = current.get()
    if not scope or not scope.call_id or not scope.organization_id:
        return
    from app.observability.capture import capture
    if capture:
        capture.usage(scope.call_id, scope.organization_id, {
            "provider": "OPENAI", "engine": scope.engine, **record,
        })


def emit(kind: str, stage: str, title: str, **data: Any) -> None:
    for key, value in (correlation_context.get() or {}).items():
        if data.get(key) is None:
            data[key] = value
    scope = current.get()
    name, origin = tool_context.get()
    if name:
        data.setdefault("tool", name)
        data.setdefault("origin", origin)
    invocation_id = operation_context.get()
    if invocation_id:
        data.setdefault("tool_invocation_id", invocation_id)
        # Keep the existing conference contract while separating durable tool IDs.
        data.setdefault("operation_id", invocation_id)
    if scope:
        data.setdefault("elapsed_ms", round((time.monotonic() - scope.started_monotonic) * 1000))
    from app.observability.telemetry import add_voice_event
    add_voice_event(kind, stage, data)
    if scope and scope.call_id and scope.organization_id:
        from app.observability.capture import capture
        if capture:
            capture.event(scope.call_id, scope.organization_id, kind, stage, data)
    if scope and scope.key:
        store.append(scope.key, kind, stage, title, **data)


def dialogue(speaker: str, text: str, *, source_id: str | None = None,
             evidence: str | None = None) -> None:
    # Use the same identity for the separate retained message and its safe event.
    source_id = source_id or str(uuid4())
    scope = current.get()
    if (scope and scope.settings.voice_transcript_capture_enabled
            and scope.call_id and scope.organization_id):
        from app.observability.capture import capture
        if capture:
            capture.message(
                scope.call_id, scope.organization_id, speaker, text,
                elapsed_ms=round((time.monotonic() - scope.started_monotonic) * 1000),
                source_id=source_id,
                evidence=evidence or ("transcription" if speaker == "caller" else "generated_text"),
                retention_days=scope.settings.voice_transcript_retention_days,
            )
    emit("dialogue", "caller" if speaker == "caller" else "voice",
         "Caller transcript" if speaker == "caller" else "Assistant response",
         speaker=speaker,
         message_source_id=source_id,
         text=(redact(text) if (scope and scope.settings.presentation_show_transcripts)
               else "Transcript hidden in live view"))


def available_tools(names: list[str]) -> None:
    emit("tools_available", "voice", "Voice engine tools configured",
         tools=[name for name in names if name in TOOLS])


def selected_tool(name: str) -> None:
    emit("tool_selected", "voice", "Engine requested a tool",
         tool=name if name in TOOLS else "unavailable_tool")


def audio_transfer(direction: str, size: int, *, boundary: str = "engine") -> None:
    """Sample actual transport boundaries; never retain audio or emit fake waveforms."""
    scope = current.get()
    if scope is None or not (scope.key or scope.call_id) or size <= 0:
        return
    now = time.monotonic()
    scope.transfer_counts[direction] = scope.transfer_counts.get(direction, 0) + 1
    if now - scope.transfer_times.get(direction, 0) < 1.5:
        return
    scope.transfer_times[direction] = now
    title = ("Caller audio received by gateway" if boundary == "gateway"
             else "Caller audio forwarded to engine")
    emit("audio_transferred", "carrier", title
         if direction == "input" else "Response audio sent to VoiceLink",
         direction=direction,
         details={"chunks": scope.transfer_counts[direction], "boundary": boundary})


def response_fragment(delta: str, *, reset: bool = False) -> None:
    scope = current.get()
    if scope is None or not scope.key:
        return
    if reset:
        scope.response_text = ""
        return
    if not scope.settings.presentation_show_transcripts:
        return
    scope.response_text = (scope.response_text + delta)[:700]
    now = time.monotonic()
    if now - scope.transfer_times.get("text", 0) < 0.4:
        return
    scope.transfer_times["text"] = now
    emit("response_fragment", "voice", "Receiving response transcript from Realtime",
         speaker="assistant", text=redact(scope.response_text))


def voice_event(kind: str, **fields: Any) -> None:
    mapping = {
        "caller_turn_captured": ("caller", "Caller turn captured"),
        "caller_turn_dequeued": ("transcription", "Transcribing caller audio"),
        "transcription_completed": ("transcription", "Caller transcription completed"),
        "generation_started": ("voice", "Response audio started"),
        "generation_completed": ("voice", "Response audio generated"),
        "playback_started": ("voice", "Response audio sent"),
        "playback_acknowledged": ("voice", "Carrier acknowledged playback"),
        "playback_interrupted": ("caller", "Caller interrupted playback"),
        "error": ("tools", "Operation needs attention"),
    }
    if kind in mapping:
        stage, title = mapping[kind]
        emit(kind, stage, title, **fields)


def safe_result(result: dict[str, object]) -> dict[str, object]:
    """Never forward arbitrary arguments, error messages, or patient records."""
    safe: dict[str, object] = {}
    for key in ("status", "booking_reference", "token_number", "payment_status",
                "replacement_reference", "replacement_token"):
        value = result.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            safe[key] = redact(value) if isinstance(value, str) else value
    for key in ("sessions", "options", "appointments"):
        rows = result.get(key)
        if isinstance(rows, list):
            safe["result_count"] = len(rows)
    offer = result.get("offer")
    if isinstance(offer, dict):
        for key in ("doctor_name", "session_date", "session_time", "currency", "fee_minor"):
            value = offer.get(key)
            if isinstance(value, (str, int)):
                safe[key] = redact(value) if isinstance(value, str) else value
    return safe


def safe_arguments(arguments: dict[str, object]) -> dict[str, object]:
    """Expose only presentation-safe scheduling fields, never arbitrary tool input."""
    aliases = {
        "doctor_name": ("doctor_name", "requested_doctor", "doctor"),
        "department_name": ("department_name", "requested_department", "department"),
        "session_date": ("session_date", "requested_date", "date"),
        "session_time": ("session_time", "requested_time", "time"),
        "topic": ("topic",),
    }
    safe: dict[str, object] = {}
    for canonical, keys in aliases.items():
        value = next((arguments.get(key) for key in keys if arguments.get(key) is not None), None)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            safe[canonical] = redact(value) if isinstance(value, str) else value
    return safe


def committed(name: str, result: dict[str, object]) -> None:
    if (name in MUTATIONS and result.get("ok") is True
            and not result.get("already_cancelled") and not result.get("already_scheduled")
            and result.get("status") not in {"CANCEL_PREVIEW", "RESCHEDULE_PREVIEW"}):
        emit("committed", "database", "Appointment transaction committed",
             tool=name, details=safe_result(result))
