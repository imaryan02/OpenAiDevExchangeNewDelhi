from uuid import uuid4

import pytest

from app.voice.call_runtime import VoiceCallRuntime
from app.voice.session import CallStateError


class Result:
    rowcount = 1
    def mappings(self):
        return self

    def one(self):
        return {"id": str(uuid4()), "owner_token": str(uuid4())}

    def one_or_none(self):
        return None


class Database:
    def __init__(self) -> None:
        self.commits = 0
        self.fail_commit = False
        self.rollbacks = 0

    async def execute(self, statement, params):
        return Result()

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_runtime_creates_one_durable_owner_fence_per_call() -> None:
    database = Database()
    runtime = VoiceCallRuntime(database, uuid4())  # type: ignore[arg-type]

    first = await runtime.start(provider_call_id="call-1", caller_phone="+919800000001")
    second = await runtime.start(provider_call_id="call-1", caller_phone="+919800000001")

    assert first is second
    assert database.commits == 1

    with pytest.raises(CallStateError, match="different"):
        await runtime.start(provider_call_id="other", caller_phone="+919800000001")
    with pytest.raises(CallStateError, match="different"):
        await runtime.start(provider_call_id="call-1", caller_phone="+919800000002")


@pytest.mark.asyncio
async def test_uncertain_start_is_not_retried() -> None:
    database = Database()
    database.fail_commit = True
    runtime = VoiceCallRuntime(database, uuid4())
    with pytest.raises(RuntimeError):
        await runtime.start(provider_call_id="call", caller_phone="+919800000001")
    assert database.rollbacks == 1
    assert runtime.tracked is None
    with pytest.raises(CallStateError, match="reconciliation"):
        await runtime.start(provider_call_id="call", caller_phone="+919800000001")


@pytest.mark.asyncio
async def test_preparation_and_carrier_ack_are_committed_and_reject_early_approval() -> None:
    from datetime import UTC, datetime, timedelta

    from app.voice.readback import ReadbackPlaybackLedger

    database = Database()
    runtime = VoiceCallRuntime(database, uuid4())
    tracked = await runtime.start(provider_call_id="call", caller_phone="+919800000001")
    onset = datetime(2026, 9, 13, tzinfo=UTC)
    await runtime.capture_turn(captured_at=onset)
    proposal, wording = await runtime.prepare_booking({
        "ok": True, "offer_token": "private-token",
        "offer": {"patient_name": "Aryan", "doctor_name": "Dr Test", "location_name": "Clinic",
                  "session_date": "2026-09-14", "session_time": "10:00 AM", "fee_minor": 10000,
                  "currency": "INR", "payment_method": "CASH", "language": "en-IN"},
    })
    assert database.commits == 3
    assert "private-token" not in wording
    ledger = ReadbackPlaybackLedger()
    segment = ledger.prepare(proposal_id=proposal.id, text=wording)
    ledger.sent(segment.id)
    arguments = dict(proposal_id=proposal.id, segment_id=segment.id, ledger=ledger,
                     completed_at=onset + timedelta(seconds=2))
    with pytest.raises(ValueError, match="acknowledged"):
        await runtime.acknowledge_readback(**arguments)
    assert database.commits == 3
    ledger.acknowledge(segment.id)
    await runtime.acknowledge_readback(**arguments)
    assert database.commits == 4
    assert tracked.call.active_proposal.readback_completed_at == arguments["completed_at"]
    # A transcript can arrive after the mark even though its speech began before it.
    turn_id = await runtime.capture_turn(captured_at=onset + timedelta(seconds=1), preserve_active_proposal=True)
    with pytest.raises(CallStateError):
        await runtime.transition(lambda call: runtime.operations.approve(
            call, proposal_id=proposal.id, caller_turn_id=turn_id,
        ))
    assert database.commits == 5
    await runtime.capture_turn(captured_at=onset + timedelta(seconds=3))
    assert tracked.call.active_proposal is None


@pytest.mark.asyncio
async def test_turn_capture_commits_and_restores_state_on_failure() -> None:
    database = Database()
    runtime = VoiceCallRuntime(database, uuid4())  # type: ignore[arg-type]
    tracked = await runtime.start(provider_call_id="call", caller_phone="+919800000001")
    assert await runtime.capture_turn() == 1
    assert database.commits == 2
    database.fail_commit = True
    with pytest.raises(RuntimeError, match="commit failed"):
        await runtime.capture_turn()
    assert database.rollbacks == 1
    assert tracked.persisted_version == tracked.call.state_version == 1
    assert tracked.call.latest_turn.id == 1
