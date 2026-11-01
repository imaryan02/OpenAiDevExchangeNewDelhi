"""VoiceLink's A-law media stream bridged to one OpenAI Realtime session per call."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from fastapi import WebSocket
from sqlalchemy import text

from app.agent.tools import TOOLS, ToolExecutor
from app.core.config import Settings
from app.db.session import get_session_factory
from app.integrations.openai_audio import OpenAIAudioClient
from app.integrations.openai_realtime import OpenAIRealtimeSession
from app.voice import presentation
from app.voice.call_runtime import VoiceCallRuntime
from app.voice.caller_items import CallerItems
from app.voice.codec import Pcm24kToAlaw8k, alaw8k_to_pcm24k
from app.voice.confirmation_intent import ConfirmationIntent, ConfirmationIntentClassifier
from app.voice.events import VoiceEvent, VoiceEventType
from app.voice.gateway import VoiceProtocolError
from app.voice.readback import ReadbackPlaybackLedger
from app.voice.readback_player import ControlledReadbackPlayer
from app.voice.realtime_policy import receptionist_instructions
from app.voice.voicelink_gateway import (
    VoiceLinkVoiceGateway,
    _is_outbound_media,
    _normalize_e164_phone,
    _phone_digits,
)

logger = structlog.get_logger()


def _event_identifiers(event: dict[str, Any]) -> dict[str, Any]:
    """Only use provider-supplied links, never the latest turn by time proximity."""
    kind = str(event.get("type") or "")
    response = event.get("response")
    response_id = event.get("response_id")
    if isinstance(response, dict):
        response_id = response.get("id") or response_id
    values: dict[str, Any] = {"response_id": response_id}
    item = event.get("item")
    item_id = event.get("item_id")
    if isinstance(item, dict):
        item_id = item.get("id") or item_id
        if item.get("type") == "function_call":
            values["provider_tool_call_id"] = item.get("call_id")
    if kind.startswith("input_audio_buffer.") or kind.startswith(
        "conversation.item.input_audio_transcription."
    ):
        values["caller_item_id"] = item_id
    elif kind.startswith("response."):
        values["assistant_item_id"] = item_id
    return values

READ_ONLY_TOOL_NAMES = {
    "get_clinic_information",
    "search_availability",
    "suggest_department",
}
READ_ONLY_TOOLS: list[dict[str, object]] = [
    tool for tool in TOOLS if str(tool.get("name")) in READ_ONLY_TOOL_NAMES
]
_RELATIONSHIP_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("MOTHER", re.compile(r"\b(?:mother|mom|mummy|mumma|maa|ma)\b", re.IGNORECASE)),
    ("FATHER", re.compile(r"\b(?:father|dad|papa|papa ji)\b", re.IGNORECASE)),
    ("SPOUSE", re.compile(r"\b(?:wife|husband|spouse|patni|pati)\b", re.IGNORECASE)),
    ("CHILD", re.compile(r"\b(?:son|daughter|child|beta|beti)\b", re.IGNORECASE)),
    ("OTHER", re.compile(r"\b(?:sister|brother|behen|bhai|aunt|uncle|friend)\b", re.IGNORECASE)),
    ("SELF", re.compile(r"\b(?:for me|myself|mere liye|mere naam se)\b", re.IGNORECASE)),
)
UPCOMING_APPOINTMENTS_TOOL: dict[str, object] = {
    "type": "function",
    "name": "list_upcoming_appointments",
    "strict": True,
    "description": (
        "List upcoming appointments for the authenticated inbound caller. "
        "The server supplies the caller phone number; never ask for it."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    },
}
BOOKING_OFFER_TOOL: dict[str, object] = {
    "type": "function", "name": "prepare_booking_offer", "strict": True,
    "description": "Prepare an appointment offer only after all listed details are known. The server reads it back and controls confirmation.",
    "parameters": {"type": "object", "additionalProperties": False, "properties": {
        "caller_name": {"type": ["string", "null"]},
        "patient_name": {"type": "string"}, "relationship": {"type": "string"},
        "session_id": {"type": "string"}, "slot_id": {"type": ["string", "null"]},
        "language": {"type": "string"}, "create_patient_if_missing": {"type": "boolean"},
        "create_caller_if_missing": {"type": "boolean"},
    }, "required": ["caller_name", "patient_name", "relationship", "session_id", "slot_id", "language", "create_patient_if_missing", "create_caller_if_missing"]},
}
CONSEQUENTIAL_PREVIEW_TOOLS: list[dict[str, object]] = [
    {"type": "function", "name": "prepare_cancel_appointment", "strict": True,
     "description": "Validate a cancellation and let the server read it back before consent.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "booking_reference": {"type": "string"}, "reason": {"type": "string"},
     }, "required": ["booking_reference", "reason"]}},
    {"type": "function", "name": "prepare_reschedule_appointment", "strict": True,
     "description": "Validate a reschedule target and let the server read it back before consent.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "booking_reference": {"type": "string"}, "new_session_id": {"type": "string"},
         "new_slot_id": {"type": ["string", "null"]},
     }, "required": ["booking_reference", "new_session_id", "new_slot_id"]}},
]


class VoiceLinkRealtimeGateway:
    """Audio-only Realtime bridge with carrier-backed playback and interruption evidence."""

    def __init__(
        self,
        settings: Settings,
        realtime: OpenAIRealtimeSession | None = None,
        audio: OpenAIAudioClient | None = None,
    ) -> None:
        self._settings = settings
        self._realtime = realtime or OpenAIRealtimeSession(settings)
        self._websocket: WebSocket | None = None
        self._clinic_name = settings.voice_clinic_name or "Geeta Medicine"
        self._stream_sid = ""
        self._send_lock = asyncio.Lock()
        self._active_mark = ""
        self._active_item_id = ""
        self._active_response_id = ""
        self._active_content_index = 0
        self._played_alaw_bytes = 0
        self._generation_id = 0
        self._audio = audio or OpenAIAudioClient(settings)
        self._readback_player = ControlledReadbackPlayer(ReadbackPlaybackLedger(), self._audio)
        self._controlled_readback_id = ""
        self._controlled_readback_links: dict[str, str | int] = {}
        self._runtime_database_session: Any = None
        self._runtime: VoiceCallRuntime | None = None
        self._caller_items = CallerItems()
        self._discarded_items: set[str] = set()
        self._output_converter = Pcm24kToAlaw8k()
        self._caller_epoch = 0
        self._tool_tasks: set[asyncio.Task[None]] = set()
        self._tool_calls: set[str] = set()
        self._playback_queue: asyncio.Queue[tuple[int, int, dict[str, Any]]] = asyncio.Queue(maxsize=128)
        self._queued_audio_bytes = 0
        self._pending_booking: tuple[str, str] | None = None
        self._pending_operation: tuple[str, str, str, dict[str, object]] | None = None
        self._readback_acknowledged = False
        self._confirmation_classifier = ConfirmationIntentClassifier(settings)
        self._confirmation_readback = ""
        self._latest_stated_relationship: str | None = None
        self._caller_drain_lock = asyncio.Lock()
        self._readback_timeout_task: asyncio.Task[None] | None = None

    async def _voice_instructions(self, caller_phone: str | None = None) -> str:
        """Use the configured organization as the authoritative call identity."""
        clinic_name = self._clinic_name
        timezone: str | None = None
        if self._runtime_database_session is not None and self._settings.voice_organization_id:
            try:
                result = await self._runtime_database_session.execute(
                    text(
                        "select name, timezone from public.organizations "
                        "where id=:organization_id and status='ACTIVE'"
                    ),
                    {"organization_id": self._settings.voice_organization_id},
                )
                row = result.mappings().one_or_none()
                if row is not None:
                    clinic_name = str(row["name"]).strip() or clinic_name
                    timezone = str(row["timezone"]).strip() or None
            except Exception:
                logger.warning(
                    "voice_clinic_context_unavailable",
                    organization_id=str(self._settings.voice_organization_id),
                )
        self._clinic_name = clinic_name or "Geeta Medicine"
        local_time: str | None = None
        if timezone:
            try:
                local_time = datetime.now(ZoneInfo(timezone)).strftime("%A, %d %B %Y, %I:%M %p")
            except ZoneInfoNotFoundError:
                logger.warning("voice_clinic_timezone_invalid", timezone=timezone)
        caller_profile: dict[str, object] | None = None
        if (
            caller_phone
            and self._runtime_database_session is not None
            and self._settings.voice_organization_id
            and self._settings.voice_actor_id
        ):
            try:
                with presentation.tool_scope("lookup_caller_family", "backend"):
                    caller_profile = await ToolExecutor(
                        session=self._runtime_database_session,
                        organization_id=self._settings.voice_organization_id,
                        actor_id=self._settings.voice_actor_id,
                        settings=self._settings,
                        caller_phone_e164=caller_phone,
                    ).execute("lookup_caller_family", {"phone_e164": caller_phone})
            except Exception:
                logger.warning("voice_caller_context_unavailable")
        return receptionist_instructions(
            clinic_name,
            timezone=timezone,
            local_time=local_time,
            pronunciation_guidance=self._settings.voice_pronunciation_guidance,
            caller_profile=caller_profile,
        )

    async def run(
        self, websocket: WebSocket, *, initial_message: dict[str, Any] | None = None
    ) -> None:
        context: dict[str, str] | None = None
        relay: asyncio.Task[None] | None = None
        try:
            while True:
                if initial_message is not None:
                    message = initial_message
                    initial_message = None
                elif relay is None:
                    message = await websocket.receive_json()
                else:
                    incoming = asyncio.create_task(websocket.receive_json())
                    try:
                        done, _ = await asyncio.wait({incoming, relay}, return_when=asyncio.FIRST_COMPLETED)
                        if relay in done:
                            await relay
                            raise VoiceProtocolError("Realtime output stream ended.")
                        message = incoming.result()
                    finally:
                        if not incoming.done():
                            incoming.cancel()
                        await asyncio.gather(incoming, return_exceptions=True)
                event = str(message.get("event", ""))
                if event == "connected":
                    continue
                if event == "start":
                    if context is not None:
                        raise VoiceProtocolError("Duplicate stream start event.")
                    context = self._validate_start(message)
                    canaries = self._settings.voice_realtime_canary_callers
                    if canaries and context["caller"] not in canaries:
                        # Select once from authenticated carrier metadata, before
                        # opening Realtime or creating durable Realtime call state.
                        context = None
                        await VoiceLinkVoiceGateway(self._settings).run(websocket, initial_message=message)
                        return
                    if not self._settings.realtime_configured:
                        raise VoiceProtocolError("OpenAI Realtime is not configured.")
                    presentation.start_call(context["caller"], "realtime", context["call_sid"])
                    assert self._settings.database_url is not None
                    assert self._settings.voice_organization_id is not None
                    runtime_factory = get_session_factory(self._settings.database_url)
                    self._runtime_database_session = runtime_factory()
                    await self._runtime_database_session.__aenter__()
                    self._runtime = VoiceCallRuntime(
                        self._runtime_database_session, self._settings.voice_organization_id
                    )
                    await self._runtime.start(
                        provider_call_id=context["call_sid"], caller_phone=context["caller"]
                    )
                    self._stream_sid = context["stream_sid"]
                    self._websocket = websocket
                    await self._realtime.connect()
                    created = await asyncio.wait_for(
                        self._realtime.receive_event(),
                        timeout=self._settings.openai_realtime_connect_timeout_seconds,
                    )
                    if created.get("type") != "session.created":
                        raise VoiceProtocolError("OpenAI Realtime did not create a session.")
                    await self._realtime.configure_voice_session(
                        await self._voice_instructions(context["caller"]),
                        tools=[
                            *READ_ONLY_TOOLS,
                            UPCOMING_APPOINTMENTS_TOOL,
                            BOOKING_OFFER_TOOL,
                            *CONSEQUENTIAL_PREVIEW_TOOLS,
                        ],
                    )
                    startup_deadline = (
                        asyncio.get_running_loop().time()
                        + self._settings.openai_realtime_connect_timeout_seconds
                    )
                    while True:
                        remaining = startup_deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise VoiceProtocolError(
                                "OpenAI Realtime did not accept the session settings in time."
                            )
                        updated = await asyncio.wait_for(
                            self._realtime.receive_event(), timeout=remaining
                        )
                        if updated.get("type") == "session.updated":
                            break
                        provider_error = updated.get("error")
                        if isinstance(provider_error, dict):
                            code = str(provider_error.get("code") or "UNKNOWN")
                            message_text = str(provider_error.get("message") or "No message")
                            logger.warning(
                                "realtime_session_update_rejected",
                                error_code=code,
                                error_message=message_text,
                            )
                            raise VoiceProtocolError(
                                f"OpenAI Realtime session settings rejected ({code}): {message_text}"
                            )
                        # Realtime may emit informational events such as
                        # rate_limits.updated between session lifecycle events.
                        logger.info(
                            "realtime_startup_event_ignored",
                            event_type=str(updated.get("type") or "unknown"),
                        )
                    presentation.available_tools([str(tool["name"]) for tool in [
                        *READ_ONLY_TOOLS, UPCOMING_APPOINTMENTS_TOOL, BOOKING_OFFER_TOOL,
                        *CONSEQUENTIAL_PREVIEW_TOOLS,
                    ]])
                    self._emit(VoiceEventType.CALL_STARTED, context["call_sid"], engine="realtime")
                    relay = asyncio.create_task(self._relay_output(websocket, context))
                    # The carrier requires initial outbound media quickly. Use the same
                    # server-owned playback path as consequential readbacks so the exact
                    # greeting is audible and cannot be skipped by a model response.
                    await self.play_controlled_readback(
                        proposal_id="initial-greeting",
                        text=(
                            f"{self._clinic_name} mein aapka swagat hai. "
                            "Batayiye, main aapki kya madad kar sakti hoon?"
                        ),
                        websocket=websocket,
                    )
                    continue
                if event == "media":
                    if context is None:
                        raise VoiceProtocolError("Media arrived before stream start.")
                    if _is_outbound_media(message):
                        continue
                    audio = self._decode_media(message)
                    if audio:
                        await self._realtime.send(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": base64.b64encode(alaw8k_to_pcm24k(audio)).decode(),
                            }
                        )
                        presentation.audio_transfer("input", len(audio))
                    continue
                if event == "mark":
                    name = str(message.get("mark", {}).get("name", ""))
                    if name and name == self._controlled_readback_id:
                        await self._acknowledge_controlled_readback(name)
                        self._emit(
                            VoiceEventType.PLAYBACK_ACKNOWLEDGED,
                            context["call_sid"] if context else "unknown",
                            playback_segment_id=name,
                        )
                        continue
                    if name and name == self._active_mark:
                        self._emit(
                            VoiceEventType.PLAYBACK_ACKNOWLEDGED,
                            context["call_sid"] if context else "unknown",
                            playback_segment_id=name,
                            audio_ms=round(self._played_alaw_bytes / 8),
                            assistant_item_id=self._active_item_id,
                            response_id=self._active_response_id,
                            generation_id=self._generation_id,
                        )
                        self._active_mark = ""
                        self._active_item_id = ""
                    elif name:
                        logger.info(
                            "voicelink_mark_ignored",
                            mark_name=name,
                            controlled_readback_active=bool(self._controlled_readback_id),
                            realtime_playback_active=bool(self._active_mark),
                        )
                    continue
                if event == "stop":
                    return
        finally:
            for task in self._tool_tasks:
                task.cancel()
            await asyncio.gather(*self._tool_tasks, return_exceptions=True)
            self._cancel_readback_timeout()
            if self._readback_timeout_task is not None:
                await asyncio.gather(self._readback_timeout_task, return_exceptions=True)
            if relay is not None:
                relay.cancel()
                await asyncio.gather(relay, return_exceptions=True)
            if self._runtime is not None:
                try:
                    await self._runtime.end()
                except Exception as error:
                    logger.warning("voice_call_session_end_failed", error_type=type(error).__name__)
            closers = [self._realtime.aclose(), self._audio.aclose()]
            if self._runtime_database_session is not None:
                closers.append(self._runtime_database_session.__aexit__(None, None, None))
            for result in await asyncio.gather(*closers, return_exceptions=True):
                if isinstance(result, BaseException):
                    logger.warning("realtime_cleanup_failed", error_type=type(result).__name__)
            self._runtime_database_session = None
            self._runtime = None
            self._websocket = None
            if context is not None:
                self._emit(VoiceEventType.CALL_ENDED, context["call_sid"], engine="realtime")

    async def _relay_output(self, websocket: WebSocket, context: dict[str, str]) -> None:
        reader = asyncio.create_task(self._read_realtime_events(websocket, context))
        playback = asyncio.create_task(self._send_playback(websocket, context["call_sid"]))
        try:
            done, _ = await asyncio.wait({reader, playback}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
        finally:
            reader.cancel()
            playback.cancel()
            await asyncio.gather(reader, playback, return_exceptions=True)

    async def _queue_playback(self, event: dict[str, Any]) -> None:
        encoded = event.get("delta")
        size = (len(encoded) * 3 + 3) // 4 if isinstance(encoded, str) else 0
        # At most ten seconds of PCM24k can wait behind the carrier writer. Apply
        # backpressure while a normal burst drains instead of dropping speech or
        # closing a healthy call merely because model output arrived faster than
        # the carrier clock.
        max_queued_bytes = 240_000
        if size > max_queued_bytes or self._playback_queue.full():
            raise VoiceProtocolError("Realtime playback backlog exceeded.")
        deadline = time.monotonic() + 5
        while self._queued_audio_bytes + size > max_queued_bytes:
            if time.monotonic() >= deadline:
                raise VoiceProtocolError("Realtime playback backlog exceeded.")
            await asyncio.sleep(0.01)
        self._playback_queue.put_nowait((self._caller_epoch, size, event))
        self._queued_audio_bytes += size

    async def _send_playback(self, websocket: WebSocket, call_id: str) -> None:
        while True:
            epoch, size, event = await self._playback_queue.get()
            try:
                if epoch != self._caller_epoch:
                    continue
                with presentation.correlation_scope(**_event_identifiers(event)):
                    if event.get("type") == "response.output_audio.delta":
                        await self._play_delta(
                            websocket, call_id, event, self._output_converter, expected_epoch=epoch,
                        )
                    elif event.get("item_id") == self._active_item_id:
                        await self._finish_playback(websocket, call_id)
            finally:
                self._queued_audio_bytes -= size
                self._playback_queue.task_done()

    async def _read_realtime_events(self, websocket: WebSocket, context: dict[str, str]) -> None:
        while True:
            event = await self._realtime.receive_event()
            kind = str(event.get("type", ""))
            call_id = context["call_sid"]
            with presentation.correlation_scope(**_event_identifiers(event)):
                if kind == "response.created":
                    presentation.response_fragment("", reset=True)
                elif kind == "response.output_audio_transcript.delta":
                    if isinstance(event.get("delta"), str):
                        presentation.response_fragment(event["delta"])
                elif kind == "response.output_audio.delta":
                    await self._queue_playback(event)
                elif kind == "response.output_audio.done":
                    await self._queue_playback(event)
                elif kind == "input_audio_buffer.speech_started":
                    presentation.emit("speech_started", "caller", "Realtime detected caller speech")
                    self._caller_epoch += 1
                    self._caller_items.start(str(event.get("item_id") or ""), datetime.now(UTC))
                    if self._controlled_readback_id:
                        proposal_id = self._pending_booking[0] if self._pending_booking else (
                            self._pending_operation[2] if self._pending_operation else None
                        )
                        presentation.emit(
                            "readback_interrupted", "consent", "Caller interrupted readback",
                            playback_segment_id=self._controlled_readback_id,
                            proposal_id=proposal_id, durable_operation_id=proposal_id,
                            failure_reason="caller_speech",
                        )
                        await self._send(websocket, {"event": "clear", "stream_sid": self._stream_sid})
                        self._readback_player.interrupt()
                        self._controlled_readback_id = ""
                        # A cleared controlled segment cannot later become consent
                        # evidence, including if the caller disconnects before STT.
                        self._pending_booking = None
                        self._pending_operation = None
                        self._readback_acknowledged = False
                        self._cancel_readback_timeout()
                    await self._interrupt_playback(websocket, call_id)
                elif kind == "input_audio_buffer.speech_stopped":
                    presentation.emit("speech_stopped", "voice", "Caller audio received; waiting for transcript")
                    self._caller_items.stop(str(event.get("item_id") or ""))
                    self._schedule_caller_drain(call_id)
                elif kind == "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript")
                    if isinstance(transcript, str):
                        presentation.dialogue("caller", transcript,
                                              source_id=str(event.get("item_id") or "") or None)
                        self._caller_items.transcribe(str(event.get("item_id") or ""), transcript)
                        self._schedule_caller_drain(call_id)
                elif kind == "response.output_audio_transcript.done":
                    if isinstance(event.get("transcript"), str):
                        presentation.dialogue("assistant", event["transcript"],
                                              source_id=str(event.get("item_id") or "") or None,
                                              evidence="generated_audio_transcript")
                elif kind == "response.done":
                    response = event.get("response")
                    if isinstance(response, dict) and isinstance(response.get("usage"), dict):
                        response_id = response.get("id") or event.get("event_id")
                        if isinstance(response_id, str) and response_id:
                            from app.observability.usage import openai_usage_record
                            usage_record = openai_usage_record(
                                operation="realtime_response",
                                model=str(response.get("model") or self._settings.openai_realtime_model),
                                request_id=response_id,
                                identity_source="provider",
                                usage=response["usage"],
                            )
                            if usage_record:
                                presentation.record_usage(usage_record)
                elif kind == "response.output_item.done":
                    item = event.get("item")
                    if isinstance(item, dict) and item.get("type") == "function_call":
                        tool_id = str(item.get("call_id") or "")
                        if tool_id in self._tool_calls:
                            continue
                        if len(self._tool_tasks) >= 4 or len(self._tool_calls) >= 256:
                            raise VoiceProtocolError("Tool backlog exceeded.")
                        self._tool_calls.add(tool_id)
                        task = asyncio.create_task(self._handle_tool_call(context, event, websocket=websocket))
                        self._tool_tasks.add(task)
                        task.add_done_callback(self._tool_finished)
                elif kind == "error":
                    error = event.get("error")
                    self._emit(
                        VoiceEventType.ERROR,
                        call_id,
                        error_code=(str(error.get("code")) if isinstance(error, dict) else "REALTIME_ERROR"),
                    )

    def _schedule_caller_drain(self, call_id: str) -> None:
        task = asyncio.create_task(self._drain_caller_items(call_id))
        self._tool_tasks.add(task)
        task.add_done_callback(self._tool_finished)

    async def _drain_caller_items(self, call_id: str) -> None:
        async with self._caller_drain_lock:
            await self._process_caller_items(call_id)

    async def _process_caller_items(self, call_id: str) -> None:
        for item in self._caller_items.ready():
            with presentation.correlation_scope(caller_item_id=item.item_id,
                                                caller_turn_id=None, response_id=None):
                stated_relationship = self._stated_relationship(item.transcript or "")
                if stated_relationship is not None:
                    self._latest_stated_relationship = stated_relationship
                epoch = self._caller_epoch
                pending_snapshot = (self._pending_booking, self._pending_operation)
                pending_acknowledged = self._readback_acknowledged and bool(
                    self._pending_booking or self._pending_operation
                )
                intent = ConfirmationIntent.UNCLEAR
                if pending_acknowledged:
                    intent = await self._confirmation_classifier.classify(
                        readback=self._confirmation_readback, transcript=item.transcript or "",
                    )
                if epoch != self._caller_epoch or pending_snapshot != (
                    self._pending_booking, self._pending_operation
                ):
                    # A newer utterance supersedes the interpretation in flight.
                    continue
                explicit = intent == ConfirmationIntent.CONFIRM
                invalidates = intent in {ConfirmationIntent.CHANGE, ConfirmationIntent.DECLINE}
                logger.info(
                    "voice_confirmation_evaluated",
                    call_id=call_id,
                    caller_item_id=item.item_id,
                    approval_candidate=explicit,
                    confirmation_intent=intent.value,
                    invalidates_pending_offer=invalidates,
                    readback_acknowledged=self._readback_acknowledged,
                    pending_booking=bool(self._pending_booking),
                    pending_operation=bool(self._pending_operation),
                )
                turn_id = await self._capture_caller_turn(
                    call_id, captured_at=item.started_at,
                    preserve_active_proposal=pending_acknowledged and not invalidates,
                )
                if invalidates or not self._readback_acknowledged:
                    # A correction/rejection or an overlapping early approval makes
                    # the old offer unusable. An unclear post-readback reply keeps it
                    # pending so the caller can be asked to confirm again.
                    self._pending_booking = None
                    self._pending_operation = None
                    self._readback_acknowledged = False
                if explicit and turn_id is not None:
                    await self._confirm_pending_booking(call_id, caller_turn_id=turn_id)
                    await self._confirm_pending_operation(call_id, caller_turn_id=turn_id)
                else:
                    response: dict[str, object] = {}
                    if pending_acknowledged:
                        response = {"instructions": (
                            "The latest reply was not approval. "
                            + ("The old offer was withdrawn. Respond to the caller's correction or refusal; "
                               "a changed booking requires a new offer and confirmation."
                               if invalidates else
                               "The offer is still pending. Answer any question using known facts, or "
                               "briefly clarify whether the caller wants the unchanged appointment. "
                               "Do not say you are waiting for backend confirmation.")
                        )}
                    await self._realtime.send({"type": "response.create", "response": response})
                self._emit(VoiceEventType.TRANSCRIPTION_COMPLETED, call_id,
                           caller_item_id=item.item_id, approval_candidate=explicit)

    async def _capture_caller_turn(
        self, call_id: str, *, captured_at: datetime | None = None,
        preserve_active_proposal: bool = False,
    ) -> int | None:
        """A completed caller utterance is a correction unless later parsed as approval."""
        if self._runtime is None or self._runtime.tracked is None:
            return None
        turn_id = await self._runtime.capture_turn(
            captured_at=captured_at, preserve_active_proposal=preserve_active_proposal
        )
        self._emit(VoiceEventType.CALLER_TURN_CAPTURED, call_id, caller_turn_id=turn_id)
        return turn_id

    async def _handle_tool_call(
        self, context: dict[str, str], event: dict[str, Any], *, websocket: WebSocket | None = None
    ) -> None:
        epoch = self._caller_epoch
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "function_call":
            return
        call_id = item.get("call_id")
        name = item.get("name")
        raw_arguments = item.get("arguments", "{}")
        if not isinstance(call_id, str) or not isinstance(name, str):
            return
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError:
            arguments = None
        presentation.selected_tool(name)
        preview_map = {
            "prepare_cancel_appointment": ("CANCEL", "cancel_appointment"),
            "prepare_reschedule_appointment": ("RESCHEDULE", "reschedule_appointment"),
        }
        allowed_names = {
            *READ_ONLY_TOOL_NAMES,
            "list_upcoming_appointments",
            "prepare_booking_offer",
            *preview_map,
        }
        if name not in allowed_names or not isinstance(arguments, dict):
            result: dict[str, object] = {"ok": False, "error": "Tool is not allowed."}
        elif (
            name == "prepare_booking_offer"
            and self._latest_stated_relationship is not None
            and str(arguments.get("relationship") or "").strip().upper()
            != self._latest_stated_relationship
        ):
            result = {
                "ok": False,
                "error": (
                    "The caller explicitly selected a different relationship. Ask for the "
                    "correct patient details and do not reuse an earlier patient's name."
                ),
            }
        else:
            assert self._settings.voice_organization_id is not None
            assert self._settings.voice_actor_id is not None
            assert self._settings.database_url is not None
            session_factory = get_session_factory(self._settings.database_url)
            async with session_factory() as database_session:
                executor_name = preview_map.get(name, ("", name))[1]
                executor_arguments = dict(arguments)
                if name == "list_upcoming_appointments":
                    executor_arguments = {
                        "phone_e164": context["caller"],
                        "challenge_id": None,
                    }
                if name == "prepare_booking_offer":
                    # Caller identity is authenticated carrier metadata. The model
                    # cannot ask for, invent or substitute another phone number.
                    executor_arguments["phone_e164"] = context["caller"]
                if name in preview_map:
                    executor_arguments["_voice_preview"] = True
                result = await ToolExecutor(
                    session=database_session,
                    organization_id=self._settings.voice_organization_id,
                    actor_id=self._settings.voice_actor_id,
                    settings=self._settings,
                    caller_phone_e164=context["caller"],
                    booking_source="AI_VOICE",
                    booking_consent_channel="AI_VOICE",
                ).execute(executor_name, executor_arguments)
        stale = epoch != self._caller_epoch
        if stale:
            result = {"ok": False, "error": "Superseded by a newer caller turn. Recheck if still needed."}
        if not stale and name == "prepare_booking_offer" and result.get("ok") is True:
            if self._runtime is None or websocket is None:
                raise VoiceProtocolError("Booking runtime is unavailable.")
            proposal, readback = await self._runtime.prepare_booking(result)
            token = result.get("offer_token")
            if not isinstance(token, str):
                raise VoiceProtocolError("Booking offer did not include a private token.")
            self._pending_booking = (proposal.id, token)
            self._readback_acknowledged = False
            segment_id = await self.play_controlled_readback(
                proposal_id=proposal.id, text=readback, websocket=websocket
            )
            self._start_readback_timeout(proposal.id, segment_id)
            # The signed token is never placed in the model conversation.
            result = {"ok": True, "status": "readback_playing", "offer": result.get("offer")}
        elif not stale and name in preview_map and result.get("ok") is True:
            if self._runtime is None or websocket is None:
                raise VoiceProtocolError("Operation runtime is unavailable.")
            operation, tool_name = preview_map[name]
            proposal = await self._runtime.prepare_operation(operation=operation, arguments=arguments)
            self._pending_operation = (operation, tool_name, proposal.id, dict(arguments))
            self._readback_acknowledged = False
            readback = self._operation_readback(operation, result)
            segment_id = await self.play_controlled_readback(
                proposal_id=proposal.id, text=readback, websocket=websocket
            )
            self._start_readback_timeout(proposal.id, segment_id)
            result = {"ok": True, "status": "readback_playing"}
        await self._realtime.send(
            {
                "type": "conversation.item.create",
                "item": {"type": "function_call_output", "call_id": call_id, "output": json.dumps(result)},
            }
        )
        presentation.emit("result_transmitted", "voice", "Tool result delivered to Realtime",
                          tool=name, details=presentation.safe_result(result))
        if not stale and result.get("status") != "readback_playing" and not self._controlled_readback_id:
            await self._realtime.send({"type": "response.create", "response": {"tool_choice": "none"}})

    async def _confirm_pending_booking(self, call_id: str, *, caller_turn_id: int) -> None:
        if not self._readback_acknowledged or self._pending_booking is None or self._runtime is None:
            return
        proposal_id, token = self._pending_booking
        logger.info("voice_booking_dispatch_started", call_id=call_id, proposal_id=proposal_id)
        try:
            result = await self._runtime.confirm_booking(
                proposal_id=proposal_id, caller_turn_id=caller_turn_id,
                offer_token=token, settings=self._settings,
            )
        except ValueError:
            self._emit(VoiceEventType.ERROR, call_id, error_code="BOOKING_CONFIRMATION_REJECTED")
            result = {"ok": False}
        finally:
            # A correction or any dispatch attempt consumes the private offer.
            self._pending_booking = None
            self._readback_acknowledged = False
        logger.info(
            "voice_booking_dispatch_completed", call_id=call_id,
            proposal_id=proposal_id, ok=result.get("ok") is True,
        )
        if result.get("ok") is not True:
            await self._realtime.send({
                "type": "conversation.item.create",
                "item": {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text":
                     "Server result: booking was not confirmed. The pending offer is no longer usable. "
                     "Do not wait for another backend result or claim success. "
                     "Recheck availability and prepare a fresh offer before requesting confirmation again."}
                ]},
            })
            await self._realtime.send({
                "type": "response.create", "response": {"tool_choice": "none", "instructions":
                "Briefly explain in the caller's language that the appointment could not be confirmed "
                "and ask whether they would like you to check availability again. Do not mention backend internals."},
            })
            return
        if result.get("ok") is True:
            reference = str(result.get("booking_reference") or "").strip()
            confirmation = "Ji, aapka appointment confirm ho gaya hai."
            if reference:
                confirmation += f" Aapka booking reference {reference} hai."
            confirmation += " Dhanyavaad."
            if self._websocket is not None:
                try:
                    await self.play_controlled_readback(
                        proposal_id=proposal_id,
                        text=confirmation,
                        websocket=self._websocket,
                    )
                    logger.info(
                        "voice_booking_confirmation_announced",
                        call_id=call_id,
                        proposal_id=proposal_id,
                        booking_reference=reference or None,
                    )
                    return
                except Exception as error:
                    logger.warning(
                        "voice_booking_confirmation_playback_failed",
                        call_id=call_id,
                        error_type=type(error).__name__,
                    )
            context_text = "Server result: the appointment is confirmed."
            if reference:
                context_text += f" Booking reference: {reference}."
            await self._realtime.send({
                "type": "conversation.item.create",
                "item": {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": context_text}
                ]},
            })
            await self._realtime.send({
                "type": "response.create", "response": {"tool_choice": "none", "instructions":
                "Briefly tell the caller the server-confirmed appointment result already in this conversation. Do not invent a booking reference or repeat the whole readback."},
            })

    async def _confirm_pending_operation(self, call_id: str, *, caller_turn_id: int) -> None:
        if not self._readback_acknowledged or self._pending_operation is None or self._runtime is None:
            return
        operation, tool_name, proposal_id, arguments = self._pending_operation
        try:
            result = await self._runtime.confirm_operation(
                operation=operation, tool_name=tool_name, proposal_id=proposal_id,
                caller_turn_id=caller_turn_id, arguments=arguments, settings=self._settings,
            )
        except ValueError:
            self._emit(VoiceEventType.ERROR, call_id, error_code="OPERATION_CONFIRMATION_REJECTED")
            result = {"ok": False}
        finally:
            self._pending_operation = None
            self._readback_acknowledged = False
        context_text = "Server result: the requested appointment change was not completed."
        if result.get("ok") is True:
            reference = str(result.get("replacement_reference") or result.get("booking_reference") or "").strip()
            context_text = "Server result: the appointment change is confirmed."
            if reference:
                context_text += f" Booking reference: {reference}."
            await self._realtime.send({
                "type": "conversation.item.create",
                "item": {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": context_text}
                ]},
            })
        else:
            await self._realtime.send({
                "type": "conversation.item.create",
                "item": {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": context_text}
                ]},
            })
        await self._realtime.send({
                "type": "response.create", "response": {"tool_choice": "none", "instructions":
                "Briefly tell the caller the server-confirmed cancellation or reschedule result already in this conversation. Do not invent details."},
            })

    async def _acknowledge_controlled_readback(self, segment_id: str) -> None:
        """Accept one matching carrier mark and persist its consent evidence."""
        if segment_id != self._controlled_readback_id:
            return
        self._readback_player.acknowledge(segment_id)
        presentation.emit("readback_acknowledged", "consent", "Carrier acknowledged readback",
                          **self._controlled_readback_links)
        self._controlled_readback_id = ""
        self._cancel_readback_timeout()
        proposal_id = self._pending_booking[0] if self._pending_booking else (
            self._pending_operation[2] if self._pending_operation else None
        )
        if self._runtime is None or proposal_id is None:
            return
        await self._runtime.acknowledge_readback(
            proposal_id=proposal_id,
            segment_id=segment_id,
            ledger=self._readback_player.ledger,
            completed_at=datetime.now(UTC),
        )
        self._readback_acknowledged = True
        presentation.emit("awaiting_confirmation", "consent",
                          "Readback acknowledged; awaiting approval",
                          **self._controlled_readback_links)

    def _start_readback_timeout(self, proposal_id: str, segment_id: str) -> None:
        self._cancel_readback_timeout()
        if not segment_id:
            raise VoiceProtocolError("Controlled readback did not register a carrier mark.")
        self._readback_timeout_task = asyncio.create_task(
            self._expire_unacknowledged_readback(proposal_id, segment_id)
        )

    def _cancel_readback_timeout(self) -> None:
        if self._readback_timeout_task is not None:
            self._readback_timeout_task.cancel()
            self._readback_timeout_task = None

    async def _expire_unacknowledged_readback(self, proposal_id: str, segment_id: str) -> None:
        try:
            await asyncio.sleep(self._settings.voice_readback_ack_timeout_seconds)
            if self._controlled_readback_id != segment_id:
                return
            pending_proposal_id = self._pending_booking[0] if self._pending_booking else (
                self._pending_operation[2] if self._pending_operation else None
            )
            if pending_proposal_id != proposal_id:
                return
            presentation.emit("readback_timeout", "consent", "Readback acknowledgment timed out",
                              proposal_id=proposal_id, durable_operation_id=proposal_id,
                              playback_segment_id=segment_id, failure_reason="carrier_ack_timeout")
            self._readback_player.interrupt()
            self._controlled_readback_id = ""
            self._pending_booking = None
            self._pending_operation = None
            self._readback_acknowledged = False
            logger.warning("controlled_readback_ack_timeout", proposal_id=proposal_id)
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _operation_readback(operation: str, result: dict[str, object]) -> str:
        reference = str(result.get("booking_reference") or "").strip()
        patient = str(result.get("patient_name") or "").strip()
        doctor = str(result.get("doctor_name") or "").strip()
        if not reference or not patient or not doctor:
            raise VoiceProtocolError("Operation preview lacks required readback details.")
        if operation == "CANCEL":
            return f"Please confirm: cancel appointment {reference} for {patient} with {doctor}."
        starts_at = str(result.get("starts_at") or "").strip()
        if not starts_at:
            raise VoiceProtocolError("Reschedule preview lacks the selected date and time.")
        location = str(result.get("location_name") or "").strip()
        branch = f" at {location}" if location else ""
        return f"Please confirm: reschedule appointment {reference} for {patient} to {starts_at} with {doctor}{branch}."

    def _tool_finished(self, task: asyncio.Task[None]) -> None:
        self._tool_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            error = task.exception()
            logger.warning(
                "realtime_tool_failed",
                error_type=type(error).__name__,
                error_message=str(error)[:300],
            )

    async def play_controlled_readback(
        self, *, proposal_id: str, text: str, websocket: WebSocket
    ) -> str:
        """Send backend-owned confirmation wording in an isolated carrier segment."""
        self._confirmation_readback = text
        if self._active_item_id:
            await self._interrupt_playback(websocket, "controlled-readback")
        if self._controlled_readback_id:
            raise VoiceProtocolError("A controlled readback is already active.")
        prepared_id = ""
        prepared_links: dict[str, str | int] = {}
        def prepared(segment_id: str) -> None:
            nonlocal prepared_id, prepared_links
            prepared_id = segment_id
            self._controlled_readback_id = segment_id
            operation_id = None if proposal_id == "initial-greeting" else proposal_id
            with presentation.correlation_scope(
                proposal_id=operation_id, durable_operation_id=operation_id,
                playback_segment_id=segment_id,
            ):
                self._controlled_readback_links = dict(presentation.correlation_context.get() or {})
                prepared_links = dict(self._controlled_readback_links)
                presentation.dialogue("assistant", text, source_id=segment_id)
                if operation_id is None:
                    presentation.emit("greeting", "voice", "Greeting prepared for playback")
                else:
                    presentation.emit("readback", "consent", "Preparing appointment readback")

        try:
            segment = await self._readback_player.play(
                proposal_id=proposal_id,
                text=text,
                send=lambda payload: self._send(websocket, payload),
                on_prepared=prepared,
            )
        except BaseException as error:
            presentation.emit("readback_failed", "consent", "Controlled readback did not complete",
                              failure_type=type(error).__name__, **prepared_links)
            if self._controlled_readback_id == prepared_id:
                self._controlled_readback_id = ""
            raise
        presentation.emit("readback_sent", "consent", "Readback audio and completion mark sent",
                          **prepared_links)
        return segment.id

    @staticmethod
    def _stated_relationship(transcript: str) -> str | None:
        for relationship, pattern in _RELATIONSHIP_PATTERNS:
            if pattern.search(transcript):
                return relationship
        return None

    async def _play_delta(
        self,
        websocket: WebSocket,
        call_id: str,
        event: dict[str, Any],
        converter: Pcm24kToAlaw8k,
        *,
        expected_epoch: int | None = None,
    ) -> None:
        incoming_item = str(event.get("item_id") or "")
        if incoming_item in self._discarded_items:
            return
        if self._controlled_readback_id:
            self._discarded_items.add(incoming_item)
            return
        encoded = event.get("delta")
        if not isinstance(encoded, str):
            return
        try:
            pcm = base64.b64decode(encoded, validate=True)
        except ValueError:
            self._emit(VoiceEventType.ERROR, call_id, error_code="INVALID_REALTIME_AUDIO")
            return
        audio = converter.feed(pcm)
        if not audio:
            return
        item_id = event.get("item_id")
        if isinstance(item_id, str) and item_id and item_id != self._active_item_id:
            self._generation_id += 1
            self._played_alaw_bytes = 0
            self._active_item_id = item_id
            self._active_response_id = str(event.get("response_id") or "")
            self._active_content_index = int(event.get("content_index", 0))
            self._emit(VoiceEventType.GENERATION_STARTED, call_id, generation_id=self._generation_id)
        for offset in range(0, len(audio), 160):
            if (expected_epoch is not None and expected_epoch != self._caller_epoch) or incoming_item in self._discarded_items:
                return
            chunk = audio[offset : offset + 160]
            await self._send(
                websocket,
                {"event": "media", "media": {"payload": base64.b64encode(chunk).decode()}},
            )
            self._played_alaw_bytes += len(chunk)
            await asyncio.sleep(len(chunk) / 8000)
        self._emit(
            VoiceEventType.PLAYBACK_STARTED,
            call_id,
            generation_id=self._generation_id or None,
            audio_ms=round(self._played_alaw_bytes / 8),
        )

    async def _finish_playback(self, websocket: WebSocket, call_id: str) -> None:
        if not self._active_item_id:
            return
        self._emit(VoiceEventType.GENERATION_COMPLETED, call_id, generation_id=self._generation_id,
                   assistant_item_id=self._active_item_id, response_id=self._active_response_id)
        self._active_mark = f"realtime-{self._generation_id}-{time.monotonic_ns()}"
        presentation.emit("playback_mark_sent", "voice", "Carrier completion mark sent",
                          playback_segment_id=self._active_mark,
                          assistant_item_id=self._active_item_id,
                          response_id=self._active_response_id, generation_id=self._generation_id)
        await self._send(websocket, {"event": "mark", "mark": {"name": self._active_mark}})

    async def _interrupt_playback(self, websocket: WebSocket, call_id: str) -> None:
        if not self._active_item_id:
            return
        await self._send(websocket, {"event": "clear", "stream_sid": self._stream_sid})
        # Sent bytes can still be buffered at the carrier. Without acknowledged
        # partial marks, zero is the only defensible lower bound on heard audio.
        audio_end_ms = 0
        self._discarded_items.add(self._active_item_id)
        self._output_converter = Pcm24kToAlaw8k()
        await self._realtime.send({"type": "response.cancel"})
        await self._realtime.send(
            {
                "type": "conversation.item.truncate",
                "item_id": self._active_item_id,
                "content_index": self._active_content_index,
                "audio_end_ms": audio_end_ms,
            }
        )
        self._emit(
            VoiceEventType.PLAYBACK_INTERRUPTED,
            call_id,
            generation_id=self._generation_id,
            playback_segment_id=self._active_mark or None,
            audio_ms=audio_end_ms,
            assistant_item_id=self._active_item_id,
            response_id=self._active_response_id,
        )
        self._active_mark = ""
        self._active_item_id = ""
        self._active_response_id = ""
        self._played_alaw_bytes = 0

    def _validate_start(self, message: dict[str, Any]) -> dict[str, str]:
        start = message.get("start")
        if not isinstance(start, dict):
            raise VoiceProtocolError("Missing stream start payload.")
        media = start.get("media_format", {})
        if media.get("encoding") != "audio/alaw" or int(media.get("sample_rate", 0)) != 8000:
            raise VoiceProtocolError("Unsupported VoiceLink audio format.")
        stream_sid = str(start.get("stream_sid") or message.get("stream_sid") or "")
        call_sid = str(start.get("call_sid") or "")
        caller = _normalize_e164_phone(start.get("from") or start.get("caller") or message.get("from"))
        called = _normalize_e164_phone(start.get("to") or start.get("called") or message.get("to"))
        if not stream_sid or not call_sid or not caller or not called:
            raise VoiceProtocolError("Incomplete VoiceLink call metadata.")
        if _phone_digits(called) != _phone_digits(self._settings.voicelink_phone_number):
            raise VoiceProtocolError("Unexpected VoiceLink destination number.")
        return {"stream_sid": stream_sid, "call_sid": call_sid, "caller": caller, "called": called}

    @staticmethod
    def _decode_media(message: dict[str, Any]) -> bytes:
        media = message.get("media")
        payload = media.get("payload") if isinstance(media, dict) else None
        if not isinstance(payload, str):
            raise VoiceProtocolError("Missing media payload.")
        try:
            return base64.b64decode(payload, validate=True)
        except ValueError as error:
            raise VoiceProtocolError("Invalid media payload.") from error

    async def _send(self, websocket: WebSocket, payload: dict[str, object]) -> None:
        # VoiceLink addresses outbound media-control messages to the active
        # bidirectional stream. Audio may be tolerated without this field, but
        # completion marks are not reliably echoed, which blocks consent.
        outgoing = dict(payload)
        if outgoing.get("event") in {"media", "mark", "clear"} and self._stream_sid:
            outgoing.setdefault("stream_sid", self._stream_sid)
        async with self._send_lock:
            await websocket.send_json(outgoing)
        if outgoing.get("event") == "media":
            presentation.audio_transfer("output", 1)

    @staticmethod
    def _emit(
        event_type: VoiceEventType,
        call_id: str,
        *,
        generation_id: int | None = None,
        playback_segment_id: str | None = None,
        **fields: str | int | float | bool | None,
    ) -> None:
        presentation.voice_event(
            event_type.value, generation_id=generation_id,
            playback_segment_id=playback_segment_id, **fields,
        )
        logger.info(
            "voice_call_event",
            **VoiceEvent(
                call_id=call_id,
                event_type=event_type,
                generation_id=generation_id,
                playback_segment_id=playback_segment_id,
                fields=fields,
            ).as_log_fields(),
        )
