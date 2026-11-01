import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.voice.session import CallSession, CallStateError
from app.voice.session_store import CallSessionStore


class Result:
    def __init__(self, *, rowcount: int = 1, row: dict[str, object] | None = None) -> None:
        self.rowcount = rowcount
        self._row = row or {}

    def mappings(self) -> "Result":
        return self

    def one(self) -> dict[str, object]:
        return self._row

    def one_or_none(self) -> dict[str, object] | None:
        return self._row or None


class Database:
    def __init__(self, *, update_count: int = 1) -> None:
        self.update_count = update_count
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if "returning id, owner_token" in sql:
            return Result(row={"id": str(uuid4()), "owner_token": str(uuid4())})
        return Result(rowcount=self.update_count)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, {"ok": True}, {"ok": False}, "invalid"])
async def test_reconciliation_requires_positive_scoped_commit_evidence(payload) -> None:
    class EvidenceDatabase:
        async def execute(self, statement, params):
            sql = str(statement)
            for fence in ("o.organization_id=:organization_id", "s.id=:session_id",
                          "s.owner_token=:owner_token", "s.caller_phone_e164=:caller_phone",
                          "o.operation_id=:operation_id", "o.proposal_version=:proposal_version",
                          "o.operation_type='BOOK'", "o.status='COMMITTED'",
                          "o.committed_at is not null"):
                assert fence in sql
            return Result(row=None if payload is None else {"result": payload})

    store = CallSessionStore(EvidenceDatabase(), uuid4())
    args = dict(session_id=uuid4(), owner_token=uuid4(), caller_phone="+919800000001",
                operation_id=uuid4(), proposal_version="version")
    if payload is None:
        assert await store.committed_booking_result(**args) is None
    elif payload == {"ok": True}:
        assert await store.committed_booking_result(**args) == payload
    else:
        with pytest.raises((CallStateError, ValueError)):
            await store.committed_booking_result(**args)


@pytest.mark.asyncio
async def test_store_uses_owner_and_version_compare_and_swap() -> None:
    db = Database()
    store = CallSessionStore(db, uuid4())  # type: ignore[arg-type]
    call = CallSession(call_id="provider-call", caller_phone="+919800000001")
    call.capture_turn(captured_at=datetime(2026, 9, 12, tzinfo=UTC))

    await store.save(
        session_id=uuid4(),
        owner_token=uuid4(),
        call=call,
        expected_version=0,
    )

    _, params = db.calls[0]
    assert params["expected_version"] == 0
    assert params["next_version"] == 1
    assert "owner_token" in params
    assert "expires_at > now()" in db.calls[0][0]


@pytest.mark.asyncio
async def test_store_rejects_stale_owner_or_version() -> None:
    db = Database(update_count=0)
    store = CallSessionStore(db, uuid4())  # type: ignore[arg-type]
    call = CallSession(call_id="provider-call", caller_phone="+919800000001")
    call.capture_turn()

    with pytest.raises(CallStateError, match="stale"):
        await store.save(
            session_id=uuid4(),
            owner_token=uuid4(),
            call=call,
            expected_version=0,
        )


@pytest.mark.asyncio
async def test_committed_operation_serializes_native_database_values() -> None:
    db = Database()
    store = CallSessionStore(db, uuid4())  # type: ignore[arg-type]
    appointment_id = uuid4()
    starts_at = datetime(2026, 9, 13, 10, 30, tzinfo=UTC)

    await store.transition_operation(
        operation_id=uuid4(),
        expected_statuses=("APPROVED",),
        next_status="COMMITTED",
        result_payload={
            "ok": True,
            "appointment_id": appointment_id,
            "starts_at": starts_at,
        },
    )

    payload = json.loads(db.calls[0][1]["result"])
    assert payload["appointment_id"] == str(appointment_id)
    assert payload["starts_at"] == str(starts_at)


@pytest.mark.asyncio
async def test_store_loads_serialized_call_state() -> None:
    call = CallSession(call_id="provider-call", caller_phone="+919800000001")
    call.capture_turn()
    db = Database()
    db_result = {
        "id": str(uuid4()),
        "owner_token": str(uuid4()),
        "state": call.as_state(),
    }

    async def execute(statement, params):
        db.calls.append((str(statement), params))
        return Result(row=db_result)

    db.execute = execute  # type: ignore[method-assign]
    store = CallSessionStore(db, uuid4())  # type: ignore[arg-type]

    loaded = await store.load_active("provider-call")

    assert loaded is not None
    assert loaded.call.call_id == "provider-call"
    assert loaded.call.latest_turn is not None
