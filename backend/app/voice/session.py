"""Deterministic per-call consent state, independent of the language model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


class CallStateError(ValueError):
    """A call event cannot safely advance the appointment operation."""


@dataclass(frozen=True)
class CallerTurn:
    id: int
    captured_at: datetime


@dataclass(frozen=True)
class OperationProposal:
    id: str
    version: str
    operation: str
    created_after_turn_id: int
    readback_playback_segment_id: str | None = None
    readback_completed_at: datetime | None = None

    @property
    def is_presented(self) -> bool:
        return self.readback_playback_segment_id is not None and self.readback_completed_at is not None


@dataclass
class CallSession:
    """In-memory domain object; Phase 2 persistence stores this state by call ID."""

    call_id: str
    caller_phone: str
    state_version: int = 0
    latest_turn: CallerTurn | None = None
    active_proposal: OperationProposal | None = None

    def capture_turn(
        self,
        *,
        captured_at: datetime | None = None,
        preserve_active_proposal: bool = False,
    ) -> CallerTurn:
        timestamp = captured_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise CallStateError("Caller turn timestamps must include a timezone.")
        next_id = (self.latest_turn.id if self.latest_turn is not None else 0) + 1
        turn = CallerTurn(id=next_id, captured_at=timestamp)
        self.latest_turn = turn
        # A parsed, explicit confirmation may preserve a completed readback for
        # approval. All other later caller turns are corrections by default.
        if self.active_proposal is not None and not preserve_active_proposal:
            self.active_proposal = None
        self.state_version += 1
        return turn

    def create_proposal(self, *, operation: str, version: str) -> OperationProposal:
        if self.latest_turn is None:
            raise CallStateError("A proposal requires a captured caller turn.")
        if operation not in {"BOOK", "CANCEL", "RESCHEDULE"}:
            raise CallStateError("Unsupported consequential operation.")
        if not version.strip():
            raise CallStateError("A proposal version is required.")
        proposal = OperationProposal(
            id=str(uuid4()),
            version=version,
            operation=operation,
            created_after_turn_id=self.latest_turn.id,
        )
        self.active_proposal = proposal
        self.state_version += 1
        return proposal

    def complete_readback(
        self,
        *,
        proposal_id: str,
        playback_segment_id: str,
        completed_at: datetime | None = None,
    ) -> OperationProposal:
        proposal = self._require_proposal(proposal_id)
        if not playback_segment_id.strip():
            raise CallStateError("A verified playback segment is required.")
        timestamp = completed_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise CallStateError("Readback timestamps must include a timezone.")
        presented = OperationProposal(
            id=proposal.id,
            version=proposal.version,
            operation=proposal.operation,
            created_after_turn_id=proposal.created_after_turn_id,
            readback_playback_segment_id=playback_segment_id,
            readback_completed_at=timestamp,
        )
        self.active_proposal = presented
        self.state_version += 1
        return presented

    def approve_proposal(self, *, proposal_id: str, caller_turn_id: int) -> OperationProposal:
        proposal = self._require_proposal(proposal_id)
        if not proposal.is_presented:
            raise CallStateError("The proposal readback was not verified as complete.")
        if self.latest_turn is None or self.latest_turn.id != caller_turn_id:
            raise CallStateError("Approval must come from the latest caller turn.")
        if caller_turn_id <= proposal.created_after_turn_id:
            raise CallStateError("Approval must be captured after the proposal readback.")
        if proposal.readback_completed_at is None or self.latest_turn.captured_at <= proposal.readback_completed_at:
            raise CallStateError("Approval speech must start after readback completion.")
        approved = proposal
        self.active_proposal = None
        self.state_version += 1
        return approved

    def _require_proposal(self, proposal_id: str) -> OperationProposal:
        if self.active_proposal is None or self.active_proposal.id != proposal_id:
            raise CallStateError("The operation proposal is no longer active.")
        return self.active_proposal

    def as_state(self) -> dict[str, Any]:
        proposal = self.active_proposal
        return {
            "call_id": self.call_id,
            "caller_phone": self.caller_phone,
            "state_version": self.state_version,
            "latest_turn": (
                {"id": self.latest_turn.id, "captured_at": self.latest_turn.captured_at.isoformat()}
                if self.latest_turn is not None
                else None
            ),
            "active_proposal": (
                {
                    "id": proposal.id,
                    "version": proposal.version,
                    "operation": proposal.operation,
                    "created_after_turn_id": proposal.created_after_turn_id,
                    "readback_playback_segment_id": proposal.readback_playback_segment_id,
                    "readback_completed_at": (
                        proposal.readback_completed_at.isoformat()
                        if proposal.readback_completed_at is not None
                        else None
                    ),
                }
                if proposal is not None
                else None
            ),
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> CallSession:
        try:
            call = cls(
                call_id=str(state["call_id"]),
                caller_phone=str(state["caller_phone"]),
                state_version=int(state["state_version"]),
            )
            turn_value = state.get("latest_turn")
            if isinstance(turn_value, dict):
                turn_at = datetime.fromisoformat(str(turn_value["captured_at"]))
                if turn_at.tzinfo is None:
                    raise CallStateError("Persisted caller turn timestamp has no timezone.")
                call.latest_turn = CallerTurn(id=int(turn_value["id"]), captured_at=turn_at)
            proposal_value = state.get("active_proposal")
            if isinstance(proposal_value, dict):
                completed_value = proposal_value.get("readback_completed_at")
                completed_at = (
                    datetime.fromisoformat(str(completed_value))
                    if completed_value is not None
                    else None
                )
                if completed_at is not None and completed_at.tzinfo is None:
                    raise CallStateError("Persisted readback timestamp has no timezone.")
                call.active_proposal = OperationProposal(
                    id=str(proposal_value["id"]),
                    version=str(proposal_value["version"]),
                    operation=str(proposal_value["operation"]),
                    created_after_turn_id=int(proposal_value["created_after_turn_id"]),
                    readback_playback_segment_id=(
                        str(proposal_value["readback_playback_segment_id"])
                        if proposal_value.get("readback_playback_segment_id") is not None
                        else None
                    ),
                    readback_completed_at=completed_at,
                )
            return call
        except (KeyError, TypeError, ValueError) as error:
            raise CallStateError("Persisted call state is invalid.") from error
