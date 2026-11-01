"""Twilio mu-law transport for the same Friday Realtime runtime."""

import struct
from typing import Any

from fastapi import WebSocket

from app.personal_agent.voice.voicelink import PersonalVoiceLinkGateway
from app.voice.codec import Pcm24kToAlaw8k, mulaw_to_pcm16_sample, pcm24k_to_mulaw8k


class Pcm24kToMulaw8k(Pcm24kToAlaw8k):
    def feed(self, payload: bytes) -> bytes:
        self._pending.extend(payload)
        usable = len(self._pending) - len(self._pending) % 6
        converted = pcm24k_to_mulaw8k(bytes(self._pending[:usable]))
        del self._pending[:usable]
        return converted


class PersonalTwilioGateway(PersonalVoiceLinkGateway):
    def _new_converter(self) -> Pcm24kToAlaw8k:
        return Pcm24kToMulaw8k()

    def _decode_audio(self, encoded: bytes) -> bytes:
        return b"".join(struct.pack("<h", mulaw_to_pcm16_sample(v)) * 3 for v in encoded)

    async def _send(
        self, websocket: WebSocket, payload: dict[str, Any], *, epoch: int | None = None
    ) -> None:
        async with self.send_lock:
            if epoch is not None and epoch != self.epoch:
                return
            await websocket.send_json({**payload, "streamSid": self.context["stream_sid"]})
