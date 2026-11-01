import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.agent.operation_service import TrackedCall
from app.core.config import Settings
from app.voice import call_runtime
from app.voice.call_runtime import VoiceCallRuntime
from app.voice.session import CallSession, CallStateError


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "ledger", "commit", "tool"])
async def test_booking_and_operation_share_commit_and_failures_never_report_success(monkeypatch, failure):
    events = []

    class Result:
        rowcount = 1

    class Database:
        async def execute(self, statement, params):
            if params.get("next_status") == "COMMITTED":
                events.append("ledger")
                if failure == "ledger":
                    raise RuntimeError("ledger failure")
            return Result()
        async def commit(self):
            events.append("commit")
            if failure == "commit":
                raise RuntimeError("commit uncertain")
        async def rollback(self):
            events.append("rollback")

    db = Database()
    org, actor = uuid4(), uuid4()
    settings = Settings.model_construct(voice_organization_id=org, voice_actor_id=actor)
    runtime = VoiceCallRuntime(db, org)
    call = CallSession("call", "+919800000001")
    at = datetime(2026, 9, 13, tzinfo=UTC)
    call.capture_turn(captured_at=at)
    proposal = call.create_proposal(operation="BOOK", version=hashlib.sha256(b"token").hexdigest())
    call.complete_readback(proposal_id=proposal.id, playback_segment_id="mark", completed_at=at + timedelta(seconds=2))
    turn = call.capture_turn(captured_at=at + timedelta(seconds=3), preserve_active_proposal=True)
    runtime.tracked = TrackedCall(uuid4(), uuid4(), call.state_version, call)

    class Executor:
        def __init__(self, session, organization_id, **kwargs):
            assert session is db
            assert organization_id == org
            assert kwargs["commit_mutations"] is False
            self.authorize = kwargs["operation_authorizer"]
        async def execute(self, name, args):
            assert await self.authorize(name, args) is None
            events.append("appointment")
            return {"ok": failure != "tool", "booking_reference": "GM-1"}

    monkeypatch.setattr(call_runtime, "ToolExecutor", Executor)
    arguments = dict(proposal_id=proposal.id, caller_turn_id=turn.id, offer_token="token", settings=settings)
    if failure in {"ledger", "commit"}:
        with pytest.raises(RuntimeError):
            await runtime.confirm_booking(**arguments)
        assert events[-1] == "rollback"
        if failure == "commit":
            with pytest.raises(CallStateError, match="reconciliation"):
                await runtime.confirm_booking(**arguments)
            with pytest.raises(CallStateError, match="fresh"):
                await runtime.reconcile_booking(db)

            class Evidence:
                def mappings(self):
                    return self
                def one_or_none(self):
                    return {"result": {"ok": True, "booking_reference": "GM-1"}}

            class FreshDatabase:
                async def execute(self, statement, params):
                    assert params["organization_id"] == org
                    assert params["session_id"] == runtime.tracked.session_id
                    assert params["owner_token"] == runtime.tracked.owner_token
                    assert params["caller_phone"] == call.caller_phone
                    assert str(params["operation_id"]) == proposal.id
                    assert params["proposal_version"] == proposal.version
                    return Evidence()

            recovered = await runtime.reconcile_booking(FreshDatabase())
            assert recovered == {"ok": True, "booking_reference": "GM-1"}
            assert events.count("appointment") == 1
            with pytest.raises(CallStateError, match="reconciliation"):
                await runtime.confirm_booking(**arguments)
    else:
        result = await runtime.confirm_booking(**arguments)
        if failure == "tool":
            assert result["ok"] is False
            assert events == ["appointment", "rollback"]
        else:
            assert events == ["appointment", "ledger", "commit"]
            with pytest.raises(CallStateError):
                await runtime.confirm_booking(**arguments)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "tool_name", "arguments"),
    [
        ("CANCEL", "cancel_appointment", {"booking_reference": "GM-1", "reason": "Unavailable"}),
        ("RESCHEDULE", "reschedule_appointment", {
            "booking_reference": "GM-1", "new_session_id": "11111111-1111-1111-1111-111111111111",
            "new_slot_id": None,
        }),
    ],
)
async def test_cancel_and_reschedule_use_the_same_atomic_approval_boundary(
    monkeypatch, operation, tool_name, arguments
):
    events = []

    class Result:
        rowcount = 1

    class Database:
        async def execute(self, statement, params):
            if params.get("next_status") == "COMMITTED":
                events.append("ledger")
            return Result()
        async def commit(self):
            events.append("commit")
        async def rollback(self):
            events.append("rollback")

    db = Database()
    org, actor = uuid4(), uuid4()
    runtime = VoiceCallRuntime(db, org)
    settings = Settings.model_construct(voice_organization_id=org, voice_actor_id=actor)
    call = CallSession("call", "+919800000001")
    at = datetime(2026, 9, 13, tzinfo=UTC)
    call.capture_turn(captured_at=at)
    proposal = call.create_proposal(operation=operation, version=runtime._arguments_version(arguments))
    call.complete_readback(proposal_id=proposal.id, playback_segment_id="mark", completed_at=at + timedelta(seconds=1))
    turn = call.capture_turn(captured_at=at + timedelta(seconds=2), preserve_active_proposal=True)
    runtime.tracked = TrackedCall(uuid4(), uuid4(), call.state_version, call)

    class Executor:
        def __init__(self, session, organization_id, **kwargs):
            assert session is db
            assert organization_id == org
            assert kwargs["commit_mutations"] is False
            self.authorize = kwargs["operation_authorizer"]
        async def execute(self, received_name, received_arguments):
            assert received_name == tool_name
            assert received_arguments == arguments
            assert await self.authorize(received_name, received_arguments) is None
            assert await self.authorize("cancel_appointment", {"booking_reference": "other"})
            events.append("mutation")
            return {"ok": True, "status": operation}

    monkeypatch.setattr(call_runtime, "ToolExecutor", Executor)
    result = await runtime.confirm_operation(
        operation=operation, tool_name=tool_name, proposal_id=proposal.id, caller_turn_id=turn.id,
        arguments=arguments, settings=settings,
    )
    assert result == {"ok": True, "status": operation}
    assert events == ["mutation", "ledger", "commit"]
    with pytest.raises(CallStateError):
        await runtime.confirm_operation(
            operation=operation, tool_name=tool_name, proposal_id=proposal.id, caller_turn_id=turn.id,
            arguments=arguments, settings=settings,
        )
