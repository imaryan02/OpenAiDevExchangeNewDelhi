"""Minimal server-side OpenAI Realtime session used by the Phase 1 preflight."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from app.core.config import Settings
from app.core.errors import ApiError

REALTIME_ENDPOINT = "wss://api.openai.com/v1/realtime"


@dataclass(frozen=True)
class RealtimePreflightResult:
    model: str
    session_id: str | None
    voice: str
    input_format: str
    output_format: str


class OpenAIRealtimeSession:
    """Small protocol client; it intentionally contains no appointment tools or writes."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: ClientConnection | None = None

    async def __aenter__(self) -> OpenAIRealtimeSession:
        await self.connect()
        return self

    async def __aexit__(self, _type: object, _value: object, _traceback: object) -> None:
        await self.aclose()

    async def connect(self) -> None:
        if not self._settings.realtime_configured:
            raise ApiError("REALTIME_NOT_CONFIGURED", "OpenAI Realtime is not configured.", 503)
        assert self._settings.openai_api_key is not None
        query = urlencode({"model": self._settings.openai_realtime_model})
        try:
            self._connection = await connect(
                f"{REALTIME_ENDPOINT}?{query}",
                additional_headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
                open_timeout=self._settings.openai_realtime_connect_timeout_seconds,
                close_timeout=5,
            )
        except Exception as error:
            raise ApiError("REALTIME_CONNECTION_FAILED", "Could not open an OpenAI Realtime session.", 502) from error

    async def aclose(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def send(self, event: dict[str, object]) -> None:
        if self._connection is None:
            raise RuntimeError("Realtime session is not connected.")
        await self._connection.send(json.dumps(event, separators=(",", ":")))

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        if self._connection is None:
            raise RuntimeError("Realtime session is not connected.")
        try:
            async for raw_event in self._connection:
                if not isinstance(raw_event, str):
                    continue
                decoded = json.loads(raw_event)
                if isinstance(decoded, dict):
                    yield decoded
        except ConnectionClosed as error:
            raise ApiError("REALTIME_CONNECTION_CLOSED", "OpenAI Realtime closed the session.", 502) from error

    async def next_event(self, *, timeout_seconds: float | None = None) -> dict[str, Any]:
        timeout = timeout_seconds or self._settings.openai_realtime_connect_timeout_seconds
        iterator = self.events().__aiter__()
        try:
            return await asyncio.wait_for(anext(iterator), timeout=timeout)
        except TimeoutError as error:
            raise ApiError("REALTIME_EVENT_TIMEOUT", "OpenAI Realtime did not respond in time.", 502) from error

    async def receive_event(self) -> dict[str, Any]:
        """Receive one event; a gateway must have exactly one consuming task."""
        if self._connection is None:
            raise RuntimeError("Realtime session is not connected.")
        try:
            raw_event = await self._connection.recv()
        except ConnectionClosed as error:
            raise ApiError("REALTIME_CONNECTION_CLOSED", "OpenAI Realtime closed the session.", 502) from error
        if not isinstance(raw_event, str):
            return {}
        decoded = json.loads(raw_event)
        return decoded if isinstance(decoded, dict) else {}

    async def configure_audio_only_session(self) -> None:
        await self.configure_voice_session(
            "This is a connection test. Do not call tools or claim actions."
        )

    async def configure_voice_session(
        self, instructions: str, *, tools: list[dict[str, object]] | None = None
    ) -> None:
        session: dict[str, object] = {
            "type": "realtime",
            "model": self._settings.openai_realtime_model,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "transcription": {
                        "model": self._settings.openai_transcription_model,
                    },
                    "turn_detection": {"type": "semantic_vad", "create_response": False},
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "voice": self._settings.openai_realtime_voice,
                },
            },
            "instructions": instructions,
        }
        if tools:
            # Realtime function tools use the same JSON Schema shape but do not
            # accept the Responses API's top-level `strict` parameter.
            session["tools"] = [
                {key: value for key, value in tool.items() if key != "strict"}
                for tool in tools
            ]
            session["tool_choice"] = "auto"
        await self.send(
            {
                "type": "session.update",
                "session": session,
            }
        )


async def preflight(settings: Settings) -> RealtimePreflightResult:
    """Verify connection and a safe audio-only configuration without sending caller audio."""
    async with OpenAIRealtimeSession(settings) as session:
        created = await session.next_event()
        if created.get("type") != "session.created":
            raise ApiError("REALTIME_PROTOCOL_ERROR", "OpenAI Realtime did not create a session.", 502)
        await session.configure_audio_only_session()
        updated = await session.next_event()
        if updated.get("type") != "session.updated":
            raise ApiError("REALTIME_PROTOCOL_ERROR", "OpenAI Realtime did not accept session settings.", 502)
        session_payload = updated.get("session")
        session_id = str(session_payload.get("id")) if isinstance(session_payload, dict) and session_payload.get("id") else None
        return RealtimePreflightResult(
            model=settings.openai_realtime_model,
            session_id=session_id,
            voice=settings.openai_realtime_voice,
            input_format="audio/pcm@24000",
            output_format="audio/pcm@24000",
        )
