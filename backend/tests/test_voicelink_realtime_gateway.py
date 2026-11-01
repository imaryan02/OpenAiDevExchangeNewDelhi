import asyncio
import base64
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.voice.codec import Pcm24kToAlaw8k, alaw8k_to_pcm24k, pcm16_sample_to_alaw
from app.voice.confirmation_intent import ConfirmationIntent
from app.voice.voicelink_realtime_gateway import VoiceLinkRealtimeGateway


@pytest.mark.asyncio
async def test_voice_instructions_use_trusted_organization_context() -> None:
    org = uuid4()

    class Result:
        def mappings(self):
            return self

        def one_or_none(self):
            return {"name": "Verified Clinic", "timezone": "Asia/Kolkata"}

    class Database:
        async def execute(self, statement, values):
            assert values == {"organization_id": org}
            assert "organizations" in str(statement)
            return Result()

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(
        voice_organization_id=org,
        voice_clinic_name="Fallback Clinic",
        voice_pronunciation_guidance="Pronounce Geeta as Gee-ta",
    ))
    gateway._runtime_database_session = Database()

    instructions = await gateway._voice_instructions()

    assert "Verified Clinic" in instructions
    assert "Fallback Clinic" not in instructions
    assert "Asia/Kolkata" in instructions
    assert "current clinic-local date and time" in instructions
    assert "Pronounce Geeta as Gee-ta" in instructions


@pytest.mark.asyncio
async def test_voice_instructions_prefetch_saved_family_for_authenticated_caller(
    monkeypatch,
) -> None:
    from app.voice import voicelink_realtime_gateway as module

    org, actor = uuid4(), uuid4()

    class Result:
        def mappings(self):
            return self

        def one_or_none(self):
            return {"name": "Verified Clinic", "timezone": "Asia/Kolkata"}

    class Database:
        async def execute(self, statement, values):
            return Result()

    class Executor:
        def __init__(self, **kwargs):
            assert kwargs["caller_phone_e164"] == "+919800000001"

        async def execute(self, name, arguments):
            assert name == "lookup_caller_family"
            assert arguments == {"phone_e164": "+919800000001"}
            return {
                "ok": True,
                "recognized": True,
                "caller_name": "Aryan Gupta",
                "family_profiles": [
                    {"patient_name": "Bibha Gupta", "relationship": "MOTHER"}
                ],
            }

    monkeypatch.setattr(module, "ToolExecutor", Executor)
    gateway = VoiceLinkRealtimeGateway(
        Settings.model_construct(
            voice_organization_id=org,
            voice_actor_id=actor,
        )
    )
    gateway._runtime_database_session = Database()

    instructions = await gateway._voice_instructions("+919800000001")

    assert "Recognized caller name: Aryan Gupta" in instructions
    assert "MOTHER: Bibha Gupta" in instructions
    assert "Caller lookup has already completed" in instructions
    assert "Never ask for the authenticated phone number" in instructions


@pytest.mark.asyncio
async def test_booking_offer_is_read_back_without_leaking_signed_token(monkeypatch) -> None:
    from app.voice import voicelink_realtime_gateway as module

    sent: list[dict[str, Any]] = []
    org, actor = uuid4(), uuid4()

    class Database:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    class Executor:
        def __init__(self, **kwargs):
            assert kwargs["caller_phone_e164"] == "+919800000001"
        async def execute(self, name, arguments):
            assert name == "prepare_booking_offer"
            assert arguments["phone_e164"] == "+919800000001"
            return {"ok": True, "offer_token": "secret-signed-offer", "offer": {"patient_name": "Aryan"}}

    class Runtime:
        async def prepare_booking(self, result):
            assert result["offer_token"] == "secret-signed-offer"
            return SimpleNamespace(id="proposal-1"), "Please confirm Aryan's appointment."

    class Realtime:
        async def send(self, event):
            sent.append(event)

    monkeypatch.setattr(module, "get_session_factory", lambda _: Database)
    monkeypatch.setattr(module, "ToolExecutor", Executor)
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(
        database_url="unused", voice_organization_id=org, voice_actor_id=actor
    ), Realtime())
    gateway._runtime = Runtime()  # type: ignore[assignment]
    played: list[tuple[str, str]] = []
    async def play(*, proposal_id, text, websocket):
        played.append((proposal_id, text))
        return "mark-1"
    gateway.play_controlled_readback = play  # type: ignore[method-assign]
    await gateway._handle_tool_call({"caller": "+919800000001"}, {
        "item": {"type": "function_call", "call_id": "offer", "name": "prepare_booking_offer", "arguments": "{}"},
    }, websocket=SimpleNamespace())
    assert played == [("proposal-1", "Please confirm Aryan's appointment.")]
    assert gateway._pending_booking == ("proposal-1", "secret-signed-offer")
    output = sent[0]["item"]["output"]
    assert "secret-signed-offer" not in output
    assert "readback_playing" in output
    assert not any(event["type"] == "response.create" for event in sent)
    gateway._cancel_readback_timeout()


@pytest.mark.asyncio
async def test_failed_prepare_offer_requests_explanation(monkeypatch) -> None:
    from app.voice import voicelink_realtime_gateway as module

    class Database:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Executor:
        def __init__(self, **kwargs):
            pass

        async def execute(self, *args):
            return {"ok": False, "error": "Selected slot is unavailable."}

    realtime = SimpleNamespace(send=AsyncMock())
    monkeypatch.setattr(module, "get_session_factory", lambda _: Database)
    monkeypatch.setattr(module, "ToolExecutor", Executor)
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(
        database_url="unused", voice_organization_id=uuid4(), voice_actor_id=uuid4(),
    ), realtime)
    await gateway._handle_tool_call({"caller": "+919800000001"}, {"item": {
        "type": "function_call", "call_id": "offer", "name": "prepare_booking_offer",
        "arguments": "{}",
    }})
    assert realtime.send.call_args_list[-1].args[0]["type"] == "response.create"
    assert gateway._pending_booking is None


@pytest.mark.asyncio
async def test_explicit_sister_selection_cannot_prepare_mother_booking() -> None:
    sent = []

    class Realtime:
        async def send(self, event):
            sent.append(event)

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), Realtime())
    gateway._latest_stated_relationship = "OTHER"
    await gateway._handle_tool_call({"caller": "+919800000001"}, {"item": {
        "type": "function_call", "call_id": "offer", "name": "prepare_booking_offer",
        "arguments": json.dumps({"relationship": "MOTHER", "patient_name": "Bibha Gupta"}),
    }})

    result = json.loads(sent[0]["item"]["output"])
    assert result["ok"] is False
    assert "explicitly selected a different relationship" in result["error"]
    assert sent[1] == {"type": "response.create", "response": {"tool_choice": "none"}}


@pytest.mark.asyncio
async def test_cancel_preview_uses_controlled_readback_and_keeps_arguments_server_owned(monkeypatch) -> None:
    from app.voice import voicelink_realtime_gateway as module

    sent = []
    org, actor = uuid4(), uuid4()

    class Database:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    class Executor:
        def __init__(self, **kwargs):
            return None
        async def execute(self, name, arguments):
            assert name == "cancel_appointment"
            assert arguments == {"booking_reference": "GM-1", "reason": "Unavailable", "_voice_preview": True}
            return {"ok": True, "status": "CANCEL_PREVIEW", "booking_reference": "GM-1",
                    "patient_name": "Aryan", "doctor_name": "Dr Test"}

    class Runtime:
        async def prepare_operation(self, *, operation, arguments):
            assert operation == "CANCEL"
            assert arguments == {"booking_reference": "GM-1", "reason": "Unavailable"}
            return SimpleNamespace(id="cancel-proposal")

    class Realtime:
        async def send(self, event):
            sent.append(event)

    monkeypatch.setattr(module, "get_session_factory", lambda _: Database)
    monkeypatch.setattr(module, "ToolExecutor", Executor)
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(
        database_url="unused", voice_organization_id=org, voice_actor_id=actor
    ), Realtime())
    gateway._runtime = Runtime()  # type: ignore[assignment]
    played = []
    async def play(**kwargs):
        played.append(kwargs)
        return "mark-cancel"
    gateway.play_controlled_readback = play  # type: ignore[method-assign]
    await gateway._handle_tool_call({"caller": "+919800000001"}, {"item": {
        "type": "function_call", "call_id": "cancel", "name": "prepare_cancel_appointment",
        "arguments": '{"booking_reference":"GM-1","reason":"Unavailable"}',
    }}, websocket=SimpleNamespace())
    assert gateway._pending_operation == (
        "CANCEL", "cancel_appointment", "cancel-proposal",
        {"booking_reference": "GM-1", "reason": "Unavailable"},
    )
    assert "cancel appointment gm-1" in played[0]["text"].lower()
    assert "_voice_preview" not in sent[0]["item"]["output"]
    gateway._cancel_readback_timeout()


@pytest.mark.asyncio
async def test_correction_consumes_pending_offer_before_later_confirmation() -> None:
    class Runtime:
        def __init__(self):
            self.capture = []
            self.confirmed = 0
            self.tracked = object()
        async def capture_turn(self, **kwargs):
            self.capture.append(kwargs)
            return len(self.capture)
        async def confirm_booking(self, **kwargs):
            self.confirmed += 1
            return {"ok": True}

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct())
    runtime = Runtime()
    gateway._runtime = runtime  # type: ignore[assignment]
    gateway._pending_booking = ("proposal", "secret")
    gateway._readback_acknowledged = True
    for item_id, transcript in (("first", "no, change the doctor"), ("second", "yes confirm")):
        gateway._caller_items.start(item_id, datetime.now(UTC))
        gateway._caller_items.stop(item_id)
        gateway._caller_items.transcribe(item_id, transcript)
    gateway._confirmation_classifier.classify = AsyncMock(return_value=ConfirmationIntent.CHANGE)
    gateway._realtime.send = AsyncMock()
    await gateway._drain_caller_items("call")
    assert runtime.confirmed == 0
    assert gateway._pending_booking is None
    assert runtime.capture[0]["preserve_active_proposal"] is False


@pytest.mark.asyncio
async def test_unclear_reply_keeps_acknowledged_booking_offer_for_reprompt() -> None:
    class Runtime:
        def __init__(self):
            self.capture = []
            self.tracked = object()

        async def capture_turn(self, **kwargs):
            self.capture.append(kwargs)
            return 1

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct())
    runtime = Runtime()
    gateway._runtime = runtime  # type: ignore[assignment]
    gateway._pending_booking = ("proposal", "secret")
    gateway._readback_acknowledged = True
    gateway._caller_items.start("unclear", datetime.now(UTC))
    gateway._caller_items.stop("unclear")
    gateway._caller_items.transcribe("unclear", "could you repeat")
    gateway._confirmation_classifier.classify = AsyncMock(return_value=ConfirmationIntent.UNCLEAR)
    gateway._realtime.send = AsyncMock()

    await gateway._drain_caller_items("call")

    assert gateway._pending_booking == ("proposal", "secret")
    assert gateway._readback_acknowledged is True
    assert runtime.capture[0]["preserve_active_proposal"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("transcript", ["hn book kar do", "hn thik hai book kar do", "हाँ ठीक है बुक कर दो"])
@pytest.mark.parametrize("acknowledged", [True, False])
async def test_reported_confirmation_dispatches_booking_only_after_readback(transcript, acknowledged) -> None:
    class Runtime:
        tracked = object()

        def __init__(self):
            self.requests = []

        async def capture_turn(self, **kwargs):
            return 7

        async def confirm_booking(self, **kwargs):
            self.requests.append(kwargs)
            return {"ok": True, "booking_reference": "GM-test"}

    class Realtime:
        def __init__(self):
            self.sent = []

        async def send(self, event):
            self.sent.append(event)

    realtime = Realtime()
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), realtime)
    runtime = Runtime()
    gateway._runtime = runtime
    gateway._pending_booking = ("proposal", "private-token")
    gateway._readback_acknowledged = acknowledged
    gateway._caller_items.start("approval", datetime.now(UTC))
    gateway._caller_items.stop("approval")
    gateway._caller_items.transcribe("approval", transcript)
    gateway._confirmation_classifier.classify = AsyncMock(return_value=ConfirmationIntent.CONFIRM)

    await gateway._drain_caller_items("call")

    assert len(runtime.requests) == int(acknowledged)
    if acknowledged:
        assert runtime.requests[0]["offer_token"] == "private-token"
        assert runtime.requests[0]["caller_turn_id"] == 7
        assert "GM-test" in realtime.sent[0]["item"]["content"][0]["text"]
    else:
        gateway._confirmation_classifier.classify.assert_not_awaited()
        assert realtime.sent == [{"type": "response.create", "response": {}}]


@pytest.mark.asyncio
async def test_only_matching_carrier_mark_persists_controlled_readback() -> None:
    class Runtime:
        def __init__(self):
            self.calls = []
        async def acknowledge_readback(self, **kwargs):
            self.calls.append(kwargs)

    class Audio:
        async def synthesize_alaw(self, text):
            return b"a" * 160

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), audio=Audio())
    runtime = Runtime()
    gateway._runtime = runtime  # type: ignore[assignment]
    segment = gateway._readback_player.ledger.prepare(proposal_id="proposal", text="Confirm details")
    gateway._readback_player.ledger.sent(segment.id)
    gateway._controlled_readback_id = segment.id
    gateway._pending_booking = ("proposal", "secret")
    await gateway._acknowledge_controlled_readback("another-mark")
    assert runtime.calls == []
    assert gateway._controlled_readback_id == segment.id
    await gateway._acknowledge_controlled_readback(segment.id)
    assert runtime.calls[0]["proposal_id"] == "proposal"
    assert runtime.calls[0]["segment_id"] == segment.id
    assert gateway._readback_acknowledged is True
    assert gateway._controlled_readback_id == ""


@pytest.mark.asyncio
async def test_new_speech_supersedes_inflight_intent_without_booking() -> None:
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct())
    gateway._pending_booking = ("proposal", "secret")
    gateway._readback_acknowledged = True
    gateway._caller_items.start("old", datetime.now(UTC))
    gateway._caller_items.stop("old")
    gateway._caller_items.transcribe("old", "go ahead")
    gateway._confirm_pending_booking = AsyncMock()

    async def classify(**kwargs):
        gateway._caller_epoch += 1
        return ConfirmationIntent.CONFIRM

    gateway._confirmation_classifier.classify = classify
    await gateway._drain_caller_items("call")
    gateway._confirm_pending_booking.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_carrier_mark_expires_private_offer_without_confirmation(monkeypatch) -> None:
    from app.voice import voicelink_realtime_gateway as module

    async def immediate_sleep(_seconds):
        return None

    monkeypatch.setattr(module.asyncio, "sleep", immediate_sleep)
    class Audio:
        async def synthesize_alaw(self, text):
            return b"a" * 160

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), audio=Audio())
    segment = gateway._readback_player.ledger.prepare(proposal_id="proposal", text="Confirm details")
    gateway._readback_player.ledger.sent(segment.id)
    gateway._controlled_readback_id = segment.id
    gateway._pending_booking = ("proposal", "secret")
    await gateway._expire_unacknowledged_readback("proposal", segment.id)
    assert gateway._controlled_readback_id == ""
    assert gateway._pending_booking is None
    assert gateway._readback_acknowledged is False


@pytest.mark.asyncio
async def test_committed_booking_result_is_added_to_realtime_context() -> None:
    sent = []
    class Realtime:
        async def send(self, event):
            sent.append(event)
    class Runtime:
        async def confirm_booking(self, **kwargs):
            return {"ok": True, "booking_reference": "GM-123"}

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), Realtime())
    gateway._runtime = Runtime()  # type: ignore[assignment]
    gateway._pending_booking = ("proposal", "secret")
    gateway._readback_acknowledged = True
    await gateway._confirm_pending_booking("call", caller_turn_id=2)
    assert sent[0]["item"]["content"][0]["text"] == "Server result: the appointment is confirmed. Booking reference: GM-123."
    assert sent[1]["type"] == "response.create"


@pytest.mark.asyncio
async def test_committed_booking_result_uses_controlled_carrier_playback_when_live() -> None:
    model_events = []
    carrier_events = []

    class Realtime:
        async def send(self, event):
            model_events.append(event)

    class Runtime:
        async def confirm_booking(self, **kwargs):
            return {"ok": True, "booking_reference": "GM-123"}

    class Audio:
        async def synthesize_alaw(self, text):
            return b"\x00" * 160

    class Websocket:
        async def send_json(self, event):
            carrier_events.append(event)

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), Realtime(), audio=Audio())
    gateway._runtime = Runtime()  # type: ignore[assignment]
    gateway._pending_booking = ("proposal", "secret")
    gateway._readback_acknowledged = True
    gateway._websocket = Websocket()  # type: ignore[assignment]
    gateway._stream_sid = "stream-1"

    await gateway._confirm_pending_booking("call", caller_turn_id=2)

    assert model_events == []
    assert gateway._confirmation_readback == (
        "Ji, aapka appointment confirm ho gaya hai. Aapka booking reference GM-123 hai. Dhanyavaad."
    )
    assert [event["event"] for event in carrier_events] == ["media", "mark"]
    assert all(event["stream_sid"] == "stream-1" for event in carrier_events)


def test_canary_numbers_require_exact_e164_and_deduplicate() -> None:
    settings = Settings(VOICE_REALTIME_CANARY_CALLERS=["+919800000001", "+919800000001"])
    assert settings.voice_realtime_canary_callers == ["+919800000001"]
    for invalid in ("9800000001", "+91 9800000001", "+09800000001", "*", ""):
        with pytest.raises(ValueError):
            Settings(VOICE_REALTIME_CANARY_CALLERS=[invalid])


@pytest.mark.asyncio
@pytest.mark.parametrize("rejected", [False, True])
async def test_failed_booking_is_reported_to_model_without_retrying(rejected) -> None:
    sent = []

    class Realtime:
        async def send(self, event):
            sent.append(event)

    class Runtime:
        async def confirm_booking(self, **kwargs):
            if rejected:
                raise ValueError("Stale consent")
            return {"ok": False, "error": "The booking offer expired."}

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), Realtime())
    gateway._runtime = Runtime()
    gateway._pending_booking = ("proposal", "secret")
    gateway._readback_acknowledged = True
    await gateway._confirm_pending_booking("call", caller_turn_id=2)
    assert "booking was not confirmed" in sent[0]["item"]["content"][0]["text"]
    assert sent[1]["type"] == "response.create"
    assert gateway._pending_booking is None


@pytest.mark.asyncio
async def test_realtime_call_requests_initial_greeting_after_session_update(monkeypatch) -> None:
    from app.voice import voicelink_realtime_gateway as module

    sent: list[dict[str, Any]] = []
    configured_tool_names: set[str] = set()
    events = iter([
        {"type": "session.created", "session": {"id": "session-1"}},
        {"type": "rate_limits.updated", "rate_limits": []},
        {"type": "session.updated", "session": {"id": "session-1"}},
    ])
    wait_forever = asyncio.Event()

    class Realtime:
        async def connect(self):
            return None
        async def receive_event(self):
            try:
                return next(events)
            except StopIteration:
                await wait_forever.wait()
        async def configure_voice_session(self, instructions, *, tools):
            assert "Introduce yourself only once" in instructions
            configured_tool_names.update(str(tool["name"]) for tool in tools)
        async def send(self, event):
            sent.append(event)
        async def aclose(self):
            return None

    class Audio:
        async def synthesize_alaw(self, text):
            return b"\x00" * 160
        async def aclose(self):
            return None

    class Database:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    class Runtime:
        def __init__(self, database, organization_id):
            return None
        async def start(self, **kwargs):
            return None

    messages = iter([
        {"event": "start", "start": {
            "stream_sid": "stream", "call_sid": "call", "from": "+919800000001",
            "to": "+919876543210",
            "media_format": {"encoding": "audio/alaw", "sample_rate": 8000},
        }},
        {"event": "stop"},
    ])

    class Socket:
        async def receive_json(self):
            return next(messages)
        async def send_json(self, event):
            sent.append(event)

    monkeypatch.setattr(module, "get_session_factory", lambda _: Database)
    monkeypatch.setattr(module, "VoiceCallRuntime", Runtime)
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(
        database_url="unused", voice_organization_id=uuid4(), voice_actor_id=uuid4(),
        voicelink_phone_number="+919876543210", openai_api_key="key",
        openai_realtime_model="gpt-realtime-2.1", openai_realtime_voice="marin",
        openai_realtime_connect_timeout_seconds=1,
    ), Realtime(), Audio())

    await gateway.run(Socket())

    assert [event["event"] for event in sent] == ["media", "mark"]
    assert all(event["stream_sid"] == "stream" for event in sent)
    assert configured_tool_names == {
        "get_clinic_information",
        "suggest_department",
        "search_availability",
        "list_upcoming_appointments",
        "prepare_booking_offer",
        "prepare_cancel_appointment",
        "prepare_reschedule_appointment",
    }


@pytest.mark.asyncio
async def test_upcoming_appointment_lookup_uses_authenticated_caller(monkeypatch) -> None:
    from app.voice import voicelink_realtime_gateway as module

    sent: list[dict[str, Any]] = []

    class Database:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None

    class Executor:
        def __init__(self, **kwargs):
            assert kwargs["caller_phone_e164"] == "+919800000001"
        async def execute(self, name, arguments):
            assert name == "list_upcoming_appointments"
            assert arguments == {
                "phone_e164": "+919800000001",
                "challenge_id": None,
            }
            return {"ok": True, "appointments": []}

    class Realtime:
        async def send(self, event):
            sent.append(event)

    monkeypatch.setattr(module, "get_session_factory", lambda _: Database)
    monkeypatch.setattr(module, "ToolExecutor", Executor)
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(
        database_url="unused", voice_organization_id=uuid4(), voice_actor_id=uuid4()
    ), Realtime())

    await gateway._handle_tool_call({"caller": "+919800000001"}, {"item": {
        "type": "function_call",
        "call_id": "appointments",
        "name": "list_upcoming_appointments",
        "arguments": "{}",
    }})

    assert json.loads(sent[0]["item"]["output"]) == {"ok": True, "appointments": []}
    assert sent[1] == {"type": "response.create", "response": {"tool_choice": "none"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("caller,expected_realtime", [("+919800000001", True), ("+919800000002", False)])
async def test_canary_selection_precedes_realtime_state_creation(monkeypatch, caller, expected_realtime) -> None:
    from app.voice import voicelink_realtime_gateway as module
    from app.voice.gateway import VoiceProtocolError

    routed = []
    start = {"event": "start", "start": {
        "stream_sid": "stream", "call_sid": "call", "from": caller, "to": "+919876543210",
        "media_format": {"encoding": "audio/alaw", "sample_rate": 8000},
    }}

    class Socket:
        async def receive_json(self):
            return start

    class Legacy:
        def __init__(self, settings):
            pass
        async def run(self, websocket, *, initial_message):
            routed.append(initial_message)

    monkeypatch.setattr(module, "VoiceLinkVoiceGateway", Legacy)
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(
        voice_realtime_canary_callers=["+919800000001"],
        voicelink_phone_number="+919876543210", openai_api_key=None,
    ))
    if expected_realtime:
        # Selected caller reaches Realtime configuration check; no network/DB is used.
        with pytest.raises(VoiceProtocolError, match="not configured"):
            await gateway.run(Socket())
        assert routed == []
    else:
        await gateway.run(Socket())
        assert routed == [start]
    assert gateway._runtime is None


@pytest.mark.asyncio
async def test_reader_processes_interruption_while_playback_is_paced(monkeypatch) -> None:
    from app.voice import voicelink_realtime_gateway as module

    events = asyncio.Queue()
    first_packet, interrupted = asyncio.Event(), asyncio.Event()
    pacing = []
    carrier = []

    class Realtime:
        async def receive_event(self):
            return await events.get()
        async def send(self, event):
            if event["type"] == "conversation.item.truncate":
                interrupted.set()

    async def sleep(delay):
        pacing.append(delay)
        first_packet.set()
        await interrupted.wait()

    class Socket:
        async def send_json(self, payload):
            carrier.append(payload)

    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), Realtime())
    pcm = alaw8k_to_pcm24k(b"a" * 1600)
    await events.put({"type": "response.output_audio.delta", "item_id": "reply",
                      "delta": base64.b64encode(pcm).decode()})
    await events.put({"type": "response.output_audio.done", "item_id": "reply"})
    relay = asyncio.create_task(gateway._relay_output(Socket(), {"call_sid": "call"}))
    try:
        await asyncio.wait_for(first_packet.wait(), 1)
        await events.put({"type": "input_audio_buffer.speech_started", "item_id": "caller"})
        await asyncio.wait_for(interrupted.wait(), 1)
        await asyncio.wait_for(gateway._playback_queue.join(), 1)
        assert pacing == [0.02]
        assert [event["event"] for event in carrier] == ["media", "clear"]
        assert gateway._queued_audio_bytes == 0
    finally:
        relay.cancel()
        await asyncio.gather(relay, return_exceptions=True)
        await gateway._audio.aclose()


@pytest.mark.asyncio
async def test_playback_overload_fails_instead_of_growing_unbounded() -> None:
    from app.voice.gateway import VoiceProtocolError

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct())
    try:
        with pytest.raises(VoiceProtocolError, match="backlog"):
            await gateway._queue_playback({"type": "response.output_audio.delta", "delta": "a" * 320004})
        assert gateway._playback_queue.empty()
        assert gateway._queued_audio_bytes == 0
        for _ in range(128):
            await gateway._queue_playback({"type": "response.output_audio.done", "item_id": "reply"})
        with pytest.raises(VoiceProtocolError, match="backlog"):
            await gateway._queue_playback({"type": "response.output_audio.done", "item_id": "reply"})
    finally:
        await gateway._audio.aclose()


@pytest.mark.asyncio
async def test_playback_failure_stops_reader_and_propagates() -> None:
    stopped = asyncio.Event()
    count = 0

    class Realtime:
        async def receive_event(self):
            nonlocal count
            count += 1
            if count == 1:
                return {"type": "response.output_audio.delta", "item_id": "reply",
                        "delta": base64.b64encode(alaw8k_to_pcm24k(b"a" * 160)).decode()}
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    class Socket:
        async def send_json(self, payload):
            raise RuntimeError("carrier disconnected")

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), Realtime())
    try:
        with pytest.raises(RuntimeError, match="carrier disconnected"):
            await asyncio.wait_for(gateway._relay_output(Socket(), {"call_sid": "call"}), 1)
        assert stopped.is_set()
    finally:
        await gateway._audio.aclose()


@pytest.mark.asyncio
async def test_synthesis_failure_releases_controlled_readback() -> None:
    class Audio:
        async def synthesize_alaw(self, text):
            raise RuntimeError("TTS unavailable")

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), audio=Audio())
    with pytest.raises(RuntimeError, match="TTS unavailable"):
        await gateway.play_controlled_readback(proposal_id="proposal", text="Details", websocket=None)
    assert gateway._controlled_readback_id == ""


@pytest.mark.asyncio
async def test_failed_readback_links_text_segment_and_operation_without_exception_content(monkeypatch):
    from app.voice import presentation

    class Audio:
        async def synthesize_alaw(self, text):
            raise RuntimeError("private patient detail and secret token")

    captured = []
    messages = []
    monkeypatch.setattr(presentation, "emit", lambda kind, *args, **fields:
                        captured.append((kind, fields)))
    monkeypatch.setattr(presentation, "dialogue", lambda speaker, text, **fields:
                        messages.append(fields))
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), audio=Audio())
    with presentation.correlation_scope(response_id="response-1", provider_tool_call_id="tool-1"):
        with pytest.raises(RuntimeError):
            await gateway.play_controlled_readback(
                proposal_id="proposal-1", text="Details", websocket=None)
    failure = next(fields for kind, fields in captured if kind == "readback_failed")
    assert failure["response_id"] == "response-1"
    assert failure["durable_operation_id"] == "proposal-1"
    assert failure["playback_segment_id"] == messages[0]["source_id"]
    assert failure["failure_type"] == "RuntimeError"
    assert "secret" not in str(captured)


def test_provider_identifiers_do_not_guess_caller_turn_for_response():
    from app.voice.voicelink_realtime_gateway import _event_identifiers

    caller = _event_identifiers({"type": "input_audio_buffer.speech_started", "item_id": "caller"})
    output = _event_identifiers({"type": "response.output_item.done", "response_id": "response",
                                "item": {"id": "output", "call_id": "tool-call",
                                         "type": "function_call"}})
    assert caller["caller_item_id"] == "caller" and "assistant_item_id" not in caller
    assert output["response_id"] == "response" and output["assistant_item_id"] == "output"
    assert output["provider_tool_call_id"] == "tool-call"
    assert "caller_turn_id" not in output and "caller_item_id" not in output


@pytest.mark.asyncio
async def test_tool_reader_remains_responsive_and_stale_result_does_not_speak(monkeypatch) -> None:
    from uuid import uuid4

    from app.voice import voicelink_realtime_gateway as module

    entered, release = asyncio.Event(), asyncio.Event()
    sent = []

    class Realtime:
        async def send(self, event):
            sent.append(event)

    class Database:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class Executor:
        def __init__(self, **kwargs):
            pass
        async def execute(self, *args):
            entered.set()
            await release.wait()
            return {"ok": True, "address": "Old result"}

    monkeypatch.setattr(module, "get_session_factory", lambda url: Database)
    monkeypatch.setattr(module, "ToolExecutor", Executor)
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(
        database_url="unused", voice_organization_id=uuid4(), voice_actor_id=uuid4()
    ), Realtime())
    task = asyncio.create_task(gateway._handle_tool_call({"caller": "+919800000001"}, {
        "item": {"type": "function_call", "call_id": "lookup", "name": "get_clinic_information", "arguments": "{}"}
    }))
    await entered.wait()
    gateway._caller_epoch += 1
    release.set()
    await task
    assert len(sent) == 1
    assert "Superseded" in sent[0]["item"]["output"]
    await gateway._audio.aclose()


def test_alaw_realtime_boundary_preserves_sample_count_and_packet_boundaries() -> None:
    source = bytes([pcm16_sample_to_alaw(4000), pcm16_sample_to_alaw(-6000)]) * 80
    pcm = alaw8k_to_pcm24k(source)
    converter = Pcm24kToAlaw8k()

    restored = converter.feed(pcm[:7]) + converter.feed(pcm[7:])

    assert len(pcm) == len(source) * 6
    assert restored == source


@pytest.mark.asyncio
async def test_realtime_delta_uses_carrier_media_and_mark_acknowledgement() -> None:
    settings = Settings.model_construct(voicelink_phone_number="+919876543210")
    gateway = VoiceLinkRealtimeGateway(settings)
    sent: list[dict[str, Any]] = []

    class Socket:
        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    # 20 ms at 24 kHz: three PCM samples per target A-law byte.
    pcm = alaw8k_to_pcm24k(bytes([pcm16_sample_to_alaw(4000)]) * 160)
    await gateway._play_delta(  # noqa: SLF001
        Socket(),
        "call-1",
        {
            "type": "response.output_audio.delta",
            "item_id": "item-1",
            "content_index": 0,
            "delta": base64.b64encode(pcm).decode(),
        },
        Pcm24kToAlaw8k(),
    )
    await gateway._finish_playback(Socket(), "call-1")  # noqa: SLF001

    assert sent[0]["event"] == "media"
    assert len(base64.b64decode(sent[0]["media"]["payload"])) == 160
    assert sent[-1]["event"] == "mark"


@pytest.mark.asyncio
async def test_barge_in_clears_carrier_and_truncates_realtime_audio() -> None:
    class Realtime:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []

        async def send(self, event: dict[str, object]) -> None:
            self.sent.append(event)

    realtime = Realtime()
    gateway = VoiceLinkRealtimeGateway(Settings.model_construct(), realtime)  # type: ignore[arg-type]
    gateway._stream_sid = "stream-1"  # noqa: SLF001
    gateway._active_item_id = "item-1"  # noqa: SLF001
    gateway._active_content_index = 0  # noqa: SLF001
    gateway._active_mark = "realtime-1"  # noqa: SLF001
    gateway._played_alaw_bytes = 320  # noqa: SLF001
    sent: list[dict[str, Any]] = []

    class Socket:
        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    await gateway._interrupt_playback(Socket(), "call-1")  # noqa: SLF001

    assert sent == [{"event": "clear", "stream_sid": "stream-1"}]
    assert realtime.sent == [
        {"type": "response.cancel"},
        {
            "type": "conversation.item.truncate",
            "item_id": "item-1",
            "content_index": 0,
            "audio_end_ms": 0,
        },
    ]


@pytest.mark.asyncio
async def test_gateway_plays_controlled_readback_as_a_distinct_carrier_segment() -> None:
    class Realtime:
        async def send(self, event: dict[str, object]) -> None:
            return None

    class Audio:
        async def synthesize_alaw(self, text: str) -> bytes:
            assert text == "Please confirm the details."
            return b"a" * 160

        async def aclose(self) -> None:
            return None

    sent: list[dict[str, Any]] = []

    class Socket:
        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    gateway = VoiceLinkRealtimeGateway(
        Settings.model_construct(), Realtime(), Audio()  # type: ignore[arg-type]
    )
    segment_id = await gateway.play_controlled_readback(
        proposal_id="proposal-1", text="Please confirm the details.", websocket=Socket()
    )

    assert sent[0]["event"] == "media"
    assert sent[1] == {"event": "mark", "mark": {"name": segment_id}}


def test_voice_engine_allows_only_explicit_rollout_values() -> None:
    assert Settings(VOICE_ENGINE="realtime").voice_engine == "realtime"
    with pytest.raises(ValueError):
        Settings(VOICE_ENGINE="unknown")


@pytest.mark.asyncio
async def test_outbound_carrier_messages_include_active_stream_identity() -> None:
    sent: list[dict[str, Any]] = []

    class Socket:
        async def send_json(self, payload: dict[str, Any]) -> None:
            sent.append(payload)

    gateway = VoiceLinkRealtimeGateway(Settings.model_construct())
    gateway._stream_sid = "stream-123"

    await gateway._send(Socket(), {"event": "media", "media": {"payload": "YQ=="}})
    await gateway._send(Socket(), {"event": "mark", "mark": {"name": "done"}})

    assert sent[0]["stream_sid"] == "stream-123"
    assert sent[1]["stream_sid"] == "stream-123"
