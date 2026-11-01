import pytest

from app.voice.readback import PlaybackStatus, ReadbackPlaybackLedger
from app.voice.session import CallStateError


def test_only_matching_sent_segment_can_be_acknowledged() -> None:
    ledger = ReadbackPlaybackLedger()
    segment = ledger.prepare(proposal_id="proposal-1", text="Please confirm Tuesday at 5 PM.")

    with pytest.raises(CallStateError, match="stale or invalid"):
        ledger.acknowledge(segment.id)

    sent = ledger.sent(segment.id)
    acknowledged = ledger.acknowledge(segment.id)

    assert sent.status == PlaybackStatus.SENT
    assert acknowledged.status == PlaybackStatus.ACKNOWLEDGED
    assert ledger.is_acknowledged(segment.id, proposal_id="proposal-1")
    assert not ledger.is_acknowledged(segment.id, proposal_id="proposal-2")


def test_interrupt_invalidates_a_pending_readback_and_stale_mark() -> None:
    ledger = ReadbackPlaybackLedger()
    segment = ledger.prepare(proposal_id="proposal-1", text="Please confirm Tuesday at 5 PM.")
    ledger.sent(segment.id)

    interrupted = ledger.interrupt_active()

    assert interrupted is not None
    assert interrupted.status == PlaybackStatus.INTERRUPTED
    with pytest.raises(CallStateError, match="stale or invalid"):
        ledger.acknowledge(segment.id)
    assert not ledger.is_acknowledged(segment.id, proposal_id="proposal-1")


def test_next_readback_interrupts_the_previous_segment() -> None:
    ledger = ReadbackPlaybackLedger()
    first = ledger.prepare(proposal_id="proposal-1", text="First details.")
    ledger.sent(first.id)
    second = ledger.prepare(proposal_id="proposal-2", text="Corrected details.")

    assert not ledger.is_acknowledged(first.id, proposal_id="proposal-1")
    assert ledger.sent(second.id).status == PlaybackStatus.SENT
