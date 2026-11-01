"""VoiceLink outbound queue adapter and event binding for Friday callbacks."""

import hashlib
import hmac
import json
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import get_session_factory
from app.personal_agent.config import PersonalSettings
from app.personal_agent.repository import PersonalRepository
from app.personal_agent.worker import Claim, DispatchResult
from app.voice.voicelink_gateway import _normalize_e164_phone, _phone_digits

ADD_LEAD_URL = "https://app.voicelink.co.in/api/v1/add_lead"
logger = structlog.get_logger()


def binding(secret: str, attempt_id: UUID) -> str:
    signature = hmac.new(secret.encode(), str(attempt_id).encode(), hashlib.sha256).hexdigest()
    return f"{attempt_id}:{signature}"


def bound_attempt(secret: str, custom: object) -> UUID | None:
    if isinstance(custom, str):
        try:
            custom = json.loads(custom)
        except ValueError:
            return None
    if not isinstance(custom, dict):
        return None
    token = custom.get("friday_binding")
    if not isinstance(token, str):
        return None
    try:
        candidate = UUID(token.split(":", 1)[0])
    except ValueError:
        return None
    return candidate if hmac.compare_digest(token, binding(secret, candidate)) else None


class VoiceLinkCallbacks:
    def __init__(self, settings: Settings, config: PersonalSettings) -> None:
        self.settings, self.config = settings, config

    async def dispatch(self, claim: Claim) -> DispatchResult:
        settings, config = self.settings, self.config
        if not (
            config.enabled and config.outbound_enabled and config.voicelink_api_token
            and config.registered_phone and settings.voicelink_phone_number
            and settings.verification_code_pepper and settings.database_url
            and claim.owner_id == config.owner_id
        ):
            return DispatchResult("failed", error_code="VOICELINK_NOT_CONFIGURED")
        sessions = get_session_factory(settings.database_url)
        async with sessions() as session:
            result = await session.execute(
                text("""select p.phone_e164 from public.personal_agent_profiles p
                        join public.personal_agent_followups f on f.owner_id=p.owner_id
                        where p.owner_id=:owner and p.generation=:generation
                        and f.id=:event and f.version=:version
                        and f.lease_token=:token and f.status='in_progress'"""),
                {"owner": claim.owner_id, "generation": claim.generation,
                 "event": claim.event_id, "version": claim.version,
                 "token": claim.token},
            )
            destination = result.scalar_one_or_none()
        if destination != config.registered_phone:
            return DispatchResult("failed", error_code="CALLBACK_DESTINATION_CHANGED")
        destination_digits = _phone_digits(destination)
        if len(destination_digits) != 12 or not destination_digits.startswith("91"):
            return DispatchResult("failed", error_code="VOICELINK_DESTINATION_NOT_INDIAN")
        body = {
            "did_number": _phone_digits(settings.voicelink_phone_number),
            # The national form reached the owner in the controlled outbound probe.
            "customer_number": destination_digits[2:],
            "country_code": "91",
            "call_limit": 1,
            "custom_parameters": json.dumps({
                "friday_binding": binding(settings.verification_code_pepper, claim.attempt_id)
            }),
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                ADD_LEAD_URL, json=body,
                headers={"Authorization": f"Bearer {config.voicelink_api_token}"},
            )
        if response.status_code in (400, 401, 403, 404, 422):
            return DispatchResult("failed", error_code=f"VOICELINK_HTTP_{response.status_code}")
        if response.status_code >= 500 or response.status_code not in (200, 201, 202):
            return DispatchResult("unknown", error_code=f"VOICELINK_HTTP_{response.status_code}")
        try:
            payload: Any = response.json()
        except ValueError:
            return DispatchResult("unknown", error_code="VOICELINK_RESPONSE_INVALID")
        if not isinstance(payload, dict) or payload.get("status") is not True:
            return DispatchResult("failed", error_code="VOICELINK_LEAD_REJECTED")
        data = payload.get("data")
        # The documented single-lead response includes outbound_queue_id.
        # Queue acceptance does not prove that a carrier call was answered.
        if not isinstance(data, dict) or not data.get("outbound_queue_id"):
            return DispatchResult("unknown", error_code="VOICELINK_QUEUE_ID_MISSING")
        return DispatchResult("accepted")


async def process_callback_event(settings: Settings, payload: dict[str, Any]) -> None:
    """Apply authenticated carrier lifecycle evidence to a signed callback attempt."""
    from app.personal_agent.config import get_personal_settings

    config = get_personal_settings()
    if not (config.enabled and config.owner_id and config.registered_phone
            and settings.database_url and settings.verification_code_pepper):
        return
    event_type = str(payload.get("event") or "").lower()
    if event_type not in {"call.initiated", "call.answered", "call.ended", "call.completed"}:
        return
    custom = payload.get("customParameters") or payload.get("custom_parameters")
    attempt_id = bound_attempt(settings.verification_code_pepper, custom)
    if attempt_id is None:
        return  # An unsigned receptionist event must never affect Friday.
    from_number = _normalize_e164_phone(payload.get("fromNumber"))
    to_number = _normalize_e164_phone(payload.get("toNumber"))
    if (from_number and _phone_digits(from_number)
            != _phone_digits(settings.voicelink_phone_number)):
        return
    if to_number and to_number != config.registered_phone:
        return
    provider_call = str(payload.get("callId") or "").strip()
    status = str(payload.get("callStatus") or "").upper().replace("-", "_")
    fallback_needed = False
    async with get_session_factory(settings.database_url).begin() as session:
        repo = PersonalRepository(session, config.owner_id)
        result = await session.execute(
            text("""select a.followup_id,a.generation,a.event_version,a.status as attempt_status,
                           a.provider_call_id,f.version as event_version_now,
                           f.status as event_status,f.call_attempts,
                           p.generation as owner_generation,
                           p.phone_e164
                    from public.personal_agent_attempts a
                    join public.personal_agent_followups f
                      on f.owner_id=a.owner_id and f.id=a.followup_id
                    join public.personal_agent_profiles p on p.owner_id=a.owner_id
                    where a.owner_id=:owner and a.id=:attempt for update of a,f"""),
            {"owner": config.owner_id, "attempt": attempt_id},
        )
        row = result.mappings().one_or_none()
        if (row is None or row["generation"] != row["owner_generation"]
                or row["phone_e164"] != config.registered_phone
                or row["provider_call_id"] not in (None, provider_call)
                or row["attempt_status"] in ("completed", "busy", "no-answer", "failed", "canceled")
                or row["event_status"] in ("resolved", "cancelled")):
            return
        if provider_call:
            await session.execute(
                text("""update public.personal_agent_attempts
                        set provider_call_id=:call,updated_at=now()
                        where owner_id=:owner and id=:attempt"""),
                {"owner": config.owner_id, "attempt": attempt_id, "call": provider_call},
            )
        if (event_type == "call.initiated"
                and row["attempt_status"] == "in-progress"):
            return
        if event_type in ("call.initiated", "call.answered"):
            attempt_status = "ringing" if event_type == "call.initiated" else "in-progress"
            await session.execute(
                text("""update public.personal_agent_attempts
                        set status=:status,updated_at=now()
                        where owner_id=:owner and id=:attempt"""),
                {"owner": config.owner_id, "attempt": attempt_id, "status": attempt_status},
            )
            if event_type == "call.answered" and row["event_status"] == "in_progress":
                await session.execute(
                    text("""update public.personal_agent_followups
                            set status='awaiting_acknowledgment',next_action=null,
                                next_action_at=null,lease_token=null,lease_until=null,
                                version=version+1,updated_at=now()
                            where owner_id=:owner and id=:event and status='in_progress'
                            and version=:version"""),
                    {"owner": config.owner_id, "event": row["followup_id"],
                     "version": row["event_version"]},
                )
            await repo.activity(
                "callback_ringing" if event_type == "call.initiated" else "callback_answered",
                "Friday callback ringing" if event_type == "call.initiated"
                else "Friday callback answered",
                followup_id=row["followup_id"],
            )
            return
        # Treat a terminal event with no trustworthy result as needing review.
        answered = status in {"ANSWER", "ANSWERED", "COMPLETED", "SUCCESS"}
        missed = status in {"NO_ANSWER", "NOANSWER", "BUSY", "FAILED", "FAILURE",
                            "CANCELLED", "CANCELED", "REJECTED"}
        if not (answered or missed) and row["attempt_status"] == "in-progress":
            answered = True
        attempt_status = (
            "completed" if answered else
            "busy" if status == "BUSY" else
            "no-answer" if status in {"NO_ANSWER", "NOANSWER"} else
            "failed" if missed else "unknown"
        )
        await session.execute(
            text("""update public.personal_agent_attempts
                    set status=:status,error_code=:reason,updated_at=now()
                    where owner_id=:owner and id=:attempt"""),
            {"owner": config.owner_id, "attempt": attempt_id,
             "status": attempt_status, "reason": status or "STATUS_MISSING"},
        )
        if row["event_status"] in ("in_progress", "awaiting_acknowledgment"):
            if answered:
                new_status, next_action = "awaiting_acknowledgment", None
            elif missed and row["call_attempts"] < config.max_call_attempts:
                new_status, next_action = "scheduled", "call"
            else:
                new_status, next_action = "needs_attention", None
            await session.execute(
                text("""update public.personal_agent_followups
                        set status=:status,next_action=:action,
                            next_action_at=case when :action='call'
                                then now()+make_interval(secs=>:delay) else null end,
                            lease_token=null,lease_until=null,version=version+1,updated_at=now()
                        where owner_id=:owner and id=:event
                        and status in ('in_progress','awaiting_acknowledgment')
                        and version in (:version,:answered_version)"""),
                {"owner": config.owner_id, "event": row["followup_id"],
                 "status": new_status, "action": next_action,
                 "delay": config.retry_seconds, "version": row["event_version"],
                 "answered_version": row["event_version"] + 1},
            )
        await repo.activity(
            "callback_completed" if answered else "callback_missed" if missed
            else "callback_needs_attention",
            "Friday callback ended" if answered else "Friday callback was not answered"
            if missed else "Friday callback result needs review",
            followup_id=row["followup_id"],
            metadata={"carrier_status": status},
        )
        fallback_needed = missed and row["call_attempts"] >= config.max_call_attempts
    if fallback_needed:
        from app.personal_agent.messaging import send_missed_call_fallback

        try:
            await send_missed_call_fallback(settings, config, row["followup_id"])
        except Exception as error:
            # The worker will find this durable needs-attention event and stage
            # the opt-in fallback. Do not ask VoiceLink to replay the call event.
            logger.warning("personal_fallback_deferred", error_type=type(error).__name__)
