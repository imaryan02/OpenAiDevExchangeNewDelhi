"""Play server-owned consequential readbacks as isolated VoiceLink segments."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from typing import Protocol

from app.voice.readback import ReadbackPlaybackLedger, ReadbackSegment
from app.voice.session import CallStateError


class AlawSynthesizer(Protocol):
    async def synthesize_alaw(self, text: str) -> bytes: ...


SendPayload = Callable[[dict[str, object]], Awaitable[None]]


class ControlledReadbackPlayer:
    """Separate TTS playback whose mark is the only completion signal accepted by the ledger."""

    def __init__(self, ledger: ReadbackPlaybackLedger, synthesizer: AlawSynthesizer) -> None:
        self._ledger = ledger
        self._synthesizer = synthesizer

    @property
    def ledger(self) -> ReadbackPlaybackLedger:
        """Server-owned playback evidence; never expose it to the conversation model."""
        return self._ledger

    async def play(
        self, *, proposal_id: str, text: str, send: SendPayload,
        on_prepared: Callable[[str], None] | None = None,
    ) -> ReadbackSegment:
        segment = self._ledger.prepare(proposal_id=proposal_id, text=text)
        try:
            if on_prepared is not None:
                on_prepared(segment.id)
            audio = await self._synthesizer.synthesize_alaw(segment.text)
            if not audio:
                raise CallStateError("Readback speech generation returned no audio.")
            for offset in range(0, len(audio), 160):
                self._ledger.require_prepared(segment.id)
                await send(
                    {
                        "event": "media",
                        "media": {"payload": base64.b64encode(audio[offset : offset + 160]).decode()},
                    }
                )
                await asyncio.sleep(len(audio[offset : offset + 160]) / 8000)
            sent = self._ledger.sent(segment.id)
            await send({"event": "mark", "mark": {"name": sent.id}})
            return sent
        except BaseException:
            self._ledger.interrupt(segment.id)
            raise

    def acknowledge(self, mark_name: str) -> ReadbackSegment:
        return self._ledger.acknowledge(mark_name)

    def interrupt(self) -> ReadbackSegment | None:
        return self._ledger.interrupt_active()
