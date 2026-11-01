from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.core.errors import ApiError
from app.voice.codec import (
    alaw8k_to_wav,
    mulaw8k_to_wav,
    pcm24k_to_alaw8k,
    pcm24k_to_mulaw8k,
)

SPEECH_INSTRUCTIONS = (
    "Speak as an Indian clinic receptionist in an ordinary, matter-of-fact conversational voice. "
    "Use a normal conversational rhythm and brief natural pauses at punctuation. "
    "Keep pitch and volume steady, with restrained intonation across Hindi and English. "
    "Do not act out emotions, use a sing-song voice, whisper, or exaggerate questions. "
    "Pronounce names, dates and numbers clearly. Speak only the supplied text."
)


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    usage: dict[str, Any] | None
    request_id: str
    identity_source: str


class OpenAIAudioClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=30)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def transcribe_mulaw(self, payload: bytes) -> str:
        return await self._transcribe_wav(mulaw8k_to_wav(payload))

    async def transcribe_alaw(self, payload: bytes) -> str:
        return await self._transcribe_wav(alaw8k_to_wav(payload))

    async def transcribe_alaw_with_usage(self, payload: bytes) -> TranscriptionResult:
        return await self._transcribe_wav_with_usage(alaw8k_to_wav(payload))

    async def _transcribe_wav(self, wav_payload: bytes) -> str:
        return (await self._transcribe_wav_with_usage(wav_payload)).text

    async def _transcribe_wav_with_usage(self, wav_payload: bytes) -> TranscriptionResult:
        api_key = self._settings.openai_api_key
        if not api_key:
            raise ApiError("AI_NOT_CONFIGURED", "OpenAI audio is not configured.", 503)
        response = await self._client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data={
                "model": self._settings.openai_transcription_model,
                "prompt": (
                    "Geeta Medicine clinic Indian healthcare reception conversation in Hindi, Hinglish, English: "
                    "Dr. Sweta Gupta, Dr. Amit Kumar, appointment booking, slot, session, fees, token, "
                    "haan, haanji, ji, bilkul, theek hai, kar do, kar dijiye, confirm kar do, please, sir, madam, gynaecologist, fever."
                ),
            },
            files={"file": ("telephone.wav", wav_payload, "audio/wav")},
        )
        if response.status_code >= 400:
            raise ApiError("TRANSCRIPTION_FAILED", "Speech recognition could not complete.", 502)
        decoded = response.json()
        payload = decoded if isinstance(decoded, dict) else {}
        usage = payload.get("usage")
        request_id = response.headers.get("x-request-id")
        return TranscriptionResult(
            text=str(payload.get("text", "")).strip(),
            usage=usage if isinstance(usage, dict) else None,
            request_id=request_id or str(uuid4()),
            identity_source="provider" if request_id else "local",
        )

    async def synthesize_mulaw(self, text: str) -> bytes:
        return pcm24k_to_mulaw8k(await self._synthesize_pcm(text))

    async def synthesize_alaw(self, text: str) -> bytes:
        return pcm24k_to_alaw8k(await self._synthesize_pcm(text))

    async def stream_synthesize_alaw(self, text: str) -> AsyncIterator[bytes]:
        """Yield telephone-ready audio as OpenAI produces PCM chunks."""
        api_key = self._settings.openai_api_key
        if not api_key:
            raise ApiError("AI_NOT_CONFIGURED", "OpenAI audio is not configured.", 503)
        pending = b""
        async with self._client.stream(
            "POST",
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {api_key}"},
            json=self._speech_request(text),
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                raise ApiError("SPEECH_FAILED", "Speech generation could not complete.", 502)
            async for chunk in response.aiter_bytes(chunk_size=960):
                pending += chunk
                usable = len(pending) - (len(pending) % 6)
                if usable:
                    yield pcm24k_to_alaw8k(pending[:usable])
                    pending = pending[usable:]

    async def _synthesize_pcm(self, text: str) -> bytes:
        api_key = self._settings.openai_api_key
        if not api_key:
            raise ApiError("AI_NOT_CONFIGURED", "OpenAI audio is not configured.", 503)
        response = await self._client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {api_key}"},
            json=self._speech_request(text),
        )
        if response.status_code >= 400:
            raise ApiError("SPEECH_FAILED", "Speech generation could not complete.", 502)
        return response.content

    def _speech_request(self, text: str) -> dict[str, str | float]:
        # Never silently cut a booking readback/reference mid-sentence.
        if len(text) > 4096:
            raise ApiError("SPEECH_TEXT_TOO_LONG", "Speech text exceeds the provider limit.", 502)
        request: dict[str, str | float] = {
            "model": self._settings.openai_tts_model,
            "voice": self._settings.openai_tts_voice,
            "input": text,
            "speed": self._settings.openai_tts_speed,
            "response_format": "pcm",
        }
        if self._settings.openai_tts_model not in {"tts-1", "tts-1-hd"}:
            request["instructions"] = SPEECH_INSTRUCTIONS
        return request
