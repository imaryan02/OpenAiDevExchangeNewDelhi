from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.agent.operation_service import TrackedCall, VoiceOperationService
from app.voice.readback import ReadbackPlaybackLedger
from app.voice.session import CallSession


class Store:
    def __init__(self) -> None:
        self.saved: list[int] = []
        self.operations: list[tuple[str, str]] = []

    async def save(self, **kwargs) -> None:
        self.saved.append(kwargs["call"].state_version)

    async def record_operation(self, **kwargs) -> None:
        self.operations.append(("record", kwargs["operation_type"]))

    async def transition_operation(self, **kwargs) -> None:
        self.operations.append((kwargs["next_status"], str(kwargs["operation_id"])))


@pytest.mark.asyncio
async def test_operation_service_requires_readback_before_approval_and_records_lifecycle() -> None:
    store = Store()
    service = VoiceOperationService(store)  # type: ignore[arg-type]
    tracked = TrackedCall(
        session_id=uuid4(),
        owner_token=uuid4(),
        persisted_version=0,
        call=CallSession(call_id="call-1", caller_phone="+919800000001"),
    )
    started = datetime(2026, 9, 12, tzinfo=UTC)
    await service.capture_turn(tracked, captured_at=started)
    proposal = await service.prepare(
        tracked,
        operation="BOOK",
        proposal_version="offer-v1",
        idempotency_key="voice-operation-key-0001",
    )
    await service.complete_readback(
        tracked,
        proposal_id=proposal.id,
        playback_segment_id="segment-1",
        completed_at=started + timedelta(seconds=2),
    )
    approval_turn = await service.capture_turn(
        tracked,
        preserve_active_proposal=True,
        captured_at=started + timedelta(seconds=3),
    )
    approved = await service.approve(
        tracked, proposal_id=proposal.id, caller_turn_id=approval_turn
    )
    await service.committed(proposal=approved, result={"ok": True, "status": "CONFIRMED"})

    assert store.saved == [1, 2, 3, 4, 5]
    assert store.operations[0] == ("record", "BOOK")
    assert [event[0] for event in store.operations[1:]] == [
        "READBACK_COMPLETED",
        "APPROVED",
        "COMMITTED",
    ]


@pytest.mark.asyncio
async def test_operation_service_requires_carrier_ack_for_controlled_readback() -> None:
    store = Store()
    service = VoiceOperationService(store)  # type: ignore[arg-type]
    tracked = TrackedCall(
        session_id=uuid4(), owner_token=uuid4(), persisted_version=0,
        call=CallSession(call_id="call-ack", caller_phone="+919800000001"),
    )
    await service.capture_turn(tracked)
    proposal = await service.prepare(
        tracked, operation="BOOK", proposal_version="offer-v1", idempotency_key="key-ack-0001"
    )
    ledger = ReadbackPlaybackLedger()
    segment = ledger.prepare(proposal_id=proposal.id, text="Please confirm your appointment.")
    ledger.sent(segment.id)

    with pytest.raises(ValueError, match="not acknowledged"):
        await service.complete_acknowledged_readback(
            tracked, proposal_id=proposal.id, playback_segment_id=segment.id, ledger=ledger
        )

    ledger.acknowledge(segment.id)
    completed = await service.complete_acknowledged_readback(
        tracked, proposal_id=proposal.id, playback_segment_id=segment.id, ledger=ledger
    )
    assert completed.is_presented
