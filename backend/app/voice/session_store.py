"""PostgreSQL persistence for versioned telephone call state."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.voice.session import CallSession, CallStateError


def _json_payload(payload: dict[str, Any] | None) -> str:
    """Serialize database tool output for the durable operation audit record.

    PostgreSQL functions return native UUID and datetime values through SQLAlchemy.
    Those values are valid booking results, but the standard JSON encoder does not
    support them. Store their stable string form so recording the audit evidence
    cannot roll back an otherwise successful appointment transaction.
    """
    return json.dumps(payload or {}, default=str)


class PersistedCallSession(tuple[UUID, UUID, CallSession]):
    """A loaded database identity, ownership fence and call state."""

    __slots__ = ()

    @property
    def session_id(self) -> UUID:
        return self[0]

    @property
    def owner_token(self) -> UUID:
        return self[1]

    @property
    def call(self) -> CallSession:
        return self[2]


class CallSessionStore:
    def __init__(self, session: AsyncSession, organization_id: UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    async def create(
        self, call: CallSession, *, expires_at: datetime | None = None
    ) -> tuple[UUID, UUID]:
        expiry = expires_at or datetime.now(UTC) + timedelta(minutes=15)
        result = await self._session.execute(
            text(
                """
                insert into public.voice_call_sessions
                    (organization_id, provider_call_id, caller_phone_e164, expires_at, state)
                values (:organization_id, :call_id, :caller_phone, :expires_at, cast(:state as jsonb))
                returning id, owner_token
                """
            ),
            {
                "organization_id": self._organization_id,
                "call_id": call.call_id,
                "caller_phone": call.caller_phone,
                "expires_at": expiry,
                "state": json.dumps(call.as_state()),
            },
        )
        row = result.mappings().one()
        return UUID(str(row["id"])), UUID(str(row["owner_token"]))

    async def load_active(self, provider_call_id: str) -> PersistedCallSession | None:
        result = await self._session.execute(
            text(
                """
                select id, owner_token, state
                from public.voice_call_sessions
                where organization_id=:organization_id
                  and provider_call_id=:call_id
                  and status='ACTIVE'
                  and expires_at > now()
                """
            ),
            {"organization_id": self._organization_id, "call_id": provider_call_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        raw_state = row["state"]
        state = raw_state if isinstance(raw_state, dict) else json.loads(str(raw_state))
        if not isinstance(state, dict):
            raise CallStateError("Persisted call state is invalid.")
        return PersistedCallSession(
            (UUID(str(row["id"])), UUID(str(row["owner_token"])), CallSession.from_state(state))
        )

    async def save(
        self,
        *,
        session_id: UUID,
        owner_token: UUID,
        call: CallSession,
        expected_version: int,
        expires_at: datetime | None = None,
    ) -> None:
        if call.state_version != expected_version + 1:
            raise CallStateError("Call state version must advance exactly once per persisted transition.")
        result = await self._session.execute(
            text(
                """
                update public.voice_call_sessions
                set state_version=:next_version,
                    state=cast(:state as jsonb),
                    expires_at=coalesce(:expires_at, expires_at)
                where id=:session_id
                  and organization_id=:organization_id
                  and owner_token=:owner_token
                  and status='ACTIVE'
                  and expires_at > now()
                  and state_version=:expected_version
                """
            ),
            {
                "session_id": session_id,
                "organization_id": self._organization_id,
                "owner_token": owner_token,
                "expected_version": expected_version,
                "next_version": call.state_version,
                "state": json.dumps(call.as_state()),
                "expires_at": expires_at,
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise CallStateError("Call session ownership or version is stale.")

    async def end(self, *, session_id: UUID, owner_token: UUID) -> None:
        result = await self._session.execute(
            text(
                """update public.voice_call_sessions
                   set status='ENDED', ended_at=now(), expires_at=now()
                   where id=:session_id and organization_id=:organization_id
                     and owner_token=:owner_token and status='ACTIVE'"""
            ),
            {"session_id": session_id, "organization_id": self._organization_id,
             "owner_token": owner_token},
        )
        if getattr(result, "rowcount", 0) != 1:
            raise CallStateError("Call session ownership or status is stale.")

    async def committed_booking_result(
        self, *, session_id: UUID, owner_token: UUID, caller_phone: str,
        operation_id: UUID, proposal_version: str,
    ) -> dict[str, Any] | None:
        """Read positive commit evidence, including for expired/ended calls.

        Use a fresh transaction after a lost commit response. Absence is not proof
        of rollback and must never authorize replay of the mutation.
        """
        result = await self._session.execute(
            text("""
                select o.result
                from public.voice_operation_records o
                join public.voice_call_sessions s
                  on s.id=o.voice_call_session_id and s.organization_id=o.organization_id
                where o.organization_id=:organization_id
                  and s.id=:session_id and s.owner_token=:owner_token
                  and s.caller_phone_e164=:caller_phone
                  and o.operation_id=:operation_id
                  and o.operation_type='BOOK' and o.proposal_version=:proposal_version
                  and o.status='COMMITTED' and o.committed_at is not null
            """),
            {"organization_id": self._organization_id, "session_id": session_id,
             "owner_token": owner_token, "caller_phone": caller_phone,
             "operation_id": operation_id, "proposal_version": proposal_version},
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        payload = row["result"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise CallStateError("Committed booking result is invalid.")
        return dict(payload)

    async def record_operation(
        self,
        *,
        session_id: UUID,
        operation_id: UUID,
        operation_type: str,
        proposal_version: str,
        idempotency_key: str,
        status: str = "PROPOSED",
        result_payload: dict[str, Any] | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                insert into public.voice_operation_records
                    (organization_id, voice_call_session_id, operation_id, operation_type,
                     proposal_version, idempotency_key, status, result)
                values (:organization_id, :session_id, :operation_id, :operation_type,
                        :proposal_version, :idempotency_key, :status, cast(:result as jsonb))
                """
            ),
            {
                "organization_id": self._organization_id,
                "session_id": session_id,
                "operation_id": operation_id,
                "operation_type": operation_type,
                "proposal_version": proposal_version,
                "idempotency_key": idempotency_key,
                "status": status,
                "result": _json_payload(result_payload),
            },
        )

    async def transition_operation(
        self,
        *,
        operation_id: UUID,
        expected_statuses: tuple[str, ...],
        next_status: str,
        result_payload: dict[str, Any] | None = None,
    ) -> None:
        result = await self._session.execute(
            text(
                """
                update public.voice_operation_records
                set status=:next_status,
                    result=cast(:result as jsonb),
                    committed_at=case when :next_status='COMMITTED' then now() else committed_at end
                where organization_id=:organization_id
                  and operation_id=:operation_id
                  and status = any(cast(:expected_statuses as text[]))
                """
            ),
            {
                "organization_id": self._organization_id,
                "operation_id": operation_id,
                "expected_statuses": list(expected_statuses),
                "next_status": next_status,
                "result": _json_payload(result_payload),
            },
        )
        if getattr(result, "rowcount", 0) != 1:
            raise CallStateError("Voice operation status is stale or invalid.")
