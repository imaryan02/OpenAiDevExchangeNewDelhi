import asyncio
import base64
import json
import re
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from fastapi import WebSocket

from app.agent.service import ReceptionAgent
from app.agent.tools import ToolExecutor
from app.core.config import Settings
from app.db.session import get_session_factory
from app.integrations.openai_audio import SPEECH_INSTRUCTIONS, OpenAIAudioClient
from app.voice import presentation
from app.voice.codec import AlawTurnDetector
from app.voice.events import VoiceEvent, VoiceEventType
from app.voice.gateway import VoiceProtocolError

logger = structlog.get_logger()


@dataclass(frozen=True)
class CapturedTurn:
    caller_turn_id: int
    audio: bytes
    captured_at: float


def _phone_digits(value: object) -> str:
    return re.sub(r"\D", "", str(value))


def _normalize_e164_phone(value: object) -> str:
    digits = _phone_digits(value)
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = f"91{digits[1:]}"
    elif len(digits) == 10:
        digits = f"91{digits}"
    return f"+{digits}" if 8 <= len(digits) <= 15 else ""


def _is_outbound_media(message: dict[str, Any]) -> bool:
    media = message.get("media")
    if not isinstance(media, dict):
        return False
    track = str(media.get("track") or "").casefold()
    direction = str(media.get("direction") or "").casefold()
    source = str(media.get("source") or message.get("source") or "").casefold()
    outbound_values = {"outbound", "output", "bot", "playback"}
    return (
        track in outbound_values
        or "outbound" in track
        or direction in outbound_values
        or "outbound" in direction
        or source in outbound_values
        or "outbound" in source
    )


def _split_sentences(text: str) -> list[str]:
    """Split text into spoken sentences while protecting clinic titles, abbreviations, and numbers."""
    cleaned = text.strip()
    if not cleaned:
        return []
    protected = cleaned
    for abbr in ("Dr.", "dr.", "Mr.", "mr.", "Mrs.", "mrs.", "Ms.", "ms.", "Prof.", "Pt.", "Sh."):
        protected = re.sub(re.escape(abbr), abbr[:-1] + "§", protected)
    protected = re.sub(r"(\d)\.(\d)", r"\1§\2", protected)
    parts = [part.strip() for part in re.split(r"(?<=[.!?\n])\s+", protected) if part.strip()]
    return [part.replace("§", ".") for part in parts] or [cleaned]


def _longest_common_ngram(words1: list[str], words2: list[str]) -> int:
    m, n = len(words1), len(words2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    max_len = 0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if words1[i - 1] == words2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
                if dp[i][j] > max_len:
                    max_len = dp[i][j]
    return max_len


HUMAN_REQUEST_PHRASES = (
    "transfer",
    "human",
    "operator",
    "representative",
    "executive",
    "agent",
    "insan",
    "aadmi",
    "kisi se baat",
    "baat karwao",
    "baat karao",
    "customer care",
    "helpline",
    "staff",
)


def _is_human_request(text: str) -> bool:
    normalized = " ".join(re.sub(r"[^\w\s\u0900-\u097f]+", " ", text.casefold()).split())
    return any(p in normalized for p in HUMAN_REQUEST_PHRASES)


def _is_self_echo(transcript: str, recent_bot_replies: list[str]) -> bool:
    """Detect if an incoming transcript is acoustic reflection of the bot's own recent speech."""
    normalized_inbound = re.sub(r"\W+", " ", transcript.casefold()).strip()
    if not normalized_inbound:
        return False
    inbound_words = normalized_inbound.split()
    if len(inbound_words) < 5:
        # Short acknowledgements, names and repeated slot choices are valid caller turns.
        return False

    first_person = {"mujhe", "mera", "meri", "mere", "main", "hum", "humko", "humare", "i", "my", "me"}
    has_first_person = bool(set(inbound_words) & first_person)

    for bot_text in recent_bot_replies:
        normalized_bot = re.sub(r"\W+", " ", bot_text.casefold()).strip()
        if not normalized_bot:
            continue

        # Exact match
        if normalized_inbound == normalized_bot:
            return True
        if not has_first_person and SequenceMatcher(None, normalized_inbound, normalized_bot).ratio() >= 0.85:
            return True

        # Check against individual clauses / sentences of bot text
        clauses = re.split(r"[,.?!;\n]+", bot_text.casefold())
        for clause in clauses:
            norm_clause = re.sub(r"\W+", " ", clause).strip()
            if not norm_clause:
                continue
            if normalized_inbound == norm_clause:
                return True
            if not has_first_person:
                if (
                    len(inbound_words) >= 3
                    and normalized_inbound in norm_clause
                    and len(normalized_inbound) >= 0.70 * len(norm_clause)
                ):
                    return True
                ratio = SequenceMatcher(None, normalized_inbound, norm_clause).ratio()
                if ratio >= 0.85:
                    return True

    return False


class VoiceLinkVoiceGateway:
    """VoiceLink JSON media-stream adapter for G.711 A-law at 8 kHz."""

    DEFAULT_FILLER = "Ji, main check karti hoon."
    FILLER_DELAY_SECONDS = 1.5
    SILENCE_TIMEOUT_SECONDS = 8.5
    _filler_cache: dict[tuple[str, ...], bytes] = {}
    _speech_cache_limit = 128
    _filler_lock = asyncio.Lock()

    def __init__(self, settings: Settings, audio: OpenAIAudioClient | None = None) -> None:
        self._settings = settings
        self._audio = audio or OpenAIAudioClient(settings)
        self._stream_sid = ""
        self._active_mark = ""
        self._playback_until = 0.0
        self._send_lock = asyncio.Lock()
        self._playback_done = asyncio.Event()
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._caller_speaking = False
        self._stream_started_at: float | None = None
        self._first_audio_sent = False

    async def run(self, websocket: WebSocket, *, initial_message: dict[str, Any] | None = None) -> None:
        detector = AlawTurnDetector(onset_frames=5, end_silence_frames=25)
        pending_media = bytearray()
        # Preserve completed caller turns in capture order. Bounded capacity prevents
        # a slow downstream service from accumulating stale confirmations forever.
        turns: asyncio.Queue[CapturedTurn | bytes | None] = asyncio.Queue(
            maxsize=self._settings.voice_max_pending_turns
        )
        captured_turns = 0
        worker: asyncio.Task[None] | None = None
        context: dict[str, str] | None = None
        try:
            while True:
                if initial_message is not None:
                    message = initial_message
                    initial_message = None
                else:
                    message = await websocket.receive_json()
                event = str(message.get("event", ""))
                if event == "connected":
                    continue
                if event == "start":
                    if context is not None:
                        raise VoiceProtocolError("Duplicate stream start event.")
                    context = self._validate_start(message)
                    presentation.start_call(context["caller"], "chained", context["call_sid"])
                    self._stream_sid = context["stream_sid"]
                    self._stream_started_at = time.monotonic()
                    self._emit_event(
                        VoiceEventType.CALL_STARTED,
                        context["call_sid"],
                        engine=self._settings.voice_engine,
                        tts_model=self._settings.openai_tts_model,
                        tts_voice=self._settings.openai_tts_voice,
                    )
                    worker = asyncio.create_task(self._process_turns(websocket, turns, context))
                    continue
                if event == "media":
                    if context is None:
                        raise VoiceProtocolError("Media arrived before stream start.")
                    if _is_outbound_media(message):
                        continue
                    media_bytes = self._decode_media(message)
                    presentation.audio_transfer("input", len(media_bytes), boundary="gateway")
                    pending_media.extend(media_bytes)
                    while len(pending_media) >= 160:
                        frame = bytes(pending_media[:160])
                        del pending_media[:160]
                        turn = detector.feed(frame)
                        self._caller_speaking = detector.is_speaking
                        if turn.speech_started and (self._active_mark or time.monotonic() < self._playback_until):
                            # Real incoming speech barge-in
                            self._active_mark = ""
                            self._playback_until = 0.0
                            self._playback_done.set()
                            logger.info("voicelink_barge_in_triggered", call_sid=context["call_sid"])
                            if self._stream_sid:
                                await self._send(
                                    websocket,
                                    {"event": "clear", "stream_sid": self._stream_sid},
                                )
                        if turn.utterance:
                            captured_turns += 1
                            captured = CapturedTurn(
                                caller_turn_id=captured_turns,
                                audio=turn.utterance,
                                captured_at=time.monotonic(),
                            )
                            if turns.full():
                                self._emit_event(
                                    VoiceEventType.ERROR,
                                    context["call_sid"],
                                    caller_turn_id=captured_turns,
                                    error_code="TURN_BACKLOG_EXCEEDED",
                                    queue_depth=turns.qsize(),
                                )
                                raise VoiceProtocolError("Voice turn backlog exceeded safe capacity.")
                            turns.put_nowait(captured)
                            self._emit_event(
                                VoiceEventType.CALLER_TURN_CAPTURED,
                                context["call_sid"],
                                caller_turn_id=captured_turns,
                                audio_ms=round(len(captured.audio) / 8),
                                queue_depth=turns.qsize(),
                            )
                            logger.info(
                                "voicelink_turn_enqueued",
                                call_sid=context["call_sid"],
                                captured_turn=captured_turns,
                                audio_ms=round(len(turn.utterance) / 8),
                                queue_depth=turns.qsize(),
                            )
                    continue
                if event == "mark":
                    name = str(message.get("mark", {}).get("name", ""))
                    if name == self._active_mark:
                        self._active_mark = ""
                        self._playback_until = 0.0
                        self._playback_done.set()
                    continue
                if event == "stop":
                    break
        finally:
            if context is not None:
                self._emit_event(VoiceEventType.CALL_ENDED, context["call_sid"])
            self._active_mark = ""
            self._playback_until = 0.0
            if worker is not None:
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker
            tasks = list(self._background_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._audio.aclose()

    def _validate_start(self, message: dict[str, Any]) -> dict[str, str]:
        start = message.get("start")
        if not isinstance(start, dict):
            raise VoiceProtocolError("Missing stream start payload.")
        media = start.get("media_format", {})
        if media.get("encoding") != "audio/alaw" or int(media.get("sample_rate", 0)) != 8000:
            raise VoiceProtocolError("Unsupported VoiceLink audio format.")
        stream_sid = str(start.get("stream_sid") or message.get("stream_sid") or "")
        call_sid = str(start.get("call_sid") or "")
        caller = _normalize_e164_phone(
            start.get("from")
            or start.get("caller")
            or start.get("caller_number")
            or start.get("callerNumber")
            or message.get("from")
        )
        called = _normalize_e164_phone(
            start.get("to")
            or start.get("called")
            or start.get("called_number")
            or start.get("calledNumber")
            or message.get("to")
        )
        if not stream_sid or not call_sid or not caller or not called:
            raise VoiceProtocolError("Incomplete VoiceLink call metadata.")
        if _phone_digits(called) != _phone_digits(self._settings.voicelink_phone_number):
            raise VoiceProtocolError("Unexpected VoiceLink destination number.")
        assert self._settings.voice_organization_id is not None
        assert self._settings.voice_actor_id is not None
        logger.info(
            "voicelink_call_started",
            call_sid=call_sid,
            caller_suffix=caller[-4:],
            called_suffix=called[-4:],
            start_fields=sorted(str(key) for key in start),
            tts_model=self._settings.openai_tts_model,
            tts_voice=self._settings.openai_tts_voice,
            tts_speed=self._settings.openai_tts_speed,
        )
        return {
            "stream_sid": stream_sid,
            "call_sid": call_sid,
            "caller": caller,
            "called": called,
            "organization_id": str(self._settings.voice_organization_id),
            "actor_id": str(self._settings.voice_actor_id),
        }

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
        turns: asyncio.Queue[CapturedTurn | bytes | None],
        context: dict[str, str],
    ) -> None:
        organization_id = UUID(context["organization_id"])
        actor_id = UUID(context["actor_id"])
        thread_id = uuid5(NAMESPACE_URL, f"voicelink:{context['call_sid']}")
        session_factory = get_session_factory(self._settings.database_url or "")
        agent = ReceptionAgent(self._settings)

        async def lookup_caller() -> dict[str, object]:
            async with session_factory() as session:
                with presentation.tool_scope("lookup_caller_family", "backend"):
                    return await ToolExecutor(
                        session,
                        organization_id,
                        actor_id=actor_id,
                        settings=self._settings,
                        caller_phone_e164=context["caller"],
                    ).execute("lookup_caller_family", {"phone_e164": context["caller"]})

        caller_lookup = self._start_background(lookup_caller())
        recent_bot_utterances: deque[str] = deque(maxlen=4)
        greeting = (
            "Namaste. Geeta Medicine mein aapka swagat hai. "
            "Main aapki appointment mein kaise madad kar sakti hoon?"
        )
        recent_bot_utterances.append(greeting)
        presentation.dialogue("assistant", greeting)
        presentation.emit("greeting", "voice", "Greeting prepared while mobile lookup runs")
        try:
            await self._play_greeting(websocket, greeting)
            self._start_background(self._get_filler_audio(self.DEFAULT_FILLER))
        except Exception as error:
            logger.warning(
                "voicelink_greeting_failed",
                call_sid=context["call_sid"],
                error_type=type(error).__name__,
                error_message=str(error),
            )
        try:
            caller_context = await asyncio.wait_for(caller_lookup, timeout=5.0)
        except Exception as error:
            logger.warning("voicelink_caller_lookup_failed", error_type=type(error).__name__)
            caller_context = {"ok": False, "error": "Caller lookup unavailable; do not assume a saved profile."}
        caller_first_name = ""
        if isinstance(caller_context, dict) and caller_context.get("caller_name"):
            caller_first_name = str(caller_context["caller_name"]).strip().split()[0]
            personalized_filler = f"Ji {caller_first_name} ji, main check karti hoon."
            self._start_background(self._get_filler_audio(personalized_filler))
        turn_number = 0
        previous_transcript = ""
        previous_transcript_at = 0.0
        consecutive_silences = 0
        consecutive_errors = 0
        call_started_at = time.monotonic()
        max_call_duration = 600.0  # 10 minutes maximum
        silence_timeout = self.SILENCE_TIMEOUT_SECONDS

        while True:
            elapsed = time.monotonic() - call_started_at
            if elapsed >= max_call_duration:
                logger.info("voicelink_max_duration_reached", call_sid=context["call_sid"])
                closing = "Call ka samay poora ho gaya hai. Aap kisi bhi samay dobara call kar sakte hain. Dhanyavaad."
                recent_bot_utterances.append(closing)
                try:
                    closing_audio = await self._audio.synthesize_alaw(closing)
                    await self._play(websocket, closing_audio)
                except Exception:
                    pass
                return

            wait_timeout = min(silence_timeout, max(1.0, max_call_duration - elapsed))
            try:
                queued_turn = await asyncio.wait_for(turns.get(), timeout=wait_timeout)
            except TimeoutError:
                if self._caller_speaking:
                    continue
                consecutive_silences += 1
                if consecutive_silences == 1:
                    reprompt = "Ji, kya aap meri baat sun pa rahe hain? Aap chahein toh main pichhli baat dobara bata sakti hoon."
                    logger.info("voicelink_silence_reprompt", call_sid=context["call_sid"])
                    recent_bot_utterances.append(reprompt)
                    try:
                        reprompt_audio = await self._audio.synthesize_alaw(reprompt)
                        await self._play(websocket, reprompt_audio)
                    except Exception:
                        pass
                    continue
                else:
                    logger.info("voicelink_silence_timeout_end", call_sid=context["call_sid"])
                    farewell = "Lagta hai aawaz nahi aa rahi hai. Kripya thodi der baad dobara call karein. Dhanyavaad."
                    recent_bot_utterances.append(farewell)
                    try:
                        farewell_audio = await self._audio.synthesize_alaw(farewell)
                        await self._play(websocket, farewell_audio)
                    except Exception:
                        pass
                    return

            if queued_turn is None:
                return

            if isinstance(queued_turn, CapturedTurn):
                utterance = queued_turn.audio
                caller_turn_id = queued_turn.caller_turn_id
                queued_age = time.monotonic() - queued_turn.captured_at
            else:
                # Compatibility with internal tests and the legacy gateway caller.
                utterance = queued_turn
                caller_turn_id = None
                queued_age = 0.0

            if queued_age > self._settings.voice_max_queued_turn_age_seconds:
                self._emit_event(
                    VoiceEventType.ERROR,
                    context["call_sid"],
                    caller_turn_id=caller_turn_id,
                    error_code="TURN_EXPIRED",
                    queued_ms=round(queued_age * 1000),
                )
                stale_reply = (
                    "Maaf kijiye, pichhli baat process hone mein zyada samay laga. "
                    "Kripya apni baat dobara bataiye."
                )
                recent_bot_utterances.append(stale_reply)
                try:
                    await self._play(websocket, await self._audio.synthesize_alaw(stale_reply))
                except Exception:
                    pass
                continue

            with presentation.correlation_scope(caller_turn_id=caller_turn_id):
                try:
                    started_at = time.perf_counter()
                    self._emit_event(
                        VoiceEventType.CALLER_TURN_DEQUEUED,
                        context["call_sid"],
                        caller_turn_id=caller_turn_id,
                        audio_ms=round(len(utterance) / 8),
                        queue_depth=turns.qsize(),
                        queued_ms=round(queued_age * 1000),
                    )
                    logger.info(
                        "voicelink_turn_dequeued",
                        call_sid=context["call_sid"],
                        queue_depth=turns.qsize(),
                        audio_ms=round(len(utterance) / 8),
                    )
                    presentation.emit("transcription_started", "transcription", "Captured audio sent for transcription",
                                      caller_turn_id=caller_turn_id)
                    transcribe_with_usage = getattr(self._audio, "transcribe_alaw_with_usage", None)
                    if callable(transcribe_with_usage):
                        transcription = await transcribe_with_usage(utterance)
                        transcript = transcription.text
                        if transcription.usage:
                            from app.observability.usage import openai_usage_record
                            from app.voice.presentation import record_usage
                            usage_record = openai_usage_record(
                                operation="transcription",
                                model=self._settings.openai_transcription_model,
                                request_id=transcription.request_id,
                                identity_source=transcription.identity_source,
                                usage=transcription.usage,
                            )
                            if usage_record:
                                record_usage(usage_record)
                    else:
                        transcript = await self._audio.transcribe_alaw(utterance)
                    transcribed_at = time.perf_counter()
                    presentation.emit(
                        "transcription_completed", "transcription", "Speech recognition completed",
                        duration_ms=round((transcribed_at - started_at) * 1000),
                        transcript_chars=len(transcript or ""), caller_turn_id=caller_turn_id,
                    )
                    if not transcript:
                        continue
                    if _is_self_echo(transcript, list(recent_bot_utterances)):
                        logger.info(
                            "voicelink_self_echo_suppressed",
                            call_sid=context["call_sid"],
                            transcript_length=len(transcript),
                        )
                        continue
                    normalized_transcript = re.sub(r"\W+", " ", transcript.casefold()).strip()
                    if (
                        normalized_transcript
                        and normalized_transcript == previous_transcript
                        and transcribed_at - previous_transcript_at < 2.5
                    ):
                        logger.info(
                            "voicelink_duplicate_turn_suppressed",
                            call_sid=context["call_sid"],
                        )
                        continue
                    consecutive_silences = 0
                    previous_transcript = normalized_transcript
                    turn_number += 1
                    presentation.dialogue("caller", transcript, source_id=(f"chained-turn-{caller_turn_id}" if caller_turn_id is not None else None))
                    presentation.emit("agent_started", "agent", "Agent processing caller turn",
                                      caller_turn_id=caller_turn_id)
                    previous_transcript_at = transcribed_at
                    logger.info(
                        "voicelink_turn_stage",
                        call_sid=context["call_sid"],
                        turn=turn_number,
                        stage="transcribed",
                        transcript_length=len(transcript),
                        elapsed_ms=round((transcribed_at - started_at) * 1000),
                    )

                    if turn_number == 1:
                        prompt_message = (
                            f"[Voice call started. Verified incoming caller ID: {context['caller']}. "
                            f"Caller/family lookup: {json.dumps(caller_context, default=str)}. "
                            "The phone number and lookup are already known; do not ask for the mobile number.]\n"
                            f"Caller said: {transcript}"
                        )
                    else:
                        prompt_message = f"Caller said: {transcript}"

                    lookup_started = asyncio.Event()

                    async def run_agent(msg: str, lookup_event: asyncio.Event) -> dict[str, Any]:
                        async with session_factory() as session:
                            from app.observability.telemetry import span_scope
                            with span_scope("voice.agent.turn", {"voice.engine": "chained"}):
                                return await agent.respond(
                                    msg,
                                    session,
                                    organization_id,
                                    actor_id,
                                    thread_id,
                                    caller_phone=context["caller"],
                                    on_lookup_start=lookup_event.set,
                                    booking_source="AI_VOICE",
                                    booking_consent_channel="AI_VOICE",
                                    allow_appointment_mutations=False,
                                )

                    agent_task = self._start_background(run_agent(prompt_message, lookup_started))
                    filler_played = False
                    if await self._should_play_filler(agent_task, lookup_started):
                        filler_text = (
                            f"Ji {caller_first_name} ji, main check karti hoon."
                            if caller_first_name
                            else self.DEFAULT_FILLER
                        )
                        filler_audio = self.__class__._filler_cache.get(self._speech_cache_key(filler_text))
                        if filler_audio and not agent_task.done():
                            filler_played = True
                            recent_bot_utterances.append(filler_text)
                            logger.info(
                                "voicelink_comfort_filler_played",
                                call_sid=context["call_sid"],
                                filler=filler_text,
                            )
                            await self._play(websocket, filler_audio)

                    result = await agent_task
                    for usage_record in result.get("usage_records", []):
                        if isinstance(usage_record, dict):
                            from app.voice.presentation import record_usage
                            record_usage(usage_record)
                    responded_at = time.perf_counter()
                    presentation.emit(
                        "agent_completed", "agent", "Agent completed caller turn",
                        caller_turn_id=caller_turn_id,
                        duration_ms=round((responded_at - transcribed_at) * 1000),
                        filler_played=filler_played,
                    )
                    reply_text = str(result["reply"])
                    presentation.dialogue("assistant", reply_text, source_id=(f"chained-turn-{caller_turn_id}" if caller_turn_id is not None else None))
                    logger.info(
                        "voicelink_turn_stage",
                        call_sid=context["call_sid"],
                        turn=turn_number,
                        stage="agent_responded",
                        reply_length=len(reply_text),
                        elapsed_ms=round((responded_at - started_at) * 1000),
                        filler_played=filler_played,
                    )
                    reply = re.sub(r"[*_#`]", "", reply_text).strip()
                    if filler_played:
                        name_pat = (
                            rf"({re.escape(caller_first_name)}\s+ji)?"
                            if caller_first_name
                            else ""
                        )
                        pattern = rf"^(ji\b|haan\b|haanji\b|bilkul\b)\s*{name_pat}[,\s]*"
                        cleaned = re.sub(pattern, "", reply, flags=re.IGNORECASE).strip()
                        if cleaned:
                            reply = cleaned[0].upper() + cleaned[1:]

                    recent_bot_utterances.append(reply)
                    first_audio_at = await self._play_stream(
                        websocket, self._stream_text_alaw(reply)
                    )
                    synthesized_at = time.perf_counter()
                    presentation.emit(
                        "playback_completed", "playback", "Response audio playback completed",
                        caller_turn_id=turn_number,
                        first_audio_latency_ms=(round((first_audio_at - started_at) * 1000)
                                                if first_audio_at is not None else None),
                        tts_first_audio_ms=(round((first_audio_at - responded_at) * 1000)
                                            if first_audio_at is not None else None),
                        playback_duration_ms=(round((synthesized_at - first_audio_at) * 1000)
                                              if first_audio_at is not None else None),
                    )
                    consecutive_errors = 0
                    logger.info(
                        "voicelink_turn_latency",
                        call_sid=context["call_sid"],
                        stt_ms=round((transcribed_at - started_at) * 1000),
                        agent_ms=round((responded_at - transcribed_at) * 1000),
                        tts_first_audio_ms=(
                            round((first_audio_at - responded_at) * 1000)
                            if first_audio_at is not None
                            else None
                        ),
                        tts_and_playback_ms=round((synthesized_at - responded_at) * 1000),
                        filler_played=filler_played,
                    )
                except Exception as error:
                    consecutive_errors += 1
                    logger.warning(
                        "voicelink_turn_failed",
                        call_sid=context["call_sid"],
                        error_type=type(error).__name__,
                        error_message=str(error),
                        consecutive_errors=consecutive_errors,
                    )
                    if consecutive_errors < 2:
                        error_msg = "Maaf kijiye, mujhe samajhne mein thodi dikkat hui. Kya aap ek baar dobara bata sakte hain?"
                        recent_bot_utterances.append(error_msg)
                        try:
                            error_audio = await self._audio.synthesize_alaw(error_msg)
                            await self._play(websocket, error_audio)
                        except Exception:
                            pass
                    else:
                        fallback_msg = (
                            "Kshama karein, hamare system mein kuch takneeki samasya aa rahi hai. "
                            "Kripya clinic desk par sampark karein ya thodi der baad dobara call karein. Dhanyavaad."
                        )
                        recent_bot_utterances.append(fallback_msg)
                        try:
                            fallback_audio = await self._audio.synthesize_alaw(fallback_msg)
                            await self._play(websocket, fallback_audio)
                        except Exception:
                            pass
                        return

    async def _should_play_filler(
        self, agent_task: asyncio.Task[Any], lookup_started: asyncio.Event,
    ) -> bool:
        done, _ = await asyncio.wait({agent_task}, timeout=self.FILLER_DELAY_SECONDS)
        if done:
            return False
        lookup_wait = asyncio.create_task(lookup_started.wait())
        try:
            await asyncio.wait({agent_task, lookup_wait}, return_when=asyncio.FIRST_COMPLETED)
            return not agent_task.done() and lookup_started.is_set()
        finally:
            lookup_wait.cancel()
            with suppress(asyncio.CancelledError):
                await lookup_wait

    def _speech_cache_key(self, text: str) -> tuple[str, ...]:
        return (
            str(self._settings.voice_organization_id),
            self._settings.openai_tts_model,
            self._settings.openai_tts_voice,
            str(self._settings.openai_tts_speed),
            SPEECH_INSTRUCTIONS,
            text,
        )

    async def _get_filler_audio(self, text: str) -> bytes | None:
        key = self._speech_cache_key(text)
        cached = self.__class__._filler_cache.get(key)
        if cached is not None:
            return cached
        async with self.__class__._filler_lock:
            if key in self.__class__._filler_cache:
                return self.__class__._filler_cache[key]
            try:
                audio = await self._audio.synthesize_alaw(text)
                if len(self.__class__._filler_cache) >= self._speech_cache_limit:
                    del self.__class__._filler_cache[next(iter(self.__class__._filler_cache))]
                self.__class__._filler_cache[key] = audio
                return audio
            except Exception as error:
                logger.warning(
                    "voicelink_filler_synthesis_failed",
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                return None

    async def _stream_text_alaw(self, text: str) -> AsyncIterator[bytes]:
        """Keep one prosodic context for the whole reply while streaming its audio."""
        if not text.strip():
            return
        async for chunk in self._audio.stream_synthesize_alaw(text.strip()):
            yield chunk

    async def _play_greeting(self, websocket: WebSocket, text: str) -> None:
        """Send the first speech chunk without waiting for full TTS or the filler lock."""
        key = self._speech_cache_key(text)
        cached = self.__class__._filler_cache.get(key)
        if cached:
            await self._play(websocket, cached)
            return

        async def stream_and_cache() -> AsyncIterator[bytes]:
            audio = bytearray()
            async for chunk in self._stream_text_alaw(text):
                audio.extend(chunk)
                yield chunk
            # Interrupted or failed streams must never become a cached greeting.
            if audio:
                if len(self.__class__._filler_cache) >= self._speech_cache_limit:
                    del self.__class__._filler_cache[next(iter(self.__class__._filler_cache))]
                self.__class__._filler_cache[key] = bytes(audio)

        await self._play_stream(websocket, stream_and_cache())

    async def _play(self, websocket: WebSocket, audio: bytes) -> None:
        if not audio:
            return
        self._playback_done.clear()
        self._active_mark = f"reply-{id(audio)}"
        self._playback_until = time.monotonic() + len(audio) / 8000 + 0.35
        for offset in range(0, len(audio), 160):
            if not self._active_mark:
                break
            await self._send(
                websocket,
                {
                    "event": "media",
                    "media": {
                        "payload": base64.b64encode(audio[offset : offset + 160]).decode()
                    },
                },
            )
        if self._active_mark:
            await self._send(websocket, {"event": "mark", "mark": {"name": self._active_mark}})
            await self._wait_for_playback()

    async def _play_stream(
        self, websocket: WebSocket, stream: AsyncIterator[bytes]
    ) -> float | None:
        first_audio_at: float | None = None
        self._playback_done.clear()
        self._active_mark = f"reply-{time.monotonic_ns()}"
        self._playback_until = time.monotonic()
        async for audio in stream:
            if not self._active_mark:
                break
            if first_audio_at is None:
                first_audio_at = time.perf_counter()
            self._playback_until = max(self._playback_until, time.monotonic()) + len(audio) / 8000
            for offset in range(0, len(audio), 160):
                if not self._active_mark:
                    break
                await self._send(
                    websocket,
                    {
                        "event": "media",
                        "media": {
                            "payload": base64.b64encode(audio[offset : offset + 160]).decode()
                        },
                    },
                )
        if self._active_mark:
            self._playback_until = max(self._playback_until, time.monotonic()) + 0.35
            await self._send(websocket, {"event": "mark", "mark": {"name": self._active_mark}})
            await self._wait_for_playback()
        return first_audio_at

    async def _wait_for_playback(self) -> None:
        """Start caller silence/following speech only after playback, or interruption."""
        remaining = max(0.0, self._playback_until - time.monotonic())
        if self._active_mark and remaining:
            try:
                await asyncio.wait_for(self._playback_done.wait(), timeout=remaining)
            except TimeoutError:
                pass  # Providers without mark acknowledgement use the audio-duration fallback.
        self._active_mark = ""
        self._playback_until = 0.0

    def _start_background(self, coroutine: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    @staticmethod
    def _emit_event(
        event_type: VoiceEventType,
        call_id: str,
        *,
        caller_turn_id: int | None = None,
        generation_id: int | None = None,
        playback_segment_id: str | None = None,
        operation_id: str | None = None,
        **fields: str | int | float | bool | None,
    ) -> None:
        event = VoiceEvent(
            call_id=call_id,
            event_type=event_type,
            caller_turn_id=caller_turn_id,
            generation_id=generation_id,
            playback_segment_id=playback_segment_id,
            operation_id=operation_id,
            fields=fields,
        )
        logger.info("voice_call_event", **event.as_log_fields())
        presentation.voice_event(
            event_type.value, caller_turn_id=caller_turn_id, generation_id=generation_id,
            playback_segment_id=playback_segment_id, operation_id=operation_id, **fields,
        )

    async def _send(self, websocket: WebSocket, payload: dict[str, object]) -> None:
        if self._stream_sid:
            payload = {**payload, "stream_sid": self._stream_sid}
        async with self._send_lock:
            await websocket.send_json(payload)
        if payload.get("event") == "media":
            if not self._first_audio_sent and self._stream_started_at is not None:
                self._first_audio_sent = True
                logger.info(
                    "voicelink_first_audio_sent",
                    stream_sid=self._stream_sid,
                    elapsed_ms=round((time.monotonic() - self._stream_started_at) * 1000),
                )
            presentation.audio_transfer("output", 1)
