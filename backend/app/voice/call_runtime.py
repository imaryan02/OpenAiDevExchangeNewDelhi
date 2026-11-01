"""Serialized durable runtime state for one telephone call."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.operation_service import TrackedCall, VoiceOperationService
from app.agent.tools import ToolExecutor
from app.core.config import Settings
from app.voice.presentation import committed, correlation_scope, emit
from app.voice.proposals import booking_proposal
from app.voice.readback import ReadbackPlaybackLedger
from app.voice.session import CallSession, CallStateError, OperationProposal
from app.voice.session_store import CallSessionStore

T = TypeVar("T")


class VoiceCallRuntime:
    """One owner fence and one transition lock per provider call."""

    def __init__(self, database_session: AsyncSession, organization_id: UUID) -> None:
        self._database_session = database_session
        self._store = CallSessionStore(database_session, organization_id)
        self.operations = VoiceOperationService(self._store)
        self.tracked: TrackedCall | None = None
        self.lock = asyncio.Lock()
        self._organization_id = organization_id
        self._uncertain = False
        self._uncertain_booking: tuple[str, str] | None = None

    async def reconcile_booking(self, fresh_session: AsyncSession) -> dict[str, object] | None:
        """Recover a known committed result without retrying or reopening this call.

        The caller owns a separate, newly opened database session/transaction.
        None means still unresolved, never that a new booking is safe.
        """
        async with self.lock:
            if not self._uncertain or self._uncertain_booking is None or self.tracked is None:
                raise CallStateError("No uncertain booking to reconcile.")
            if fresh_session is self._database_session:
                raise CallStateError("Reconciliation requires a fresh database session.")
            operation_id, version = self._uncertain_booking
            return await CallSessionStore(fresh_session, self._organization_id).committed_booking_result(
                session_id=self.tracked.session_id, owner_token=self.tracked.owner_token,
                caller_phone=self.tracked.call.caller_phone,
                operation_id=UUID(operation_id), proposal_version=version,
            )

    async def prepare_booking(self, result: dict[str, object]) -> tuple[OperationProposal, str]:
        data = booking_proposal(result)

        async def prepare(tracked: TrackedCall) -> OperationProposal:
            return await self.operations.prepare(
                tracked, operation="BOOK", proposal_version=data.version,
                idempotency_key=f"voice-book:{tracked.session_id}:{data.version}",
            )

        proposal = await self.transition(prepare)
        emit("proposal_persisted", "consent", "Booking proposal persisted",
             proposal_id=proposal.id, durable_operation_id=proposal.id, operation_type="BOOK")
        return proposal, data.readback_text

    async def prepare_operation(self, *, operation: str, arguments: dict[str, object]) -> OperationProposal:
        """Persist a non-booking proposal whose server-held arguments cannot drift."""
        if operation not in {"CANCEL", "RESCHEDULE"}:
            raise CallStateError("Unsupported voice operation.")
        version = self._arguments_version(arguments)
        proposal = await self.transition(lambda tracked: self.operations.prepare(
            tracked, operation=operation, proposal_version=version,
            idempotency_key=f"voice-{operation.casefold()}:{tracked.session_id}:{version}",
        ))
        emit("proposal_persisted", "consent", "Operation proposal persisted",
             proposal_id=proposal.id, durable_operation_id=proposal.id, operation_type=operation)
        return proposal

    async def acknowledge_readback(
        self, *, proposal_id: str, segment_id: str, ledger: ReadbackPlaybackLedger, completed_at: datetime
    ) -> OperationProposal:
        return await self.transition(lambda tracked: self.operations.complete_acknowledged_readback(
            tracked, proposal_id=proposal_id, playback_segment_id=segment_id,
            ledger=ledger, completed_at=completed_at,
        ))

    async def transition(self, action: Callable[[TrackedCall], Awaitable[T]]) -> T:
        """Serialize and commit one domain transition; fence an uncertain commit."""
        async with self.lock:
            if self._uncertain or self.tracked is None:
                raise CallStateError("Call runtime is unavailable or requires reconciliation.")
            before = self.tracked.call.as_state()
            version = self.tracked.persisted_version
            committing = False
            try:
                result = await action(self.tracked)
                committing = True
                await self._database_session.commit()
                return result
            except BaseException:
                if committing:
                    self._uncertain = True
                    emit("mutation_failed", "database", "Commit outcome uncertain; reconciliation required")
                try:
                    await self._database_session.rollback()
                finally:
                    self.tracked.call = CallSession.from_state(before)
                    self.tracked.persisted_version = version
                raise

    async def confirm_booking(
        self, *, proposal_id: str, caller_turn_id: int, offer_token: str, settings: Settings
    ) -> dict[str, object]:
        """Commit approval, appointment and outcome under the same database transaction.

        The caller must have persisted an explicitly approved, correlated input turn.
        This is an internal boundary, never a model-exposed tool.
        """
        with correlation_scope(proposal_id=proposal_id, durable_operation_id=proposal_id,
                               caller_turn_id=caller_turn_id):
            async with self.lock:
                if self._uncertain or self.tracked is None:
                    raise CallStateError("Call runtime is unavailable or requires reconciliation.")
                tracked = self.tracked
                proposal = tracked.call.active_proposal
                if proposal is None or proposal.id != proposal_id or proposal.operation != "BOOK":
                    raise CallStateError("No matching booking proposal.")
                if hashlib.sha256(offer_token.encode()).hexdigest() != proposal.version:
                    raise CallStateError("Signed offer does not match the readback proposal.")
                if settings.voice_actor_id is None or settings.voice_organization_id != self._organization_id:
                    raise CallStateError("Voice actor or organization does not match the runtime.")
                before = tracked.call.as_state()
                version = tracked.persisted_version
                committing = False

                async def authorize(name: str, arguments: dict[str, Any]) -> dict[str, object] | None:
                    if name != "confirm_booking_offer" or arguments.get("offer_token") != offer_token:
                        return {"ok": False, "error": "Operation is outside the approved proposal."}
                    return None

                try:
                    approved = await self.operations.approve(
                        tracked, proposal_id=proposal_id, caller_turn_id=caller_turn_id
                    )
                    emit("approval_granted", "consent", "Backend accepted explicit confirmation")
                    result = await ToolExecutor(
                        self._database_session, self._organization_id,
                        actor_id=settings.voice_actor_id, settings=settings,
                        caller_phone_e164=tracked.call.caller_phone,
                        operation_authorizer=authorize, commit_mutations=False,
                        booking_source="AI_VOICE", booking_consent_channel="AI_VOICE",
                    ).execute("confirm_booking_offer", {"offer_token": offer_token})
                    if result.get("ok") is not True:
                        await self._database_session.rollback()
                        tracked.call = CallSession.from_state(before)
                        tracked.persisted_version = version
                        return result
                    await self.operations.committed(proposal=approved, result=result)
                    self._uncertain_booking = (proposal.id, proposal.version)
                    committing = True
                    emit("mutation_started", "database", "Committing approved booking transaction",
                         tool="confirm_booking_offer")
                    await self._database_session.commit()
                    self._uncertain_booking = None
                    committed("confirm_booking_offer", result)
                    return result
                except BaseException:
                    if committing:
                        self._uncertain = True
                        emit("mutation_failed", "database", "Commit outcome uncertain; reconciliation required")
                    try:
                        await self._database_session.rollback()
                    finally:
                        tracked.call = CallSession.from_state(before)
                        tracked.persisted_version = version
                    raise

    async def confirm_operation(
        self, *, operation: str, tool_name: str, proposal_id: str, caller_turn_id: int,
        arguments: dict[str, object], settings: Settings,
    ) -> dict[str, object]:
        """Atomically commit a server-held cancellation or reschedule after consent."""
        with correlation_scope(proposal_id=proposal_id, durable_operation_id=proposal_id,
                               caller_turn_id=caller_turn_id):
            if operation not in {"CANCEL", "RESCHEDULE"} or tool_name not in {
                "cancel_appointment", "reschedule_appointment"
            }:
                raise CallStateError("Unsupported voice operation.")
            async with self.lock:
                if self._uncertain or self.tracked is None:
                    raise CallStateError("Call runtime is unavailable or requires reconciliation.")
                tracked = self.tracked
                proposal = tracked.call.active_proposal
                if proposal is None or proposal.id != proposal_id or proposal.operation != operation:
                    raise CallStateError("No matching operation proposal.")
                if proposal.version != self._arguments_version(arguments):
                    raise CallStateError("Operation arguments do not match the readback proposal.")
                if settings.voice_actor_id is None or settings.voice_organization_id != self._organization_id:
                    raise CallStateError("Voice actor or organization does not match the runtime.")
                before, version = tracked.call.as_state(), tracked.persisted_version
                committing = False

                async def authorize(name: str, requested: dict[str, Any]) -> dict[str, object] | None:
                    if name != tool_name or requested != arguments:
                        return {"ok": False, "error": "Operation is outside the approved proposal."}
                    return None

                try:
                    approved = await self.operations.approve(
                        tracked, proposal_id=proposal_id, caller_turn_id=caller_turn_id
                    )
                    emit("approval_granted", "consent", "Backend accepted explicit confirmation")
                    result = await ToolExecutor(
                        self._database_session, self._organization_id, actor_id=settings.voice_actor_id,
                        settings=settings, caller_phone_e164=tracked.call.caller_phone,
                        operation_authorizer=authorize, commit_mutations=False,
                        booking_source="AI_VOICE", booking_consent_channel="AI_VOICE",
                    ).execute(tool_name, arguments)
                    if result.get("ok") is not True:
                        await self._database_session.rollback()
                        tracked.call = CallSession.from_state(before)
                        tracked.persisted_version = version
                        return result
                    await self.operations.committed(proposal=approved, result=result)
                    committing = True
                    emit("mutation_started", "database", "Committing approved appointment change", tool=tool_name)
                    await self._database_session.commit()
                    committed(tool_name, result)
                    return result
                except BaseException:
                    if committing:
                        self._uncertain = True
                        emit("mutation_failed", "database", "Commit outcome uncertain; reconciliation required")
                    try:
                        await self._database_session.rollback()
                    finally:
                        tracked.call = CallSession.from_state(before)
                        tracked.persisted_version = version
                    raise

    @staticmethod
    def _arguments_version(arguments: dict[str, object]) -> str:
        try:
            serialized = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        except (TypeError, ValueError) as error:
            raise CallStateError("Operation arguments are not serializable.") from error
        return hashlib.sha256(serialized.encode()).hexdigest()

    async def capture_turn(self, *, captured_at: datetime | None = None, preserve_active_proposal: bool = False) -> int:
        return await self.transition(lambda tracked: self.operations.capture_turn(
            tracked, captured_at=captured_at, preserve_active_proposal=preserve_active_proposal,
        ))

    async def start(self, *, provider_call_id: str, caller_phone: str) -> TrackedCall:
        async with self.lock:
            if self._uncertain:
                raise CallStateError("Call runtime requires reconciliation.")
            if self.tracked is not None:
                if (self.tracked.call.call_id, self.tracked.call.caller_phone) != (provider_call_id, caller_phone):
                    raise CallStateError("Call runtime is already bound to a different caller or call.")
                return self.tracked
            existing = await self._store.load_active(provider_call_id)
            if existing is not None:
                if existing.call.caller_phone != caller_phone:
                    raise CallStateError("Active call does not belong to this caller.")
                self.tracked = TrackedCall(
                    session_id=existing.session_id, owner_token=existing.owner_token,
                    persisted_version=existing.call.state_version, call=existing.call,
                )
                return self.tracked
            call = CallSession(call_id=provider_call_id, caller_phone=caller_phone)
            committing = False
            try:
                session_id, owner_token = await self._store.create(call)
                committing = True
                await self._database_session.commit()
            except BaseException:
                if committing:
                    self._uncertain = True
                await self._database_session.rollback()
                raise
            self.tracked = TrackedCall(
                session_id=session_id, owner_token=owner_token, persisted_version=0, call=call
            )
            return self.tracked

    async def end(self) -> None:
        """Close the durable call once carrier media has ended."""
        async with self.lock:
            if self.tracked is None or self._uncertain:
                return
            await self._store.end(
                session_id=self.tracked.session_id, owner_token=self.tracked.owner_token
            )
            await self._database_session.commit()
