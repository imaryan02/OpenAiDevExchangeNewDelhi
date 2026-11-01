"""Controlled readback playback evidence for consequential voice operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from app.voice.session import CallStateError


class PlaybackStatus(StrEnum):
    PREPARED = "PREPARED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class ReadbackSegment:
    id: str
    proposal_id: str
    text: str
    status: PlaybackStatus


class ReadbackPlaybackLedger:
    """Owns carrier mark evidence; generated or sent speech is never consent evidence."""

    def __init__(self) -> None:
        self._segments: dict[str, ReadbackSegment] = {}
        self._active_id: str | None = None

    def prepare(self, *, proposal_id: str, text: str) -> ReadbackSegment:
        if not proposal_id.strip() or not text.strip():
            raise CallStateError("A proposal and non-empty readback are required.")
        self.interrupt_active()
        segment = ReadbackSegment(
            id=f"readback-{uuid4()}", proposal_id=proposal_id, text=text.strip(), status=PlaybackStatus.PREPARED
        )
        self._segments[segment.id] = segment
        self._active_id = segment.id
        return segment

    def sent(self, segment_id: str) -> ReadbackSegment:
        segment = self._require_active(segment_id, PlaybackStatus.PREPARED)
        return self._replace(segment, PlaybackStatus.SENT)

    def require_prepared(self, segment_id: str) -> None:
        self._require_active(segment_id, PlaybackStatus.PREPARED)

    def interrupt(self, segment_id: str) -> None:
        if self._active_id == segment_id:
            self.interrupt_active()

    def acknowledge(self, segment_id: str) -> ReadbackSegment:
        segment = self._require_active(segment_id, PlaybackStatus.SENT)
        self._active_id = None
        return self._replace(segment, PlaybackStatus.ACKNOWLEDGED)

    def interrupt_active(self) -> ReadbackSegment | None:
        if self._active_id is None:
            return None
        segment = self._segments[self._active_id]
        self._active_id = None
        if segment.status in {PlaybackStatus.PREPARED, PlaybackStatus.SENT}:
            return self._replace(segment, PlaybackStatus.INTERRUPTED)
        return segment

    def is_acknowledged(self, segment_id: str, *, proposal_id: str) -> bool:
        segment = self._segments.get(segment_id)
        return bool(
            segment
            and segment.proposal_id == proposal_id
            and segment.status == PlaybackStatus.ACKNOWLEDGED
        )

    def _require_active(self, segment_id: str, expected: PlaybackStatus) -> ReadbackSegment:
        segment = self._segments.get(segment_id)
        if segment is None or self._active_id != segment_id or segment.status != expected:
            raise CallStateError("Playback evidence is stale or invalid.")
        return segment

    def _replace(self, segment: ReadbackSegment, status: PlaybackStatus) -> ReadbackSegment:
        next_segment = ReadbackSegment(
            id=segment.id, proposal_id=segment.proposal_id, text=segment.text, status=status
        )
        self._segments[next_segment.id] = next_segment
        return next_segment
