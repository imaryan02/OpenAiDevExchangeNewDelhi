import asyncio
import base64
import json
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_graph, build_tools
from app.core.config import Settings
from app.integrations.openai_audio import OpenAIAudioClient, TranscriptionResult
from app.voice import voicelink_gateway as gateway_module
from app.voice.codec import AlawTurnDetector, pcm16_sample_to_alaw
from app.voice.voicelink_gateway import VoiceLinkVoiceGateway, _is_self_echo


def test_barge_in_requires_sustained_speech_and_preserves_start_of_utterance() -> None:
    detector = AlawTurnDetector(onset_frames=5, min_speech_frames=5, end_silence_frames=3)
    voice = bytes([pcm16_sample_to_alaw(5000)]) * 160
    quiet = bytes([pcm16_sample_to_alaw(0)]) * 160
    assert not detector.feed(voice).speech_started
    for _ in range(3):
        assert not detector.feed(quiet).speech_started
    for _ in range(4):
        assert not detector.feed(voice).speech_started
    assert detector.feed(voice).speech_started
    assert not detector.feed(voice).speech_started
    detector.feed(quiet)
    detector.feed(quiet)
    result = detector.feed(quiet)
    assert result.utterance is not None and voice * 6 in result.utterance
    assert not detector.is_speaking


@pytest.mark.asyncio
async def test_voicelink_preserves_completed_turns_while_worker_is_busy() -> None:
    settings = Settings.model_construct(
        database_url="postgresql+asyncpg://unused",
        voicelink_phone_number="+919800000001",
        voice_organization_id=uuid4(),
        voice_actor_id=uuid4(),
    )
    gateway = VoiceLinkVoiceGateway(settings)
    captured_queue: asyncio.Queue[bytes | None] | None = None

    async def blocked_worker(_websocket: Any, turns: asyncio.Queue[bytes | None],
                             _context: dict[str, str]) -> None:
        nonlocal captured_queue
        captured_queue = turns
        await asyncio.Event().wait()

    gateway._process_turns = blocked_worker  # type: ignore[method-assign]
    voice = bytes([pcm16_sample_to_alaw(5000)]) * 160
    silence = bytes([pcm16_sample_to_alaw(0)]) * 160
    one_turn = [voice] * 10 + [silence] * 25

    class Socket:
        def __init__(self) -> None:
            self.messages = [
                {
                    "event": "start",
                    "start": {
                        "stream_sid": "stream-ordered",
                        "call_sid": "call-ordered",
                        "media_format": {"encoding": "audio/alaw", "sample_rate": 8000},
                        "caller": "+919800000002",
                        "called": "+919800000001",
                    },
                },
                *[
                    {
                        "event": "media",
                        "media": {"payload": base64.b64encode(frame).decode()},
                    }
                    for frame in one_turn + one_turn
                ],
                {"event": "stop"},
            ]

        async def receive_json(self) -> dict[str, Any]:
            await asyncio.sleep(0)
            return self.messages.pop(0)

        async def send_json(self, _payload: dict[str, object]) -> None:
            return None

    await gateway.run(Socket())  # type: ignore[arg-type]

    assert captured_queue is not None
    assert captured_queue.qsize() == 2


@pytest.mark.parametrize("reply", ["Ji", "Theek hai", "Dr Amit", "kal shaam 5 baje"])
def test_short_caller_repetitions_are_not_dropped_as_echo(reply: str) -> None:
    assert not _is_self_echo(reply, [reply])


@pytest.mark.asyncio
async def test_clinic_information_is_callable_by_the_actual_agent_graph() -> None:
    executed = []
    lookup_started = []

    class Executor:
        async def execute(self, name: str, args: dict) -> dict:
            executed.append((name, args))
            return {"ok": True, "locations": [{"name": "Main", "address": "Demo Road"}]}

    class Model:
        def bind_tools(self, tools: list, **kwargs: Any) -> "Model":
            assert "get_clinic_information" in {t.name for t in tools}
            return self

        async def ainvoke(self, messages: list) -> AIMessage:
            if isinstance(messages[-1], ToolMessage):
                assert json.loads(messages[-1].content)["locations"][0]["address"] == "Demo Road"
                return AIMessage(content="Our main clinic is on Demo Road.")
            return AIMessage(content="", tool_calls=[{
                "name": "get_clinic_information", "args": {"topic": "address"}, "id": "lookup",
            }])

    graph = build_graph(cast(Any, Model()), build_tools(cast(Any, Executor())), InMemorySaver(),
                        on_lookup_start=lambda: lookup_started.append(True))
    result = await graph.ainvoke({"messages": [HumanMessage(content="Where is the clinic?")]},
                                 {"configurable": {"thread_id": str(uuid4())}})
    assert executed == [("get_clinic_information", {"topic": "address"})]
    assert lookup_started == [True]
    assert result["messages"][-1].content == "Our main clinic is on Demo Road."


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
async def test_playback_waits_before_next_reply_or_silence_timer(streaming: bool) -> None:
    audio = AsyncMock()
    gateway = VoiceLinkVoiceGateway(Settings.model_construct(), audio)
    mark_sent = asyncio.Event()

    class WebSocket:
        async def send_json(self, payload: dict) -> None:
            if payload["event"] == "mark":
                mark_sent.set()

    async def stream():
        yield b"\x55" * 8000

    socket = cast(Any, WebSocket())
    playback = asyncio.create_task(gateway._play_stream(socket, stream()) if streaming
                                   else gateway._play(socket, b"\x55" * 8000))
    await asyncio.wait_for(mark_sent.wait(), 1)
    await asyncio.sleep(0)
    assert not playback.done()  # all bytes sent is not the same as all audio heard
    gateway._playback_done.set()  # provider mark / interruption releases the wait
    await asyncio.wait_for(playback, 1)
    assert gateway._active_mark == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("lookup", [False, True])
async def test_slow_model_only_gets_filler_after_an_actual_lookup(
    monkeypatch: pytest.MonkeyPatch, lookup: bool,
) -> None:
    settings = Settings.model_construct(database_url="unused")
    audio = AsyncMock(spec=OpenAIAudioClient)
    audio.transcribe_alaw_with_usage.return_value = TranscriptionResult(
        text="Doctor available hain?", usage=None,
        request_id="test-transcription", identity_source="local",
    )
    audio.synthesize_alaw.return_value = b"greeting-or-filler"
    gateway = VoiceLinkVoiceGateway(settings, audio)
    gateway.FILLER_DELAY_SECONDS = 0.01
    gateway._play = AsyncMock()  # type: ignore[method-assign]
    gateway._play_stream = AsyncMock(return_value=None)  # type: ignore[method-assign]
    monkeypatch.setattr(VoiceLinkVoiceGateway, "_filler_cache", {})

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Executor:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, *args):
            return {"ok": True, "caller_name": "Aryan Gupta"}

    class Agent:
        def __init__(self, settings):
            pass

        async def respond(self, *args, **kwargs):
            if lookup:
                kwargs["on_lookup_start"]()
            await asyncio.sleep(0.03)
            return {"reply": "Doctor Amit kal available hain."}

    monkeypatch.setattr(gateway_module, "get_session_factory", lambda _: Session)
    monkeypatch.setattr(gateway_module, "ToolExecutor", Executor)
    monkeypatch.setattr(gateway_module, "ReceptionAgent", Agent)
    turns: asyncio.Queue[bytes | None] = asyncio.Queue()
    turns.put_nowait(b"caller-audio")
    turns.put_nowait(None)
    await gateway._process_turns(cast(Any, object()), turns, {
        "organization_id": str(uuid4()), "actor_id": str(uuid4()),
        "caller": "+919800000001", "call_sid": "test",
    })
    assert gateway._play.await_count == (1 if lookup else 0)  # optional filler
    assert gateway._play_stream.await_count == 2  # streamed greeting and reply
    audio.transcribe_alaw_with_usage.assert_awaited_once_with(b"caller-audio")
    await asyncio.gather(*gateway._background_tasks)


@pytest.mark.asyncio
async def test_single_noise_packet_does_not_clear_playback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def idle(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(VoiceLinkVoiceGateway, "_process_turns", idle)
    settings = Settings.model_construct(voice_organization_id=uuid4(), voice_actor_id=uuid4(),
                                        voicelink_phone_number="+919800000001")
    gateway = VoiceLinkVoiceGateway(settings, AsyncMock())
    gateway._active_mark = "playing"
    voice = bytes([pcm16_sample_to_alaw(5000)]) * 160
    incoming = iter([
        {"event": "start", "start": {"stream_sid": "s", "call_sid": "c",
            "caller": "+919800000002", "called": "+919800000001",
            "media_format": {"encoding": "audio/alaw", "sample_rate": 8000}}},
        {"event": "media", "media": {"payload": base64.b64encode(voice).decode()}},
        {"event": "stop"},
    ])
    socket = AsyncMock()
    socket.receive_json.side_effect = lambda: next(incoming)
    await gateway.run(socket)
    assert not any(call.args[0]["event"] == "clear" for call in socket.send_json.call_args_list)


@pytest.mark.asyncio
async def test_silence_recovery_does_not_fire_during_greeting_or_restart_booking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class Executor:
        def __init__(self, *args, **kwargs):
            pass

        async def execute(self, *args):
            return {"ok": True}

    monkeypatch.setattr(gateway_module, "get_session_factory", lambda _: Session)
    monkeypatch.setattr(gateway_module, "ToolExecutor", Executor)
    monkeypatch.setattr(VoiceLinkVoiceGateway, "_filler_cache", {})
    audio = AsyncMock()
    audio.synthesize_alaw.return_value = b"\x55" * 8000
    async def greeting_stream(text):
        yield b"\x55" * 8000
    audio.stream_synthesize_alaw = greeting_stream
    gateway = VoiceLinkVoiceGateway(Settings.model_construct(database_url="unused"), audio)
    gateway.SILENCE_TIMEOUT_SECONDS = 0.01
    greeting_queued = asyncio.Event()
    marks = 0

    class Socket:
        async def send_json(self, payload):
            nonlocal marks
            if payload["event"] == "mark":
                marks += 1
                if marks == 1:
                    greeting_queued.set()
                else:
                    gateway._playback_done.set()

    task = asyncio.create_task(gateway._process_turns(cast(Any, Socket()), asyncio.Queue(), {
        "organization_id": str(uuid4()), "actor_id": str(uuid4()),
        "caller": "+919800000001", "call_sid": "silence-test",
    }))
    try:
        await asyncio.wait_for(greeting_queued.wait(), 1)
        await asyncio.sleep(0.04)  # several silence intervals while greeting still plays
        assert marks == 1
        gateway._playback_done.set()
        await asyncio.wait_for(task, 1)
        assert marks == 3  # greeting, one contextual reprompt, farewell
        spoken = [call.args[0] for call in audio.synthesize_alaw.call_args_list]
        assert any("pichhli baat" in text for text in spoken)
        assert not any("kiske liye appointment" in text or "Medicine se bol" in text for text in spoken)
    finally:
        task.cancel()
        await asyncio.gather(task, *gateway._background_tasks, return_exceptions=True)
