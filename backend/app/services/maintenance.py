import asyncio
from datetime import date, timedelta

import structlog
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import get_session_factory
from app.services.outbox import dispatch_outbox_once
from app.services.schedule_generation import generate_active_organization_sessions

logger = structlog.get_logger()


async def run_maintenance(settings: Settings) -> None:
    """Expire stale state, extend schedules, and dispatch notifications."""
    if settings.database_url is None:
        return
    factory = get_session_factory(settings.database_url)
    next_schedule_generation = 0.0
    while True:
        try:
            async with factory() as session:
                expired = (
                    await session.execute(
                        text("select public.expire_simulated_appointment_holds()")
                    )
                ).scalar_one()
                verification_expiry_available = (
                    await session.execute(
                        text(
                            "select to_regprocedure("
                            "'public.expire_verification_challenges()') is not null"
                        )
                    )
                ).scalar_one()
                expired_verifications = 0
                if verification_expiry_available:
                    expired_verifications = (
                        await session.execute(
                            text("select public.expire_verification_challenges()")
                        )
                    ).scalar_one()
                expired_voice_result = await session.execute(
                    text(
                        """update public.voice_call_sessions
                           set status='EXPIRED', ended_at=now()
                           where status in ('ACTIVE', 'CLOSING') and expires_at <= now()"""
                    )
                )
                expired_voice_sessions = int(getattr(expired_voice_result, "rowcount", 0) or 0)
                messages_available = (await session.execute(text(
                    "select to_regclass('public.voice_observability_messages') is not null"
                ))).scalar_one()
                if messages_available:
                    await session.execute(text(
                        "delete from public.voice_observability_messages where expires_at <= now()"
                    ))
                if asyncio.get_running_loop().time() >= next_schedule_generation:
                    generated = await generate_active_organization_sessions(
                        session, date.today() + timedelta(days=21)
                    )
                    if generated:
                        logger.info("rolling_schedule_sessions_generated", count=generated)
                await session.commit()
                if asyncio.get_running_loop().time() >= next_schedule_generation:
                    next_schedule_generation = asyncio.get_running_loop().time() + 3600
                if expired:
                    logger.info("appointment_holds_expired", count=expired)
                if expired_verifications:
                    logger.info("verification_challenges_expired", count=expired_verifications)
                if expired_voice_sessions:
                    logger.info("voice_call_sessions_expired", count=expired_voice_sessions)
            async with factory() as outbox_session:
                delivered = await dispatch_outbox_once(outbox_session, settings)
                if delivered:
                    logger.info("outbox_notifications_delivered", count=delivered)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("maintenance_cycle_failed")
        await asyncio.sleep(60)
