"""Select Personal AI once, after carrier authentication and valid start metadata."""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import ApiError
from app.db.session import get_session_factory
from app.personal_agent.callbacks import bound_attempt
from app.personal_agent.config import PersonalSettings
from app.personal_agent.repository import PersonalRepository
from app.voice.gateway import VoiceProtocolError
from app.voice.voicelink_gateway import _normalize_e164_phone, _phone_digits

logger = structlog.get_logger()


def validate_start(message: dict[str, Any], settings: Settings) -> dict[str, str]:
    start = message.get("start")
    if not isinstance(start, dict):
        raise VoiceProtocolError("Missing stream start payload.")
    media = start.get("media_format")
    if not isinstance(media, dict) or media.get("encoding") != "audio/alaw":
        raise VoiceProtocolError("Unsupported VoiceLink audio format.")
    if str(media.get("sample_rate")) != "8000":
        raise VoiceProtocolError("Unsupported VoiceLink sample rate.")
    caller = _normalize_e164_phone(
        start.get("from")
        or start.get("caller")
        or start.get("caller_number")
        or start.get("callerNumber")
        or message.get("from")
    )
    called = _normalize_e164_phone(
        start.get("to")
        or start.get("called")
        or start.get("called_number")
        or start.get("calledNumber")
        or message.get("to")
    )
    stream = str(start.get("stream_sid") or message.get("stream_sid") or "")
    call = str(start.get("call_sid") or "")
    if not caller or not called or not stream or not call:
        raise VoiceProtocolError("Incomplete VoiceLink call metadata.")
    custom = start.get("custom_parameters")
    attempt_id = (
        bound_attempt(settings.verification_code_pepper, custom)
        if settings.verification_code_pepper
        else None
    )
    outbound = attempt_id is not None and (
        _phone_digits(caller) == _phone_digits(settings.voicelink_phone_number)
    )
    if outbound:
        caller, called = called, caller
    if _phone_digits(called) != _phone_digits(settings.voicelink_phone_number):
        raise VoiceProtocolError("Unexpected VoiceLink destination.")
    return {
        "caller": caller,
        "called": called,
        "stream_sid": stream,
        "call_sid": call,
        "direction": "outbound" if outbound else "inbound",
        "attempt_id": str(attempt_id) if outbound else "",
    }


async def select_callback_call(
    settings: Settings,
    config: PersonalSettings,
    context: dict[str, str],
    *,
    provider: str = "voicelink",
) -> tuple[UUID, int] | None:
    if not (
        config.enabled
        and config.owner_id
        and config.registered_phone
        and settings.database_url
        and context.get("attempt_id")
        and context["caller"] == config.registered_phone
        and context["direction"] == "outbound"
    ):
        return None
    attempt_id = UUID(context["attempt_id"])
    async with get_session_factory(settings.database_url).begin() as session:
        repo = PersonalRepository(session, config.owner_id)
        profile = await repo.profile(lock=True)
        if profile["phone_e164"] != config.registered_phone:
            return None
        result = await session.execute(
            text("""select a.followup_id,a.event_version,a.provider_call_id,
                           f.status as event_status,f.version as event_version
                    from public.personal_agent_attempts a
                    join public.personal_agent_followups f
                      on f.owner_id=a.owner_id and f.id=a.followup_id
                    where a.owner_id=:owner and a.id=:attempt
                    and a.generation=:generation and f.generation=:generation
                    and a.status in ('submitting','accepted','ringing','in-progress','unknown')
                    and f.status in ('in_progress','awaiting_acknowledgment')
                    and f.version in (a.event_version,a.event_version+1)
                    for update of a,f"""),
            {"owner": config.owner_id, "attempt": attempt_id, "generation": profile["generation"]},
        )
        row = result.mappings().one_or_none()
        if row is None or row["provider_call_id"] not in (None, context["call_sid"]):
            return None
        active = await session.execute(
            text("""select exists(select 1 from public.personal_agent_calls
                    where owner_id=:owner and status='active'
                    and heartbeat_at>now()-interval '60 seconds')"""),
            {"owner": config.owner_id},
        )
        if active.scalar_one():
            return None
        await session.execute(
            text("""update public.personal_agent_calls
                    set status='expired',ended_at=now()
                    where owner_id=:owner and status='active'
                    and heartbeat_at<=now()-interval '60 seconds'"""),
            {"owner": config.owner_id},
        )
        await session.execute(
            text("""update public.personal_agent_attempts
                    set provider_call_id=:call,status='in-progress',updated_at=now()
                    where owner_id=:owner and id=:attempt"""),
            {"owner": config.owner_id, "attempt": attempt_id, "call": context["call_sid"]},
        )
        created = await session.execute(
            text("""insert into public.personal_agent_calls
                    (owner_id,generation,provider,provider_call_id,direction,followup_id)
                    values (:owner,:generation,:provider,:call,'outbound',:event)
                    on conflict (provider,provider_call_id) do nothing returning id"""),
            {
                "owner": config.owner_id,
                "generation": profile["generation"],
                "call": context["call_sid"],
                "event": row["followup_id"],
                "provider": provider,
            },
        )
        call_id = created.scalar_one_or_none()
        if call_id is None:
            raise VoiceProtocolError("Duplicate callback stream.")
        await session.execute(
            text("""update public.personal_agent_followups
                    set status='awaiting_acknowledgment',next_action=null,
                        next_action_at=null,lease_token=null,lease_until=null,
                        version=version+1,updated_at=now()
                    where owner_id=:owner and id=:event and generation=:generation
                    and status='in_progress' and version=:version"""),
            {
                "owner": config.owner_id,
                "event": row["followup_id"],
                "generation": profile["generation"],
                "version": row["event_version"],
            },
        )
        await repo.activity(
            "callback_started",
            "Owner answered Friday's callback",
            followup_id=row["followup_id"],
            call_id=call_id,
        )
        return call_id, profile["generation"]


async def select_personal_call(
    settings: Settings, config: PersonalSettings, context: dict[str, str]
) -> tuple[UUID, int] | None:
    if not config.enabled or not config.owner_id or not settings.database_url:
        return None
    if not settings.realtime_configured or context["direction"].startswith("outbound"):
        return None
    if config.registered_phone and context["caller"] != config.registered_phone:
        return None
    # Only lookup failures fall back. After a personal call is committed, runtime
    # errors end it; they must not switch an established call to another identity.
    try:
        async with get_session_factory(settings.database_url).begin() as session:
            repo = PersonalRepository(session, config.owner_id)
            profile = await repo.profile(lock=True)
            if profile["mode"] != "personal_agent" or profile["phone_e164"] != context["caller"]:
                return None
            active = await session.execute(
                text("""select exists(select 1 from public.personal_agent_calls
                        where owner_id=:owner and status='active'
                        and heartbeat_at>now()-interval '60 seconds')"""),
                {"owner": config.owner_id},
            )
            if active.scalar_one():
                raise ApiError("PERSONAL_CALL_ACTIVE", "Another personal call is active.", 409)
            await session.execute(
                text("""update public.personal_agent_calls set status='expired',ended_at=now()
                        where owner_id=:owner and status='active'
                        and heartbeat_at<=now()-interval '60 seconds'"""),
                {"owner": config.owner_id},
            )
            result = await session.execute(
                text("""insert into public.personal_agent_calls
                        (owner_id,generation,provider,provider_call_id,direction)
                        values (:owner,:generation,'voicelink',:call,'inbound') returning id"""),
                {
                    "owner": config.owner_id,
                    "generation": profile["generation"],
                    "call": context["call_sid"],
                },
            )
            call_id = result.scalar_one()
            await repo.activity(
                "call_started", "Incoming Personal AI call started", call_id=call_id
            )
            selected = (call_id, profile["generation"])
        return selected
    except IntegrityError as error:
        # A reused carrier call ID must not reconnect with a different personality.
        raise VoiceProtocolError("Duplicate personal carrier call.") from error
    except ApiError as error:
        if error.code == "PERSONAL_CALL_ACTIVE":
            raise
        logger.warning("personal_route_lookup_failed", error_type=type(error).__name__)
        return None
    except Exception as error:
        logger.warning("personal_route_lookup_failed", error_type=type(error).__name__)
        return None
