from datetime import timedelta
from uuid import uuid4

import pytest

from app.agent.operation_service import TrackedCall, VoiceOperationService
from app.voice.booking_controller import VoiceBookingController
from app.voice.readback import ReadbackPlaybackLedger
from app.voice.session import CallSession, CallStateError


class Store:
    async def save(self, **kwargs) -> None:
        return None

    async def record_operation(self, **kwargs) -> None:
        return None

    async def transition_operation(self, **kwargs) -> None:
        return None


@pytest.mark.asyncio
async def test_booking_controller_requires_ack_then_later_explicit_approval() -> None:
    ledger = ReadbackPlaybackLedger()
    service = VoiceOperationService(Store())  # type: ignore[arg-type]
    tracked = TrackedCall(uuid4(), uuid4(), 0, CallSession("call-1", "+919800000001"))
    await service.capture_turn(tracked)
    confirmed: list[str] = []

    async def play(proposal_id: str, text: str) -> str:
        segment = ledger.prepare(proposal_id=proposal_id, text=text)
        ledger.sent(segment.id)
        return segment.id

    async def confirm(token: str) -> dict[str, object]:
        confirmed.append(token)
        return {"ok": True, "booking_reference": "GM-1"}

    controller = VoiceBookingController(service, tracked, ledger, play, confirm)
    proposal = await controller.present_offer({
        "ok": True, "offer_token": "private", "offer": {
            "patient_name": "Aryan", "doctor_name": "Dr Amit", "location_name": "Main",
            "session_date": "Tuesday", "session_time": "5 PM IST", "fee_minor": 50000,
            "currency": "INR", "payment_method": "CASH", "language": "en-IN",
        },
    })
    with pytest.raises(CallStateError, match="not been acknowledged"):
        await controller.approve(explicit=True, caller_turn_id=1)
    segment_id = next(iter(ledger._segments))  # noqa: SLF001
    presented = await controller.acknowledge_readback(segment_id)
    assert presented.readback_completed_at is not None
    approval_turn = await service.capture_turn(
        tracked, preserve_active_proposal=True,
        captured_at=presented.readback_completed_at + timedelta(seconds=1),
    )
    result = await controller.approve(explicit=True, caller_turn_id=approval_turn)
    with pytest.raises(CallStateError, match="no active booking proposal"):
        await controller.approve(explicit=True, caller_turn_id=approval_turn)

    assert proposal.id
    assert result["booking_reference"] == "GM-1"
    assert confirmed == ["private"]


@pytest.mark.asyncio
async def test_correction_invalidates_readback_before_approval() -> None:
    ledger = ReadbackPlaybackLedger()
    service = VoiceOperationService(Store())  # type: ignore[arg-type]
    tracked = TrackedCall(uuid4(), uuid4(), 0, CallSession("call-2", "+919800000002"))
    await service.capture_turn(tracked)

    async def play(proposal_id: str, text: str) -> str:
        segment = ledger.prepare(proposal_id=proposal_id, text=text)
        ledger.sent(segment.id)
        return segment.id

    async def confirm(token: str) -> dict[str, object]:
        return {"ok": True}

    controller = VoiceBookingController(service, tracked, ledger, play, confirm)
    await controller.present_offer({
        "ok": True, "offer_token": "private", "offer": {
            "patient_name": "Aryan", "doctor_name": "Dr Amit", "location_name": "Main",
            "session_date": "Tuesday", "session_time": "5 PM IST", "fee_minor": 50000,
            "currency": "INR", "payment_method": "CASH", "language": "en-IN",
        },
    })
    await controller.capture_correction()

    with pytest.raises(CallStateError, match="no active booking proposal"):
        await controller.approve(explicit=True, caller_turn_id=2)
