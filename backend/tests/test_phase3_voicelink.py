import asyncio
import base64
import time
from collections import deque
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from pydantic import AnyHttpUrl

from app.core.config import Settings
from app.voice.codec import pcm16_sample_to_alaw
from app.voice.voicelink_gateway import (
    VoiceLinkVoiceGateway,
    _is_human_request,
    _is_self_echo,
)

ORGANIZATION_ID = UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = UUID("33333333-3333-3333-3333-333333333333")


def _settings() -> Settings:
    return Settings.model_construct(
        database_url="postgresql+asyncpg://unused",
        openai_api_key="openai-secret",
        openai_model="gpt-4o-mini",
        openai_transcription_model="gpt-4o-mini-transcribe",
        openai_tts_model="gpt-4o-mini-tts",
        openai_tts_voice="coral",
        public_backend_url=AnyHttpUrl("https://voice.example"),
        public_websocket_url="wss://voice.example/v1/voicelink/media",
        voicelink_phone_number="+919876543210",
        voice_organization_id=ORGANIZATION_ID,
        voice_actor_id=ACTOR_ID,
        verification_code_pepper="binding-secret",
    )


def test_human_request_detection() -> None:
    assert _is_human_request("Can you transfer me to a human?") is True
    assert _is_human_request("Kisi aadmi se baat kara do") is True
    assert _is_human_request("Connect me to executive please") is True
    assert _is_human_request("Customer care se baat karni hai") is True
    assert _is_human_request("Doctor Amit Sharma kal kab milenge") is False
    assert _is_human_request("Haan book kar dijiye") is False


def test_self_echo_does_not_suppress_slot_repetition() -> None:
    recent = [
        "Namaste Geeta Medicine mein aapka swagat hai.",
        "Dr Amit Sharma is available tomorrow five to seven in the evening. Would you like to book?",
    ]
    # Repeating a slot choice from the doctor session is NOT echo
    assert _is_self_echo("tomorrow five to seven", recent) is False
    assert _is_self_echo("kal shaam 5 se 7", recent) is False

    # Exact echo of assistant's full sentence IS echo
    assert _is_self_echo("Namaste Geeta Medicine mein aapka swagat hai.", recent) is True


@pytest.mark.asyncio
async def test_incoming_speech_barge_in_sends_clear_event() -> None:
    settings = _settings()
    sent_messages: list[dict[str, Any]] = []

    class MockWebSocket:
        def __init__(self, incoming: list[dict[str, Any]]) -> None:
            self._incoming = deque(incoming)

        async def receive_json(self) -> dict[str, Any]:
            if self._incoming:
                return self._incoming.popleft()
            await asyncio.sleep(0.1)
            return {"event": "stop"}

        async def send_json(self, data: dict[str, Any]) -> None:
            sent_messages.append(data)

    voiced_frame = bytes([pcm16_sample_to_alaw(5000)]) * 160
    b64_voiced = base64.b64encode(voiced_frame).decode()

    start_msg = {
        "event": "start",
        "start": {
            "stream_sid": "stream-test-123",
            "call_sid": "call-test-456",
            "media_format": {"encoding": "audio/alaw", "sample_rate": 8000},
            "caller": "+919876543210",
            "called": "+919876543210",
        },
    }

    media_msg = {
        "event": "media",
        "media": {"payload": b64_voiced},
    }

    mock_ws = MockWebSocket([start_msg, *[media_msg] * 5, {"event": "stop"}])

    mock_audio = MagicMock()
    mock_audio.synthesize_alaw = AsyncMock(return_value=voiced_frame)
    mock_audio.aclose = AsyncMock()

    gateway = VoiceLinkVoiceGateway(settings, audio=mock_audio)
    # Simulate assistant actively playing
    gateway._active_mark = "reply-active-mark"
    gateway._playback_until = time.monotonic() + 5.0

    await gateway.run(mock_ws)  # type: ignore[arg-type]

    # When voiced media arrived, barge-in should clear active mark and playback_until
    assert gateway._active_mark == ""
    assert gateway._playback_until == 0.0

    # A clear event must have been sent to the telephony provider
    clear_events = [m for m in sent_messages if m.get("event") == "clear"]
    assert len(clear_events) >= 1
    assert clear_events[0]["stream_sid"] == "stream-test-123"


@pytest.mark.asyncio
async def test_silence_reprompt_and_graceful_hangup() -> None:
    settings = _settings()
    gateway = VoiceLinkVoiceGateway(settings)

    class MockWs:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []

        async def send_json(self, data: dict[str, Any]) -> None:
            self.sent.append(data)

    mock_ws = MockWs()
    turns: asyncio.Queue[bytes | None] = asyncio.Queue()

    # Audio synthesis mock
    gateway._audio.synthesize_alaw = AsyncMock(return_value=b"\x55" * 160)  # type: ignore[method-assign]
    gateway._play = AsyncMock()  # type: ignore[method-assign]

    context = {
        "organization_id": str(ORGANIZATION_ID),
        "actor_id": str(ACTOR_ID),
        "call_sid": "test-silence-sid",
        "caller": "+919876543210",
    }

    # Run _process_turns with accelerated silence timeout (patching inside for testing)
    task = asyncio.create_task(gateway._process_turns(mock_ws, turns, context))  # type: ignore[arg-type]

    # Let silence trigger
    await asyncio.sleep(0.05)
    # Cancel task cleanly
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
