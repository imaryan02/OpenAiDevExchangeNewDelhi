import asyncio
import base64
import json
import re
import time
from contextlib import suppress
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from fastapi import WebSocket

from app.agent.service import ReceptionAgent
from app.agent.tools import ToolExecutor
from app.core.config import Settings
from app.db.session import get_session_factory
from app.integrations.openai_audio import OpenAIAudioClient
from app.voice.codec import MulawTurnDetector
from app.voice.security import verify_stream_binding

logger = structlog.get_logger()


class VoiceProtocolError(Exception):
    pass


class TwilioVoiceGateway:
    def __init__(
        self,
        settings: Settings,
        audio: OpenAIAudioClient | None = None,
    ) -> None:
        self._settings = settings
        self._audio = audio or OpenAIAudioClient(settings)
        self._stream_sid = ""
        self._active_mark = ""
        self._send_lock = asyncio.Lock()

    async def run(self, websocket: WebSocket) -> None:
        if not self._settings.database_url or not self._settings.verification_code_pepper:
            raise VoiceProtocolError("Voice database or signing configuration is incomplete.")
        detector = MulawTurnDetector()
        turns: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=1)
        worker: asyncio.Task[None] | None = None
        binding: dict[str, str] | None = None
        try:
            while True:
                message = await websocket.receive_json()
                event = str(message.get("event", ""))
                if event == "connected":
                    continue
                if event == "start":
                    if binding is not None:
                        raise VoiceProtocolError("Duplicate stream start event.")
                    binding = self._validate_start(message)
                    self._stream_sid = str(message.get("streamSid", ""))
                    worker = asyncio.create_task(self._process_turns(websocket, turns, binding))
                    continue
                if event == "media":
                    if binding is None:
                        raise VoiceProtocolError("Media arrived before stream start.")
                    frame = self._decode_media(message)
                    turn = detector.feed(frame)
                    if turn.speech_started and self._active_mark:
                        await self._send(
                            websocket,
                            {"event": "clear", "streamSid": self._stream_sid},
                        )
                        self._active_mark = ""
                    if turn.utterance:
                        if turns.full():
                            with suppress(asyncio.QueueEmpty):
                                turns.get_nowait()
                        turns.put_nowait(turn.utterance)
                    continue
                if event == "mark":
                    name = str(message.get("mark", {}).get("name", ""))
                    if name == self._active_mark:
                        self._active_mark = ""
                    continue
                if event == "stop":
                    break
        finally:
            if worker is not None:
                if turns.full():
                    with suppress(asyncio.QueueEmpty):
                        turns.get_nowait()
                turns.put_nowait(None)
                with suppress(asyncio.CancelledError):
                    await worker
            await self._audio.aclose()

    def _validate_start(self, message: dict[str, Any]) -> dict[str, str]:
        start = message.get("start")
        if not isinstance(start, dict):
            raise VoiceProtocolError("Missing stream start payload.")
        media = start.get("mediaFormat", {})
        if (
            media.get("encoding") != "audio/x-mulaw"
            or int(media.get("sampleRate", 0)) != 8000
            or int(media.get("channels", 0)) != 1
        ):
            raise VoiceProtocolError("Unsupported telephone audio format.")
        parameters = start.get("customParameters", {})
        token = str(parameters.get("binding", "")) if isinstance(parameters, dict) else ""
        secret = self._settings.verification_code_pepper or ""
        binding = verify_stream_binding(token, secret)
        if binding is None or binding["call_sid"] != str(start.get("callSid", "")):
            raise VoiceProtocolError("Invalid stream binding.")
        if str(start.get("accountSid", "")) != (self._settings.twilio_account_sid or ""):
            raise VoiceProtocolError("Unexpected Twilio account.")
        return binding

    @staticmethod
    def _decode_media(message: dict[str, Any]) -> bytes:
        media = message.get("media")
        if not isinstance(media, dict):
            raise VoiceProtocolError("Missing media payload.")
        try:
            payload = base64.b64decode(str(media.get("payload", "")), validate=True)
        except ValueError as error:
            raise VoiceProtocolError("Invalid media encoding.") from error
        if not payload or len(payload) > 4096:
            raise VoiceProtocolError("Invalid media frame size.")
        return payload

    async def _process_turns(
        self,
        websocket: WebSocket,
        turns: asyncio.Queue[bytes | None],
        binding: dict[str, str],
    ) -> None:
        organization_id = UUID(binding["organization_id"])
        actor_id = UUID(binding["actor_id"])
        thread_id = uuid5(NAMESPACE_URL, f"twilio:{binding['call_sid']}")
        session_factory = get_session_factory(self._settings.database_url or "")
        async with session_factory() as session:
            caller_context = await ToolExecutor(
                session,
                organization_id,
                actor_id=actor_id,
                settings=self._settings,
                caller_phone_e164=binding["caller"],
            ).execute("lookup_caller_family", {"phone_e164": binding["caller"]})
        while True:
            utterance = await turns.get()
            if utterance is None:
                return
            try:
                started_at = time.perf_counter()
                transcript = await self._audio.transcribe_mulaw(utterance)
                transcribed_at = time.perf_counter()
                if not transcript:
                    continue
                trusted_context = (
                    "[Trusted voice gateway context: incoming caller ID is "
                    f"{binding['caller']}. Caller/family lookup result: "
                    f"{json.dumps(caller_context, default=str)}. The lookup is already complete; "
                    "do not call lookup_caller_family again. Recognition does not verify access "
                    "to private appointment details. Follow the phone-call identity flow in the "
                    "system instructions.]\nCaller said: "
                )
                async with session_factory() as session:
                    result = await ReceptionAgent(self._settings).respond(
                        trusted_context + transcript,
                        session,
                        organization_id,
                        actor_id,
                        thread_id,
                        caller_phone=binding["caller"],
                        booking_source="AI_VOICE",
                        booking_consent_channel="AI_VOICE",
                        allow_appointment_mutations=False,
                    )
                responded_at = time.perf_counter()
                reply = re.sub(r"[*_#`]", "", str(result["reply"])).strip()
                audio = await self._audio.synthesize_mulaw(reply)
                synthesized_at = time.perf_counter()
                await self._play(websocket, audio)
                logger.info(
                    "voice_turn_latency",
                    call_sid=binding["call_sid"],
                    stt_ms=round((transcribed_at - started_at) * 1000),
                    agent_ms=round((responded_at - transcribed_at) * 1000),
                    tts_ms=round((synthesized_at - responded_at) * 1000),
                )
            except Exception as error:
                logger.warning(
                    "voice_turn_failed",
                    call_sid=binding["call_sid"],
                    error_type=type(error).__name__,
                )

    async def _play(self, websocket: WebSocket, audio: bytes) -> None:
        if not audio:
            return
        for offset in range(0, len(audio), 160):
            payload = base64.b64encode(audio[offset : offset + 160]).decode()
            await self._send(
                websocket,
                {"event": "media", "streamSid": self._stream_sid, "media": {"payload": payload}},
            )
        self._active_mark = f"reply-{id(audio)}"
        await self._send(
            websocket,
            {
                "event": "mark",
                "streamSid": self._stream_sid,
                "mark": {"name": self._active_mark},
            },
        )

    async def _send(self, websocket: WebSocket, payload: dict[str, object]) -> None:
        async with self._send_lock:
            await websocket.send_json(payload)
