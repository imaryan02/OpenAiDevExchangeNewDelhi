from datetime import UTC, datetime, timedelta

import pytest

from app.voice.session import CallSession, CallStateError


@pytest.mark.parametrize("offset", [-1, 0])
def test_delayed_transcript_cannot_turn_early_speech_into_consent(offset: int) -> None:
    session = CallSession(call_id="early", caller_phone="+919800000001")
    started = datetime(2026, 9, 12, tzinfo=UTC)
    session.capture_turn(captured_at=started)
    proposal = session.create_proposal(operation="BOOK", version="v1")
    completed = started + timedelta(seconds=5)
    session.complete_readback(proposal_id=proposal.id, playback_segment_id="segment", completed_at=completed)
    early = session.capture_turn(captured_at=completed + timedelta(seconds=offset), preserve_active_proposal=True)
    with pytest.raises(CallStateError, match="speech must start"):
        session.approve_proposal(proposal_id=proposal.id, caller_turn_id=early.id)


def test_only_a_turn_after_completed_readback_can_approve() -> None:
    session = CallSession(call_id="call-1", caller_phone="+919800000001")
    first = session.capture_turn(captured_at=datetime(2026, 9, 12, tzinfo=UTC))
    proposal = session.create_proposal(operation="BOOK", version="offer-v1")
    session.complete_readback(
        proposal_id=proposal.id,
        playback_segment_id="segment-1",
        completed_at=first.captured_at + timedelta(seconds=2),
    )
    approval = session.capture_turn(
        captured_at=first.captured_at + timedelta(seconds=3), preserve_active_proposal=True
    )

    approved = session.approve_proposal(proposal_id=proposal.id, caller_turn_id=approval.id)

    assert approved.version == "offer-v1"
    assert session.active_proposal is None


def test_correction_invalidates_an_offer_before_it_can_be_confirmed() -> None:
    session = CallSession(call_id="call-2", caller_phone="+919800000002")
    session.capture_turn()
    proposal = session.create_proposal(operation="BOOK", version="offer-v1")
    session.complete_readback(proposal_id=proposal.id, playback_segment_id="segment-1")
    correction = session.capture_turn()

    with pytest.raises(CallStateError, match="no longer active"):
        session.approve_proposal(proposal_id=proposal.id, caller_turn_id=correction.id)


def test_readback_and_approval_require_the_correct_order() -> None:
    session = CallSession(call_id="call-3", caller_phone="+919800000003")
    turn = session.capture_turn()
    proposal = session.create_proposal(operation="CANCEL", version="cancel-v1")

    with pytest.raises(CallStateError, match="readback"):
        session.approve_proposal(proposal_id=proposal.id, caller_turn_id=turn.id)


def test_session_state_round_trip_preserves_presented_proposal() -> None:
    session = CallSession(call_id="call-4", caller_phone="+919800000004")
    turn = session.capture_turn(captured_at=datetime(2026, 9, 12, tzinfo=UTC))
    proposal = session.create_proposal(operation="RESCHEDULE", version="reschedule-v1")
    session.complete_readback(
        proposal_id=proposal.id,
        playback_segment_id="segment-4",
        completed_at=turn.captured_at + timedelta(seconds=2),
    )

    loaded = CallSession.from_state(session.as_state())

    assert loaded.state_version == session.state_version
    assert loaded.latest_turn == session.latest_turn
    assert loaded.active_proposal == session.active_proposal

    with pytest.raises(CallStateError, match="after the proposal"):
        session.complete_readback(proposal_id=proposal.id, playback_segment_id="segment-1")
        session.approve_proposal(proposal_id=proposal.id, caller_turn_id=turn.id)
