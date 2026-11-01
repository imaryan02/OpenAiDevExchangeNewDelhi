"""Friday's VoiceLink A-law/Realtime gateway. No receptionist tools or prompts."""

import asyncio
import base64
import json
import time
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import get_session_factory
from app.integrations.openai_realtime import OpenAIRealtimeSession
from app.personal_agent.config import PersonalSettings
from app.personal_agent.repository import PersonalRepository
from app.personal_agent.service import PersonalRuntime
from app.voice.codec import Pcm24kToAlaw8k, alaw8k_to_pcm24k, pcm16_sample_to_alaw
from app.voice.gateway import VoiceProtocolError
from app.voice.voicelink_gateway import _is_outbound_media

logger = structlog.get_logger()


async def receive_personal_voicelink_input(
    websocket: WebSocket,
    incoming: asyncio.Queue[dict[str, Any] | Exception],
    startup_stop: asyncio.Event,
    call_sid: str,
) -> None:
    """Drain the carrier socket while route lookup and Realtime are starting."""
    started = time.monotonic()
    media_frames = 0
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                raise VoiceProtocolError("Invalid personal stream event.")
            kind = message.get("event")
            if kind == "media":
                media_frames += 1
            await incoming.put(message)
            if kind == "stop":
                startup_stop.set()
                logger.info(
                    "personal_voicelink_provider_stop",
                    call_sid=call_sid,
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                    media_frames=media_frames,
                )
                return
    except asyncio.CancelledError:
        raise
    except Exception as error:
        startup_stop.set()
        logger.info(
            "personal_voicelink_provider_disconnected",
            call_sid=call_sid,
            elapsed_ms=round((time.monotonic() - started) * 1000),
            media_frames=media_frames,
            close_code=error.code if isinstance(error, WebSocketDisconnect) else None,
            error_type=type(error).__name__,
        )
        await incoming.put(error)


async def stream_startup_audio(
    websocket: WebSocket,
    stream_sid: str,
    stop: asyncio.Event,
    send_lock: asyncio.Lock,
    greeting_started: asyncio.Event,
) -> None:
    """Greet immediately, then keep the outbound leg alive while Friday starts."""
    try:
        greeting = Path(__file__).with_name("friday_hi_boss.alaw").read_bytes()
    except OSError:
        greeting = b""
        logger.warning("personal_voicelink_opening_audio_missing")
    silence = bytes([pcm16_sample_to_alaw(0)]) * 160
    started = time.monotonic()
    frames = 0
    greeting_frames = 0
    offset = 0
    try:
        while not stop.is_set():
            chunk = greeting[offset : offset + 160] if offset < len(greeting) else silence
            payload = {
                "event": "media",
                "media": {"payload": base64.b64encode(chunk).decode()},
                "stream_sid": stream_sid,
            }
            async with send_lock:
                if stop.is_set():
                    break
                await websocket.send_json(payload)
            frames += 1
            if offset < len(greeting):
                greeting_frames += 1
                offset += len(chunk)
                if greeting_frames == 1:
                    greeting_started.set()
                    logger.info("personal_voicelink_opening_audio_sent", stream_sid=stream_sid)
            elif frames == 1:
                logger.info("personal_voicelink_startup_media_sent", stream_sid=stream_sid)
            try:
                await asyncio.wait_for(stop.wait(), timeout=len(chunk) / 8000)
            except TimeoutError:
                pass
    except (RuntimeError, WebSocketDisconnect):
        # The carrier may close before Friday's voice session is ready.
        pass
    finally:
        logger.info(
            "personal_voicelink_startup_media_ended",
            stream_sid=stream_sid,
            frames=frames,
            greeting_frames=greeting_frames,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )


class PersonalVoiceLinkGateway:
    def __init__(
        self,
        settings: Settings,
        config: PersonalSettings,
        context: dict[str, str],
        call_id: UUID,
        generation: int,
        *,
        startup_silence_stop: asyncio.Event | None = None,
        send_lock: asyncio.Lock | None = None,
        opening_greeting_started: asyncio.Event | None = None,
        incoming_events: asyncio.Queue[dict[str, Any] | Exception] | None = None,
    ) -> None:
        assert settings.database_url
        self.settings, self.config, self.context = settings, config, context
        self.sessions = get_session_factory(settings.database_url)
        self.runtime = PersonalRuntime(
            self.sessions, config, call_id=call_id, generation=generation
        )
        self.call_id = call_id
        self.realtime = OpenAIRealtimeSession(settings)
        self.audio: asyncio.Queue[tuple[int, bytes | str]] = asyncio.Queue(maxsize=500)
        self.epoch = 0
        self.converter = self._new_converter()
        self.active_response = False
        self.pending_response = False
        self.discarded: set[str] = set()
        self.active_item = ""
        self.response_id = ""
        self.discarded_responses: set[str] = set()
        self.active_mark = ""
        self.tool_count = 0
        self.send_lock = send_lock or asyncio.Lock()
        self.startup_silence_stop = startup_silence_stop
        self.opening_greeting_started = opening_greeting_started
        self.incoming_events = incoming_events
        self.started_at = time.monotonic()
        self.first_audio_generated = False
        self.first_audio_sent = False
        self.opening_interrupted = False

    async def run(self, websocket: WebSocket) -> None:
        failed = True
        tasks: list[asyncio.Task[None]] = []
        try:
            prepared = await self.runtime.prepare()
            await self.realtime.connect()
            await self._expect("session.created")
            instructions = prepared["instructions"]
            if self.opening_greeting_started is not None and self.opening_greeting_started.is_set():
                instructions += (
                    "\nThe caller has already heard your opening 'Hi Boss.' greeting "
                    "on this call. Wait for Aryan's request and do not repeat it."
                )
            await self.realtime.configure_voice_session(
                instructions, tools=prepared["tools"]
            )
            await self._expect("session.updated")
            logger.info(
                "personal_voicelink_realtime_ready",
                call_sid=self.context["call_sid"],
                elapsed_ms=round((time.monotonic() - self.started_at) * 1000),
            )
            tasks = [
                asyncio.create_task(self._incoming(websocket)),
                asyncio.create_task(self._model(websocket)),
                asyncio.create_task(self._playback(websocket)),
                asyncio.create_task(self._heartbeat()),
            ]
            # The owner leads both inbound and callback conversations. Keep the
            # callback reason in context until he asks for it.
            if self.opening_greeting_started is None or not self.opening_greeting_started.is_set():
                await self._respond(
                    "Say exactly 'Hi Boss.' and nothing else. This is only the opening "
                    "greeting. Do not explain the call, ask a question, or use a tool. "
                    "Stop speaking and wait for Aryan to speak."
                )
            async with asyncio.timeout(self.config.max_call_seconds):
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    await task
            failed = False
        except WebSocketDisconnect:
            failed = False
        finally:
            if self.startup_silence_stop is not None:
                self.startup_silence_stop.set()
            logger.info(
                "personal_voicelink_stream_ended",
                call_sid=self.context["call_sid"],
                elapsed_ms=round((time.monotonic() - self.started_at) * 1000),
                first_audio_generated=self.first_audio_generated,
                first_audio_sent=self.first_audio_sent,
                opening_interrupted=self.opening_interrupted,
                failed=failed,
            )
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.realtime.aclose()
            with suppress(Exception):
                async with self.sessions.begin() as session:
                    repo = PersonalRepository(session, self.runtime.owner_id)
                    await session.execute(
                        text("""update public.personal_agent_calls set status=:status,ended_at=now()
                                where owner_id=:owner and id=:id and status='active'"""),
                        {
                            "owner": self.runtime.owner_id,
                            "id": self.call_id,
                            "status": "failed" if failed else "ended",
                        },
                    )
                    await repo.activity(
                        "call_failed" if failed else "call_ended",
                        "Personal AI call failed" if failed else "Personal AI call ended",
                        call_id=self.call_id,
                    )

    async def _expect(self, kind: str) -> None:
        async with asyncio.timeout(self.settings.openai_realtime_connect_timeout_seconds):
            while True:
                event = await self.realtime.receive_event()
                if event.get("type") == kind:
                    return
                if event.get("type") == "error":
                    raise VoiceProtocolError("Personal Realtime startup rejected.")

    async def _send(
        self, websocket: WebSocket, payload: dict[str, Any], *, epoch: int | None = None
    ) -> None:
        async with self.send_lock:
            if epoch is not None and epoch != self.epoch:
                return
            await websocket.send_json({**payload, "stream_sid": self.context["stream_sid"]})

    def _new_converter(self) -> Pcm24kToAlaw8k:
        return Pcm24kToAlaw8k()

    def _decode_audio(self, encoded: bytes) -> bytes:
        return alaw8k_to_pcm24k(encoded)

    async def _respond(self, instructions: str | None = None) -> None:
        if self.active_response:
            self.pending_response = True
            return
        self.active_response = True
        response = {"instructions": instructions, "tool_choice": "none"} if instructions else {}
        await self.realtime.send({"type": "response.create", "response": response})

    async def _incoming(self, websocket: WebSocket) -> None:
        while True:
            if self.incoming_events is None:
                message = await websocket.receive_json()
            else:
                item = await self.incoming_events.get()
                if isinstance(item, Exception):
                    raise item
                message = item
            kind = message.get("event")
            if kind == "stop":
                return
            if kind == "start":
                raise VoiceProtocolError("Duplicate personal stream start.")
            if kind == "mark":
                mark = message.get("mark")
                if isinstance(mark, dict) and mark.get("name") == self.active_mark:
                    self.active_item = ""
                    self.active_mark = ""
                continue
            if kind != "media" or _is_outbound_media(message):
                continue
            media = message.get("media")
            if not isinstance(media, dict) or not isinstance(media.get("payload"), str):
                raise VoiceProtocolError("Invalid personal media payload.")
            payload = media["payload"]
            if len(payload) > 64000:
                raise VoiceProtocolError("Personal media frame is too large.")
            try:
                encoded = base64.b64decode(payload, validate=True)
                pcm = self._decode_audio(encoded)
            except ValueError as error:
                raise VoiceProtocolError("Invalid personal audio encoding.") from error
            await self.realtime.send(
                {"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()}
            )

    async def _playback(self, websocket: WebSocket) -> None:
        while True:
            epoch, audio = await self.audio.get()
            if isinstance(audio, str):
                await self._send(websocket, {"event": "mark", "mark": {"name": audio}}, epoch=epoch)
                continue
            for offset in range(0, len(audio), 160):
                if epoch != self.epoch:
                    break
                chunk = audio[offset : offset + 160]
                if self.startup_silence_stop is not None:
                    self.startup_silence_stop.set()
                await self._send(
                    websocket,
                    {"event": "media", "media": {"payload": base64.b64encode(chunk).decode()}},
                    epoch=epoch,
                )
                if not self.first_audio_sent:
                    self.first_audio_sent = True
                    logger.info(
                        "personal_voicelink_first_audio_sent",
                        call_sid=self.context["call_sid"],
                        elapsed_ms=round((time.monotonic() - self.started_at) * 1000),
                    )
                await asyncio.sleep(len(chunk) / 8000)

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(15)
            async with self.sessions.begin() as session:
                result = await session.execute(
                    text("""update public.personal_agent_calls set heartbeat_at=now()
                            where owner_id=:owner and id=:id and status='active'
                            and generation=(select generation from public.personal_agent_profiles
                                            where owner_id=:owner) returning id"""),
                    {"owner": self.runtime.owner_id, "id": self.call_id},
                )
                if result.scalar_one_or_none() is None:
                    raise VoiceProtocolError("Personal call was invalidated.")

    async def _model(self, websocket: WebSocket) -> None:
        while True:
            event = await self.realtime.receive_event()
            kind = event.get("type")
            if kind == "error":
                # A server VAD cancellation can race our explicit interruption.
                if event.get("error", {}).get("code") == "response_cancel_not_active":
                    continue
                raise VoiceProtocolError("Personal Realtime stream failed.")
            if kind == "input_audio_buffer.speech_started":
                if not self.first_audio_sent:
                    self.opening_interrupted = True
                    logger.info(
                        "personal_voicelink_opening_interrupted",
                        call_sid=self.context["call_sid"],
                        elapsed_ms=round((time.monotonic() - self.started_at) * 1000),
                    )
                self.epoch += 1
                if self.active_response and self.response_id:
                    self.discarded_responses.add(self.response_id)
                if self.active_item:
                    self.discarded.add(self.active_item)
                self.converter = self._new_converter()
                while not self.audio.empty():
                    self.audio.get_nowait()
                await self._send(websocket, {"event": "clear"})
                if self.active_response:
                    await self.realtime.send({"type": "response.cancel"})
                # No carrier evidence of heard length: truncate interrupted audio to zero.
                if self.active_item:
                    await self.realtime.send(
                        {
                            "type": "conversation.item.truncate",
                            "item_id": self.active_item,
                            "content_index": 0,
                            "audio_end_ms": 0,
                        }
                    )
                self.active_item = ""
                self.active_mark = ""
            elif kind == "response.created":
                self.response_id = str(event.get("response", {}).get("id") or "")
            elif kind == "conversation.item.input_audio_transcription.completed":
                transcript = str(event.get("transcript") or "").strip()
                if transcript:
                    await self.runtime.remember(
                        source_id=str(event.get("item_id") or ""),
                        speaker="caller",
                        content=transcript,
                    )
                    await self._respond()
            elif kind in {"response.output_audio.delta", "response.audio.delta"}:
                if not self.first_audio_generated:
                    self.first_audio_generated = True
                    logger.info(
                        "personal_voicelink_first_audio_generated",
                        call_sid=self.context["call_sid"],
                        elapsed_ms=round((time.monotonic() - self.started_at) * 1000),
                    )
                item = str(event.get("item_id") or "")
                if item in self.discarded or event.get("response_id") in self.discarded_responses:
                    continue
                self.active_item = item
                try:
                    audio = self.converter.feed(
                        base64.b64decode(event.get("delta", ""), validate=True)
                    )
                    if audio:
                        self.audio.put_nowait((self.epoch, audio))
                except (ValueError, asyncio.QueueFull) as error:
                    raise VoiceProtocolError(
                        "Invalid or excessive personal output audio."
                    ) from error
            elif kind in {"response.output_audio.done", "response.audio.done"}:
                item = str(event.get("item_id") or "")
                if (
                    item
                    and item not in self.discarded
                    and event.get("response_id") not in self.discarded_responses
                ):
                    self.active_mark = f"personal-{self.epoch}-{item}"
                    try:
                        self.audio.put_nowait((self.epoch, self.active_mark))
                    except asyncio.QueueFull as error:
                        raise VoiceProtocolError(
                            "Personal playback queue exceeded its limit."
                        ) from error
            elif kind == "response.done":
                self.active_response = False
                response = event.get("response", {})
                logger.info(
                    "personal_voicelink_response_done",
                    call_sid=self.context["call_sid"],
                    elapsed_ms=round((time.monotonic() - self.started_at) * 1000),
                    response_status=response.get("status"),
                    first_audio_generated=self.first_audio_generated,
                    first_audio_sent=self.first_audio_sent,
                )
                if response.get("status") == "failed":
                    raise VoiceProtocolError("Personal model response failed.")
                tools = False
                if (
                    response.get("status") == "completed"
                    and response.get("id") not in self.discarded_responses
                ):
                    for item in response.get("output", []):
                        if item.get("type") == "function_call":
                            tools = True
                            await self._tool(item)
                        elif item.get("type") == "message" and item.get("id") not in self.discarded:
                            transcript = " ".join(
                                str(part.get("transcript") or "")
                                for part in item.get("content", [])
                            )
                            if transcript.strip():
                                await self.runtime.remember(
                                    source_id=str(item.get("id") or ""),
                                    speaker="assistant",
                                    content=transcript,
                                )
                if tools or self.pending_response:
                    self.pending_response = False
                    await self._respond()

    async def _tool(self, item: dict[str, Any]) -> None:
        self.tool_count += 1
        if self.tool_count > 128:
            raise VoiceProtocolError("Personal tool budget exceeded.")
        request_id = str(item.get("call_id") or "")
        try:
            raw = item.get("arguments", "{}")
            if not isinstance(raw, str) or len(raw) > 12000:
                raise ValueError("Invalid tool input")
            arguments = json.loads(raw)
            if not isinstance(arguments, dict):
                raise ValueError("Invalid tool input")
        except (ValueError, TypeError):
            result = {"ok": False, "message": "Invalid tool arguments; clarify and retry."}
        else:
            result = await self.runtime.execute(request_id, str(item.get("name") or ""), arguments)
        await self.realtime.send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": request_id,
                    "output": json.dumps(result),
                },
            }
        )
