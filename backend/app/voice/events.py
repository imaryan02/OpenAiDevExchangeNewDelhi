"""Correlated, PII-minimised events for telephone voice sessions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class VoiceEventType(StrEnum):
    CALL_STARTED = "call_started"
    CALL_ENDED = "call_ended"
    CALLER_TURN_CAPTURED = "caller_turn_captured"
    CALLER_TURN_DEQUEUED = "caller_turn_dequeued"
    TRANSCRIPTION_COMPLETED = "transcription_completed"
    GENERATION_STARTED = "generation_started"
    GENERATION_COMPLETED = "generation_completed"
    PLAYBACK_STARTED = "playback_started"
    PLAYBACK_ACKNOWLEDGED = "playback_acknowledged"
    PLAYBACK_INTERRUPTED = "playback_interrupted"
    ERROR = "error"


@dataclass(frozen=True)
class VoiceEvent:
    """A single call event that is safe to emit without transcript/audio payloads."""

    call_id: str
    event_type: VoiceEventType
    event_id: str = field(default_factory=lambda: str(uuid4()))
    monotonic_ms: int = field(default_factory=lambda: round(time.monotonic() * 1000))
    caller_turn_id: int | None = None
    generation_id: int | None = None
    playback_segment_id: str | None = None
    operation_id: str | None = None
    fields: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    def as_log_fields(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "voice_event_id": self.event_id,
            "voice_event_type": self.event_type.value,
            "monotonic_ms": self.monotonic_ms,
            "caller_turn_id": self.caller_turn_id,
            "generation_id": self.generation_id,
            "playback_segment_id": self.playback_segment_id,
            "operation_id": self.operation_id,
            **self.fields,
        }
