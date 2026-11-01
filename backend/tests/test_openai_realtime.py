import json
from typing import Any

import pytest

from app.core.config import Settings
from app.integrations import openai_realtime
from app.integrations.openai_realtime import OpenAIRealtimeSession, preflight
from app.voice.events import VoiceEvent, VoiceEventType


def test_voice_event_has_correlated_identifiers_without_transcript() -> None:
    event = VoiceEvent(
        call_id="call-123",
        event_type=VoiceEventType.CALLER_TURN_CAPTURED,
        caller_turn_id=4,
        fields={"audio_ms": 620, "queue_depth": 1},
    )

    fields = event.as_log_fields()

    assert fields["call_id"] == "call-123"
    assert fields["voice_event_type"] == "caller_turn_captured"
    assert fields["caller_turn_id"] == 4
    assert fields["audio_ms"] == 620
    assert "transcript" not in fields


@pytest.mark.asyncio
async def test_audio_only_configuration_uses_semantic_vad_and_pcm() -> None:
    sent: list[dict[str, Any]] = []

    class Connection:
        async def send(self, payload: str) -> None:
            sent.append(json.loads(payload))

    settings = Settings.model_construct(
        openai_api_key="test-key",
        openai_realtime_model="gpt-realtime-2.1",
        openai_realtime_voice="marin",
    )
    session = OpenAIRealtimeSession(settings)
    session._connection = Connection()  # type: ignore[assignment]

    await session.configure_audio_only_session()

    configured = sent[0]["session"]
    assert configured["model"] == "gpt-realtime-2.1"
    assert configured["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24000}
    assert configured["audio"]["input"]["turn_detection"] == {
        "type": "semantic_vad", "create_response": False,
    }
    assert configured["audio"]["input"]["transcription"] == {"model": "gpt-4o-mini-transcribe"}
    assert configured["audio"]["output"]["voice"] == "marin"


@pytest.mark.asyncio
async def test_voice_configuration_accepts_gateway_instructions() -> None:
    sent: list[dict[str, Any]] = []

    class Connection:
        async def send(self, payload: str) -> None:
            sent.append(json.loads(payload))

    session = OpenAIRealtimeSession(Settings.model_construct(openai_api_key="test-key"))
    session._connection = Connection()  # type: ignore[assignment]

    await session.configure_voice_session("Use concise Hinglish.")

    assert sent[0]["session"]["instructions"] == "Use concise Hinglish."


@pytest.mark.asyncio
async def test_voice_configuration_exposes_only_supplied_tools() -> None:
    sent: list[dict[str, Any]] = []

    class Connection:
        async def send(self, payload: str) -> None:
            sent.append(json.loads(payload))

    session = OpenAIRealtimeSession(Settings.model_construct(openai_api_key="test-key"))
    session._connection = Connection()  # type: ignore[assignment]
    tools = [{
        "type": "function",
        "name": "clinic",
        "strict": True,
        "parameters": {"type": "object"},
    }]

    await session.configure_voice_session("Use concise Hinglish.", tools=tools)

    assert sent[0]["session"]["tools"] == [
        {"type": "function", "name": "clinic", "parameters": {"type": "object"}}
    ]
    assert tools[0]["strict"] is True
    assert sent[0]["session"]["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_preflight_requires_session_created_then_updated(monkeypatch: pytest.MonkeyPatch) -> None:
    configured = False

    class Session:
        def __init__(self, _settings: Settings) -> None:
            self._events = iter(
                [
                    {"type": "session.created", "session": {"id": "session-1"}},
                    {"type": "session.updated", "session": {"id": "session-1"}},
                ]
            )

        async def __aenter__(self) -> "Session":
            return self

        async def __aexit__(self, _type: object, _value: object, _traceback: object) -> None:
            return None

        async def next_event(self) -> dict[str, object]:
            return next(self._events)

        async def configure_audio_only_session(self) -> None:
            nonlocal configured
            configured = True

    monkeypatch.setattr(openai_realtime, "OpenAIRealtimeSession", Session)
    settings = Settings.model_construct(
        openai_api_key="test-key",
        openai_realtime_model="gpt-realtime-2.1",
        openai_realtime_voice="marin",
    )

    result = await preflight(settings)

    assert configured is True
    assert result.session_id == "session-1"
    assert result.input_format == "audio/pcm@24000"


def test_realtime_requires_backend_key_and_configuration() -> None:
    assert Settings.model_construct(openai_api_key="test-key").realtime_configured is True
    assert Settings.model_construct(openai_api_key=None).realtime_configured is False
