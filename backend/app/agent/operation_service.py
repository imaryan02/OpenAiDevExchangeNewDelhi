"""Durable authorization lifecycle for consequential voice operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.voice.readback import ReadbackPlaybackLedger
from app.voice.session import CallSession, OperationProposal
from app.voice.session_store import CallSessionStore


@dataclass
class TrackedCall:
    session_id: UUID
    owner_token: UUID
    persisted_version: int
    call: CallSession


class VoiceOperationService:
    """Coordinates durable state with an appointment mutation authorization boundary."""

    def __init__(self, store: CallSessionStore) -> None:
        self._store = store

    async def capture_turn(
        self,
        tracked: TrackedCall,
        *,
        preserve_active_proposal: bool = False,
        captured_at: datetime | None = None,
    ) -> int:
        turn = tracked.call.capture_turn(
            preserve_active_proposal=preserve_active_proposal, captured_at=captured_at
        )
        await self._save(tracked)
        return turn.id

    async def prepare(
        self,
        tracked: TrackedCall,
        *,
        operation: str,
        proposal_version: str,
        idempotency_key: str,
    ) -> OperationProposal:
        proposal = tracked.call.create_proposal(operation=operation, version=proposal_version)
        await self._save(tracked)
        await self._store.record_operation(
            session_id=tracked.session_id,
            operation_id=UUID(proposal.id),
            operation_type=operation,
            proposal_version=proposal_version,
            idempotency_key=idempotency_key,
        )
        return proposal

    async def complete_readback(
        self,
        tracked: TrackedCall,
        *,
        proposal_id: str,
        playback_segment_id: str,
        completed_at: datetime | None = None,
    ) -> OperationProposal:
        proposal = tracked.call.complete_readback(
            proposal_id=proposal_id,
            playback_segment_id=playback_segment_id,
            completed_at=completed_at,
        )
        await self._save(tracked)
        await self._store.transition_operation(
            operation_id=UUID(proposal.id),
            expected_statuses=("PROPOSED",),
            next_status="READBACK_COMPLETED",
        )
        return proposal

    async def complete_acknowledged_readback(
        self,
        tracked: TrackedCall,
        *,
        proposal_id: str,
        playback_segment_id: str,
        ledger: ReadbackPlaybackLedger,
        completed_at: datetime | None = None,
    ) -> OperationProposal:
        """Advance consent state only when the active carrier mark proves completion."""
        if not ledger.is_acknowledged(playback_segment_id, proposal_id=proposal_id):
            raise ValueError("The readback segment was not acknowledged by the carrier.")
        return await self.complete_readback(
            tracked,
            proposal_id=proposal_id,
            playback_segment_id=playback_segment_id,
            completed_at=completed_at,
        )

    async def approve(self, tracked: TrackedCall, *, proposal_id: str, caller_turn_id: int) -> OperationProposal:
        proposal = tracked.call.approve_proposal(
            proposal_id=proposal_id, caller_turn_id=caller_turn_id
        )
        await self._save(tracked)
        await self._store.transition_operation(
            operation_id=UUID(proposal.id),
            expected_statuses=("READBACK_COMPLETED",),
            next_status="APPROVED",
        )
        return proposal

    async def committed(
        self, *, proposal: OperationProposal, result: dict[str, Any]
    ) -> None:
        await self._store.transition_operation(
            operation_id=UUID(proposal.id),
            expected_statuses=("APPROVED",),
            next_status="COMMITTED",
            result_payload=result,
        )

    async def failed(self, *, proposal: OperationProposal, result: dict[str, Any]) -> None:
        await self._store.transition_operation(
            operation_id=UUID(proposal.id),
            expected_statuses=("APPROVED",),
            next_status="FAILED",
            result_payload=result,
        )

    async def _save(self, tracked: TrackedCall) -> None:
        await self._store.save(
            session_id=tracked.session_id,
            owner_token=tracked.owner_token,
            call=tracked.call,
            expected_version=tracked.persisted_version,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        tracked.persisted_version = tracked.call.state_version
