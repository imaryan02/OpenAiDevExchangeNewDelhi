"""Per-call server controller for a guarded booking confirmation."""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.agent.operation_service import TrackedCall, VoiceOperationService
from app.voice.proposals import booking_proposal
from app.voice.readback import ReadbackPlaybackLedger
from app.voice.session import CallStateError, OperationProposal

ConfirmBooking = Callable[[str], Awaitable[dict[str, object]]]
PlayReadback = Callable[[str, str], Awaitable[str]]


@dataclass
class PendingBooking:
    proposal: OperationProposal
    offer_token: str
    readback_completed: bool = False


class VoiceBookingController:
    """Keeps signed offers server-only and authorizes at most one matching commit."""

    def __init__(
        self,
        service: VoiceOperationService,
        tracked: TrackedCall,
        ledger: ReadbackPlaybackLedger,
        play_readback: PlayReadback,
        confirm_booking: ConfirmBooking,
    ) -> None:
        self._service = service
        self._tracked = tracked
        self._ledger = ledger
        self._play_readback = play_readback
        self._confirm_booking = confirm_booking
        self._pending: PendingBooking | None = None

    async def present_offer(self, tool_result: dict[str, object]) -> OperationProposal:
        proposal_data = booking_proposal(tool_result)
        offer_token = str(tool_result["offer_token"])
        proposal = await self._service.prepare(
            self._tracked,
            operation="BOOK",
            proposal_version=proposal_data.version,
            idempotency_key=f"voice-book-{secrets.token_urlsafe(18)}",
        )
        self._pending = PendingBooking(proposal=proposal, offer_token=offer_token)
        segment_id = await self._play_readback(proposal.id, proposal_data.readback_text)
        # The player owns the ledger; this check ensures a mismatched callback cannot
        # attach another proposal's audio to this operation.
        if not self._ledger.is_acknowledged(segment_id, proposal_id=proposal.id):
            return proposal
        await self._complete_readback(proposal, segment_id)
        self._require_pending().readback_completed = True
        return proposal

    async def acknowledge_readback(self, segment_id: str) -> OperationProposal:
        pending = self._require_pending()
        self._ledger.acknowledge(segment_id)
        completed = await self._complete_readback(pending.proposal, segment_id)
        pending.readback_completed = True
        return completed

    async def approve(self, *, explicit: bool, caller_turn_id: int) -> dict[str, object]:
        pending = self._require_pending()
        if not explicit:
            raise CallStateError("A clear explicit approval is required.")
        if not pending.readback_completed:
            raise CallStateError("The readback has not been acknowledged yet.")
        approved = await self._service.approve(
            self._tracked, proposal_id=pending.proposal.id, caller_turn_id=caller_turn_id
        )
        # Once dispatch starts, an uncertain result must be reconciled, never retried
        # by replaying this in-memory pending offer.
        self._pending = None
        result = await self._confirm_booking(pending.offer_token)
        if result.get("ok") is True:
            await self._service.committed(proposal=approved, result=result)
        else:
            await self._service.failed(proposal=approved, result=result)
        self._pending = None
        return result

    async def capture_correction(self) -> int:
        """Persist the later caller turn before discarding its obsolete offer."""
        turn_id = await self._service.capture_turn(self._tracked)
        self._ledger.interrupt_active()
        self._pending = None
        return turn_id

    async def _complete_readback(
        self, proposal: OperationProposal, segment_id: str
    ) -> OperationProposal:
        if not self._ledger.is_acknowledged(segment_id, proposal_id=proposal.id):
            raise CallStateError("The readback has not been acknowledged yet.")
        return await self._service.complete_acknowledged_readback(
            self._tracked,
            proposal_id=proposal.id,
            playback_segment_id=segment_id,
            ledger=self._ledger,
        )

    def _require_pending(self) -> PendingBooking:
        if self._pending is None:
            raise CallStateError("There is no active booking proposal.")
        return self._pending
