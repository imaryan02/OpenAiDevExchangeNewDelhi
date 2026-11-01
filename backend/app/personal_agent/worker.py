"""Durable personal callback claims with injected provider adapter.

The future adapter is injected, never selected by the model. Leasing, submitting
and result transactions end before network work. Uncertain submission never redials.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.session import get_session_factory
from app.personal_agent.config import PersonalSettings, get_personal_settings
from app.personal_agent.repository import PersonalRepository

logger = structlog.get_logger()


@dataclass(frozen=True)
class Claim:
    owner_id: UUID
    event_id: UUID
    attempt_id: UUID
    generation: int
    version: int
    token: UUID


@dataclass(frozen=True)
class DispatchResult:
    status: Literal["accepted", "failed", "unknown"]
    provider_call_id: str | None = None
    error_code: str | None = None


Dispatch = Callable[[Claim], Awaitable[DispatchResult]]


class PersonalScheduler:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        config: PersonalSettings,
        settings: Settings | None = None,
    ):
        self.sessions, self.config, self.settings = sessions, config, settings

    async def pending_fallback(self) -> None:
        if not (
            self.settings
            and self.config.owner_id
            and self.config.registered_phone
            and self.config.whatsapp_enabled
            and self.settings.twilio_whatsapp_configured
            and self.settings.public_backend_url
        ):
            return
        async with self.sessions() as session:
            result = await session.execute(
                text("""select f.id from public.personal_agent_followups f
                        join public.personal_agent_profiles p on p.owner_id=f.owner_id
                        where f.owner_id=:owner and f.generation=p.generation
                        and p.whatsapp_fallback and f.status='needs_attention'
                        and f.call_attempts>=:maximum
                        and not exists(select 1 from public.personal_agent_messages m
                          where m.owner_id=f.owner_id and m.followup_id=f.id
                          and m.generation=f.generation and m.status!='canceled')
                        order by f.updated_at,f.id limit 1"""),
                {"owner": self.config.owner_id, "maximum": self.config.max_call_attempts},
            )
            event_id = result.scalar_one_or_none()
        if event_id:
            from app.personal_agent.messaging import send_missed_call_fallback

            await send_missed_call_fallback(self.settings, self.config, event_id)

    async def claim(self) -> Claim | None:
        if not self.config.owner_id:
            return None
        async with self.sessions.begin() as session:
            repo = PersonalRepository(session, self.config.owner_id)
            profile = await repo.profile(lock=True)
            # A process may stop after staging a WhatsApp send. Its outcome is
            # uncertain, so surface it for review without resubmitting it.
            stale_messages = await session.execute(
                text("""select id,followup_id,event_version
                        from public.personal_agent_messages
                        where owner_id=:owner and generation=:generation
                        and status='submitting'
                        and updated_at<now()-interval '2 minutes' for update"""),
                {"owner": repo.owner_id, "generation": profile["generation"]},
            )
            for message in stale_messages.mappings():
                await session.execute(
                    text("""update public.personal_agent_messages
                            set status='unknown',updated_at=now()
                            where owner_id=:owner and id=:id and status='submitting'"""),
                    {"owner": repo.owner_id, "id": message["id"]},
                )
                await session.execute(
                    text("""update public.personal_agent_followups
                            set status='needs_attention',version=version+1,updated_at=now()
                            where owner_id=:owner and id=:event and generation=:generation
                            and status='awaiting_acknowledgment' and version=:version"""),
                    {
                        "owner": repo.owner_id,
                        "event": message["followup_id"],
                        "generation": profile["generation"],
                        "version": message["event_version"] + 1,
                    },
                )
                await repo.activity(
                    "whatsapp_unconfirmed",
                    "WhatsApp submission outcome needs review",
                    followup_id=message["followup_id"],
                    metadata={"message_id": str(message["id"])},
                )
            # Expired unsubmitted claims are safe to requeue. Anything submitted
            # may have reached the carrier and requires explicit reconciliation.
            expired = await session.execute(
                text("""select id,version from public.personal_agent_followups
                        where owner_id=:owner and generation=:generation
                        and status='in_progress' and lease_until<now() for update"""),
                {"owner": repo.owner_id, "generation": profile["generation"]},
            )
            for row in expired.mappings():
                uncertain = await session.execute(
                    text("""select exists(select 1 from public.personal_agent_attempts
                            where owner_id=:owner and followup_id=:id and event_version=:version
                            and status in
                              ('submitting','accepted','ringing','in-progress','unknown'))"""),
                    {"owner": repo.owner_id, "id": row["id"], "version": row["version"]},
                )
                attention = uncertain.scalar_one()
                await session.execute(
                    text("""update public.personal_agent_attempts
                            set status=:status,updated_at=now()
                            where owner_id=:owner and followup_id=:id and event_version=:version
                            and status in ('queued','submitting')"""),
                    {
                        "owner": repo.owner_id,
                        "id": row["id"],
                        "version": row["version"],
                        "status": "unknown" if attention else "canceled",
                    },
                )
                await session.execute(
                    text("""update public.personal_agent_followups set status=:status,
                            next_action=case when :attention then null else 'call' end,
                            next_action_at=case when :attention then null else now() end,
                            lease_token=null,lease_until=null,version=version+1,updated_at=now()
                            where owner_id=:owner and id=:id"""),
                    {
                        "owner": repo.owner_id,
                        "id": row["id"],
                        "attention": attention,
                        "status": "needs_attention" if attention else "scheduled",
                    },
                )
                await repo.activity(
                    "lease_recovered",
                    "Submission uncertain; review required"
                    if attention
                    else "Unsubmitted reminder recovered",
                    followup_id=row["id"],
                )
            # If the carrier never sends a final status, stop waiting after the
            # maximum call length. This stays visible for manual review; a
            # missing webhook is never grounds for an automatic redial.
            stale = await session.execute(
                text("""select f.id,f.version from public.personal_agent_followups f
                        where f.owner_id=:owner and f.generation=:generation
                        and f.status='awaiting_acknowledgment'
                        and exists(select 1 from public.personal_agent_attempts a
                            where a.owner_id=:owner and a.followup_id=f.id
                            and a.status in ('accepted','ringing','in-progress')
                            and a.updated_at<now()-make_interval(secs=>:seconds))
                        and not exists(select 1 from public.personal_agent_calls c
                            where c.owner_id=:owner and c.followup_id=f.id
                            and c.status='active'
                            and c.heartbeat_at>now()-interval '60 seconds')
                        for update"""),
                {
                    "owner": repo.owner_id,
                    "generation": profile["generation"],
                    "seconds": self.config.max_call_seconds + 60,
                },
            )
            for row in stale.mappings():
                await session.execute(
                    text("""update public.personal_agent_followups
                            set status='needs_attention',version=version+1,
                                updated_at=now() where owner_id=:owner and id=:id
                                and version=:version"""),
                    {"owner": repo.owner_id, "id": row["id"], "version": row["version"]},
                )
                await repo.activity(
                    "callback_needs_attention",
                    "Callback final status missing",
                    followup_id=row["id"],
                )
            active = await session.execute(
                text("""select exists(select 1 from public.personal_agent_calls
                        where owner_id=:owner and status='active'
                        and heartbeat_at>now()-interval '60 seconds')
                        or exists(select 1 from public.personal_agent_attempts
                          where owner_id=:owner and generation=:generation
                          and status in
                            ('queued','submitting','accepted','ringing','in-progress','unknown')
                          and exists(select 1 from public.personal_agent_followups f
                            where f.id=personal_agent_attempts.followup_id
                            and f.owner_id=:owner
                            and f.status in ('in_progress','awaiting_acknowledgment')))"""),
                {"owner": repo.owner_id, "generation": profile["generation"]},
            )
            if active.scalar_one():
                return None
            due = await session.execute(
                text("""select * from public.personal_agent_followups
                        where owner_id=:owner and generation=:generation and status='scheduled'
                        and next_action='call' and next_action_at<=now()
                        order by next_action_at,id limit 1 for update skip locked"""),
                {"owner": repo.owner_id, "generation": profile["generation"]},
            )
            event = due.mappings().one_or_none()
            if event is None:
                return None
            late = await session.execute(
                text("select :trigger < now()-make_interval(secs=>:seconds)"),
                {"trigger": event["next_action_at"], "seconds": self.config.max_lateness_seconds},
            )
            if late.scalar_one() or event["call_attempts"] >= self.config.max_call_attempts:
                await session.execute(
                    text("""update public.personal_agent_followups set status='needs_attention',
                            next_action=null,next_action_at=null,version=version+1,updated_at=now()
                            where owner_id=:owner and id=:id"""),
                    {"owner": repo.owner_id, "id": event["id"]},
                )
                await repo.activity(
                    "reminder_needs_attention",
                    "Reminder late or attempt budget exhausted",
                    followup_id=event["id"],
                )
                return None
            token = uuid4()
            await session.execute(
                text("""update public.personal_agent_followups set status='in_progress',
                        lease_token=:token,lease_until=now()+make_interval(secs=>:seconds),
                        updated_at=now() where owner_id=:owner and id=:id"""),
                {
                    "owner": repo.owner_id,
                    "id": event["id"],
                    "token": token,
                    "seconds": self.config.lease_seconds,
                },
            )
            attempt = await session.execute(
                text("""insert into public.personal_agent_attempts
                        (owner_id,followup_id,generation,event_version)
                        values (:owner,:id,:generation,:version) returning id"""),
                {
                    "owner": repo.owner_id,
                    "id": event["id"],
                    "generation": profile["generation"],
                    "version": event["version"],
                },
            )
            await repo.activity(
                "reminder_triggered", "Reminder claimed for callback", followup_id=event["id"]
            )
            selected = Claim(
                repo.owner_id,
                event["id"],
                attempt.scalar_one(),
                profile["generation"],
                event["version"],
                token,
            )
        return selected

    async def submitting(self, claim: Claim) -> bool:
        async with self.sessions.begin() as session:
            profile = await PersonalRepository(session, claim.owner_id).profile(lock=True)
            if profile["generation"] != claim.generation:
                return False
            result = await session.execute(
                text("""update public.personal_agent_attempts a
                        set status='submitting',updated_at=now()
                        where a.owner_id=:owner and a.id=:attempt and a.status='queued'
                        and exists(select 1 from public.personal_agent_followups f
                          where f.owner_id=:owner and f.id=:id and f.version=:version
                          and f.generation=:generation and f.status='in_progress'
                          and f.lease_token=:token and f.lease_until>now())
                        and not exists(select 1 from public.personal_agent_calls c
                          where c.owner_id=:owner and c.status='active'
                          and c.heartbeat_at>now()-interval '60 seconds') returning a.id"""),
                {
                    "owner": claim.owner_id,
                    "attempt": claim.attempt_id,
                    "id": claim.event_id,
                    "version": claim.version,
                    "generation": claim.generation,
                    "token": claim.token,
                },
            )
            submitted = result.scalar_one_or_none() is not None
            if submitted:
                await session.execute(
                    text("""update public.personal_agent_followups set call_attempts=call_attempts+1
                            where owner_id=:owner and id=:id"""),
                    {"owner": claim.owner_id, "id": claim.event_id},
                )
        return submitted

    async def finish(self, claim: Claim, outcome: DispatchResult) -> None:
        async with self.sessions.begin() as session:
            repo = PersonalRepository(session, claim.owner_id)
            await repo.profile(lock=True)
            await session.execute(
                text("""update public.personal_agent_attempts set status=:status,
                        provider_call_id=:provider,error_code=:error,updated_at=now()
                        where owner_id=:owner and id=:attempt
                        and status in ('submitting','unknown')"""),
                {
                    "owner": claim.owner_id,
                    "attempt": claim.attempt_id,
                    "status": outcome.status,
                    "provider": outcome.provider_call_id,
                    "error": outcome.error_code,
                },
            )
            if outcome.status == "unknown":
                # VoiceLink may have accepted a timed-out POST. Keep the lease until
                # a signed callback or recovery marks it for manual reconciliation.
                await repo.activity(
                    "callback_uncertain",
                    "Callback submission outcome is unknown",
                    followup_id=claim.event_id,
                    metadata={"attempt_id": str(claim.attempt_id)},
                )
                return
            if outcome.status == "accepted":
                # Provider acceptance is not an answered call. The signed voice
                # webhook advances the event; the lease catches missing callbacks.
                await session.execute(
                    text("""update public.personal_agent_followups
                            set lease_until=now()+make_interval(secs=>:seconds),
                                updated_at=now()
                            where owner_id=:owner and id=:id and generation=:generation
                            and version=:version and status='in_progress'
                            and lease_token=:token"""),
                    {
                        "owner": claim.owner_id,
                        "id": claim.event_id,
                        "generation": claim.generation,
                        "version": claim.version,
                        "token": claim.token,
                        "seconds": self.config.max_call_seconds + 60,
                    },
                )
                await repo.activity(
                    "callback_accepted",
                    "Callback accepted by provider",
                    followup_id=claim.event_id,
                    metadata={"attempt_id": str(claim.attempt_id)},
                )
                return
            # A definite provider rejection is safe to retry within the budget.
            # Reschedule/cancel/reset wins over a late network response.
            await session.execute(
                text("""update public.personal_agent_followups
                        set status=case when call_attempts<:maximum
                            then 'scheduled' else 'needs_attention' end,
                        next_action=case when call_attempts<:maximum then 'call' else null end,
                        next_action_at=case when call_attempts<:maximum
                            then now()+make_interval(secs=>:delay) else null end,
                        lease_token=null,lease_until=null,
                        version=version+1,updated_at=now() where owner_id=:owner and id=:id
                        and generation=:generation and version=:version
                        and status='in_progress' and lease_token=:token"""),
                {
                    "owner": claim.owner_id,
                    "id": claim.event_id,
                    "generation": claim.generation,
                    "version": claim.version,
                    "token": claim.token,
                    "maximum": self.config.max_call_attempts,
                    "delay": self.config.retry_seconds,
                },
            )
            await repo.activity(
                "callback_rejected",
                "Callback rejected by provider; retry if eligible",
                followup_id=claim.event_id,
                metadata={"attempt_id": str(claim.attempt_id), "status": outcome.status},
            )

    async def run(self, dispatch: Dispatch) -> None:
        while True:
            try:
                await self.pending_fallback()
                claim = await self.claim()
                if claim and await self.submitting(claim):
                    try:
                        async with asyncio.timeout(self.config.lease_seconds / 2):
                            outcome = await dispatch(claim)
                    except Exception as error:
                        # A timeout/exception may occur AFTER provider acceptance.
                        outcome = DispatchResult("unknown", error_code=type(error).__name__)
                    await self.finish(claim, outcome)
            except asyncio.CancelledError:
                raise  # Expiring leases are reconciled after restart.
            except Exception as error:
                logger.warning("personal_worker_cycle_failed", error_type=type(error).__name__)
            await asyncio.sleep(self.config.worker_interval_seconds)


def start_worker(settings: Settings, dispatch: Dispatch | None = None) -> asyncio.Task[None] | None:
    try:
        config = get_personal_settings()
        if not (
            config.enabled
            and config.scheduler_enabled
            and config.outbound_enabled
            and config.owner_id
            and settings.database_url
        ):
            return None
        if dispatch is None:
            if config.callback_provider == "twilio":
                from app.personal_agent.twilio_callbacks import TwilioCallbacks, configured

                if not configured(settings):
                    logger.warning("personal_worker_disabled", reason="twilio_credentials_pending")
                    return None
                dispatch = TwilioCallbacks(settings, config).dispatch
            else:
                from app.personal_agent.callbacks import VoiceLinkCallbacks

                if not (
                    config.voicelink_api_token
                    and config.registered_phone
                    and settings.voicelink_phone_number
                    and settings.verification_code_pepper
                ):
                    logger.warning(
                        "personal_worker_disabled", reason="voicelink_credentials_pending"
                    )
                    return None
                dispatch = VoiceLinkCallbacks(settings, config).dispatch
        scheduler = PersonalScheduler(get_session_factory(settings.database_url), config, settings)
        return asyncio.create_task(scheduler.run(dispatch))
    except Exception as error:
        logger.warning("personal_worker_disabled", error_type=type(error).__name__)
        return None
