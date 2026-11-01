"""Owner-bound WhatsApp submission and signed Twilio delivery evidence."""

import hashlib
import json
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.db.session import get_session_factory
from app.integrations.twilio import TwilioWhatsAppClient
from app.personal_agent.config import PersonalSettings, get_personal_settings
from app.personal_agent.domain import next_message_status
from app.personal_agent.memory import bound_call
from app.personal_agent.repository import PersonalRepository
from app.personal_agent.tools import SendWhatsApp
from app.voice.security import valid_twilio_signature

router = APIRouter(prefix="/v1/personal-agent/whatsapp", tags=["personal WhatsApp"])


def status_url(settings: Settings, message_id: UUID) -> str:
    assert settings.public_backend_url
    root = str(settings.public_backend_url).rstrip("/")
    return f"{root}/v1/personal-agent/whatsapp/status/{message_id}"


async def send_missed_call_fallback(
    settings: Settings, config: PersonalSettings, event_id: UUID,
) -> None:
    """Send one update after the final unanswered callback."""
    if not (config.enabled and config.whatsapp_enabled and config.owner_id
            and config.registered_phone
            and settings.twilio_whatsapp_configured and settings.public_backend_url
            and settings.database_url):
        return
    sessions = get_session_factory(settings.database_url)
    async with sessions.begin() as session:
        repo = PersonalRepository(session, config.owner_id)
        profile = await repo.profile(lock=True)
        if (profile["phone_e164"] != config.registered_phone
                or not profile["whatsapp_fallback"]):
            return
        result = await session.execute(
            text("""select * from public.personal_agent_followups
                    where owner_id=:owner and id=:event and generation=:generation
                    and status='needs_attention' and call_attempts>=:maximum
                    for update"""),
            {"owner": config.owner_id, "event": event_id,
             "generation": profile["generation"],
             "maximum": config.max_call_attempts},
        )
        event = result.mappings().one_or_none()
        if event is None:
            return
        existing = await session.execute(
            text("""select exists(select 1 from public.personal_agent_messages
                    where owner_id=:owner and followup_id=:event
                    and generation=:generation and status!='canceled')"""),
            {"owner": config.owner_id, "event": event_id,
             "generation": profile["generation"]},
        )
        if existing.scalar_one():
            return
        body = f"Friday update: {event['title']}"
        if event["context"]:
            body += f"\n{event['context'][:400]}"
        snapshot = event["task_snapshot"]
        if isinstance(snapshot, list):
            titles = [str(item.get("title", ""))[:200]
                      for item in snapshot[:20] if isinstance(item, dict)]
            if titles:
                body += "\n\n" + "\n".join(f"• {title}" for title in titles if title)
        body = body[:1600]
        created = await session.execute(
            text("""insert into public.personal_agent_messages
                    (owner_id,followup_id,generation,event_version,body,status)
                    values (:owner,:event,:generation,:version,:body,'submitting')
                    returning id"""),
            {"owner": config.owner_id, "event": event_id,
             "generation": profile["generation"], "version": event["version"],
             "body": body},
        )
        message_id = created.scalar_one()
        await session.execute(
            text("""update public.personal_agent_followups
                    set status='awaiting_acknowledgment',version=version+1,updated_at=now()
                    where owner_id=:owner and id=:event and version=:version"""),
            {"owner": config.owner_id, "event": event_id,
             "version": event["version"]},
        )
        await repo.activity(
            "whatsapp_fallback_requested", "Missed-call WhatsApp fallback prepared",
            followup_id=event_id, metadata={"message_id": str(message_id)},
        )
    try:
        delivery = await TwilioWhatsAppClient(settings).send(
            config.registered_phone, body,
            status_callback=status_url(settings, message_id),
            content_sid=config.whatsapp_content_sid,
        )
        provider_id, status = delivery.provider_message_id, "accepted"
    except ApiError:
        # A provider timeout may happen after acceptance. Never send this row again.
        provider_id, status = None, "unknown"
    async with sessions.begin() as session:
        repo = PersonalRepository(session, config.owner_id)
        profile = await repo.profile(lock=True)
        await session.execute(
            text("""update public.personal_agent_messages
                    set provider_message_id=coalesce(provider_message_id,:provider),
                        status=case when status='submitting' then :status else status end,
                        updated_at=now()
                    where owner_id=:owner and id=:id and generation=:generation"""),
            {"owner": config.owner_id, "id": message_id,
             "generation": profile["generation"],
             "provider": provider_id, "status": status},
        )
        if status == "unknown":
            await session.execute(
                text("""update public.personal_agent_followups
                        set status='needs_attention',version=version+1,updated_at=now()
                        where owner_id=:owner and id=:event and generation=:generation
                        and status='awaiting_acknowledgment' and version=:version"""),
                {"owner": config.owner_id, "event": event_id,
                 "generation": profile["generation"],
                 "version": event["version"] + 1},
            )
        await repo.activity(
            "whatsapp_submitted" if provider_id else "whatsapp_unconfirmed",
            "Missed-call update submitted" if provider_id
            else "Missed-call WhatsApp outcome unconfirmed",
            followup_id=event_id, metadata={"message_id": str(message_id)},
        )


class PersonalMessenger:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        config: PersonalSettings,
        *,
        owner_id: UUID,
        call_id: UUID,
        generation: int,
    ) -> None:
        self.sessions, self.settings, self.config = sessions, settings, config
        self.owner_id, self.call_id, self.generation = owner_id, call_id, generation

    async def send(self, request_id: str, arguments: dict[str, object]) -> dict[str, object]:
        if not request_id or len(request_id) > 200:
            return {"ok": False, "code": "TOOL_REQUEST_INVALID"}
        try:
            data = SendWhatsApp.model_validate(arguments)
        except ValidationError:
            return {"ok": False, "code": "TOOL_ARGUMENT_INVALID"}
        if not (
            self.config.enabled
            and self.config.whatsapp_enabled
            and self.settings.twilio_whatsapp_configured
            and self.settings.public_backend_url
            and self.config.registered_phone
        ):
            return {"ok": False, "code": "WHATSAPP_NOT_READY"}
        encoded = json.dumps(
            {"name": "send_whatsapp_update", "arguments": arguments},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        async with self.sessions.begin() as session:
            repo = PersonalRepository(session, self.owner_id)
            call = await bound_call(repo, self.call_id, self.generation)
            profile = await repo.profile()
            if profile["phone_e164"] != self.config.registered_phone:
                return {"ok": False, "code": "DESTINATION_CHANGED"}
            previous = await session.execute(
                text("""select input_hash,result from public.personal_agent_tool_results
                        where owner_id=:owner and call_id=:call and request_id=:request"""),
                {"owner": self.owner_id, "call": self.call_id, "request": request_id},
            )
            old = previous.mappings().one_or_none()
            if old is not None:
                if old["input_hash"] != digest:
                    return {"ok": False, "code": "TOOL_REQUEST_REUSED"}
                return dict(old["result"])
            event_id = data.event_id or call["followup_id"]
            if call["followup_id"] and event_id != call["followup_id"]:
                return {"ok": False, "code": "FOLLOWUP_MISMATCH"}
            event = None
            if event_id:
                selected = await session.execute(
                    text("""select * from public.personal_agent_followups
                            where owner_id=:owner and generation=:generation and id=:id
                            and status not in ('resolved','cancelled') for update"""),
                    {"owner": self.owner_id, "generation": self.generation, "id": event_id},
                )
                event = selected.mappings().one_or_none()
                if event is None:
                    return {"ok": False, "code": "FOLLOWUP_UNAVAILABLE"}
            tasks = await repo.tasks(today_only=True)
            lines = [f"• {row['title']}" for row in tasks[:20]]
            if event is None and not lines:
                return {"ok": False, "code": "NO_UPDATE_AVAILABLE"}
            if event is None:
                created = await session.execute(
                    text("""insert into public.personal_agent_followups
                            (owner_id,generation,title,context,status,source_call_id)
                            values (:owner,:generation,'Task update',
                                'Owner requested a task update on WhatsApp',
                                'awaiting_acknowledgment',:call) returning id"""),
                    {"owner": self.owner_id, "generation": self.generation,
                     "call": self.call_id},
                )
                event_id = created.scalar_one()
            assert event_id is not None
            header = (
                f"Friday update: {event['title']}"
                if event else "Friday: today's pending tasks"
            )
            body = header
            if event and event["context"]:
                body += f"\n{event['context'][:400]}"
            if lines:
                body += "\n\n" + "\n".join(lines)
            body = body[:1600]
            message = await session.execute(
                text("""insert into public.personal_agent_messages
                        (owner_id,followup_id,generation,event_version,body,status)
                        select :owner,id,:generation,version,:body,'submitting'
                        from public.personal_agent_followups where owner_id=:owner
                        and generation=:generation and id=:event returning id"""),
                {"owner": self.owner_id, "generation": self.generation,
                 "event": event_id, "body": body},
            )
            message_id = message.scalar_one()
            staged: dict[str, object] = {
                "ok": False, "code": "WHATSAPP_SUBMITTING",
                "message": "WhatsApp request is being submitted.",
            }
            await session.execute(
                text("""insert into public.personal_agent_tool_results
                        (call_id,owner_id,request_id,input_hash,result)
                        values (:call,:owner,:request,:hash,cast(:result as jsonb))"""),
                {"call": self.call_id, "owner": self.owner_id, "request": request_id,
                 "hash": digest, "result": json.dumps(staged)},
            )
            await repo.activity(
                "whatsapp_requested", "Owner requested a WhatsApp update",
                call_id=self.call_id, followup_id=event_id,
                metadata={"message_id": str(message_id)},
            )
        # The provider request runs after the durable message and dedupe key commit.
        try:
            delivery = await TwilioWhatsAppClient(self.settings).send(
                self.config.registered_phone, body,
                status_callback=status_url(self.settings, message_id),
                content_sid=self.config.whatsapp_content_sid,
            )
            outcome: dict[str, object] = {
                "ok": True,
                "data": {"message_id": str(message_id), "status": "submitted",
                         "delivery_confirmed": False},
            }
            provider_id = delivery.provider_message_id
            status = "accepted"
        except ApiError:
            # A network failure may happen after Twilio accepted the request.
            # Wait for a signed status callback or manual review; never resend.
            outcome = {"ok": False, "code": "WHATSAPP_OUTCOME_UNKNOWN",
                       "message": "WhatsApp submission could not be confirmed."}
            provider_id = None
            status = "unknown"
        async with self.sessions.begin() as session:
            await PersonalRepository(session, self.owner_id).profile(lock=True)
            await session.execute(
                text("""update public.personal_agent_messages
                        set provider_message_id=coalesce(provider_message_id,:provider),
                            status=case when status='submitting' then :status else status end,
                            updated_at=now()
                        where owner_id=:owner and id=:id and generation=:generation"""),
                {"owner": self.owner_id, "id": message_id,
                 "generation": self.generation, "provider": provider_id,
                 "status": status},
            )
            await session.execute(
                text("""update public.personal_agent_tool_results
                        set result=cast(:result as jsonb)
                        where owner_id=:owner and call_id=:call and request_id=:request"""),
                {"owner": self.owner_id, "call": self.call_id,
                 "request": request_id, "result": json.dumps(outcome)},
            )
            await PersonalRepository(session, self.owner_id).activity(
                "whatsapp_submitted" if provider_id else "whatsapp_unconfirmed",
                "WhatsApp submitted to provider" if provider_id
                else "WhatsApp submission unconfirmed",
                call_id=self.call_id, followup_id=event_id,
                metadata={"message_id": str(message_id)},
            )
        return outcome


@router.post("/status/{message_id}")
async def whatsapp_status(message_id: UUID, request: Request) -> Response:
    settings, config = get_settings(), get_personal_settings()
    if not (
        config.enabled and config.whatsapp_enabled and config.owner_id
        and config.registered_phone and settings.database_url
        and settings.public_backend_url and settings.twilio_auth_token
    ):
        return Response(status_code=403)
    fields = dict(parse_qsl((await request.body()).decode(), keep_blank_values=True))
    if not valid_twilio_signature(
        status_url(settings, message_id), fields,
        request.headers.get("X-Twilio-Signature"), settings.twilio_auth_token,
    ):
        return Response(status_code=403)
    sid = fields.get("MessageSid", "")
    incoming = fields.get("MessageStatus", "")
    if not (
        sid.startswith("SM") or sid.startswith("MM")
    ) or incoming not in {"accepted","sending","sent","delivered","read","failed","undelivered"}:
        return Response(status_code=400)
    expected_from = TwilioWhatsAppClient._normalize_whatsapp(
        settings.twilio_whatsapp_from or ""
    )
    if (
        (fields.get("To") and fields["To"] != f"whatsapp:{config.registered_phone}")
        or (fields.get("From") and fields["From"] != expected_from)
        or (fields.get("AccountSid") and fields["AccountSid"] != settings.twilio_account_sid)
    ):
        return Response(status_code=403)
    sessions = get_session_factory(settings.database_url)
    async with sessions.begin() as session:
        repo = PersonalRepository(session, config.owner_id)
        profile = await repo.profile(lock=True)
        result = await session.execute(
            text("""select * from public.personal_agent_messages
                    where owner_id=:owner and generation=:generation and id=:id
                    for update"""),
            {"owner": config.owner_id, "generation": profile["generation"],
             "id": message_id},
        )
        row = result.mappings().one_or_none()
        if (
            row is None or profile["phone_e164"] != config.registered_phone
            or row["provider_message_id"] not in (None, sid)
        ):
            return Response(status_code=404)
        status = next_message_status(row["status"], incoming)
        await session.execute(
            text("""update public.personal_agent_messages
                    set provider_message_id=:sid,status=:status,
                        error_code=:error,updated_at=now()
                    where owner_id=:owner and id=:id"""),
            {"owner": config.owner_id, "id": message_id, "sid": sid,
             "status": status, "error": fields.get("ErrorCode")},
        )
        if status != row["status"]:
            if status in {"failed", "undelivered"}:
                await session.execute(
                    text("""update public.personal_agent_followups
                            set status='needs_attention',version=version+1,
                                updated_at=now()
                            where owner_id=:owner and id=:event
                            and status='awaiting_acknowledgment'
                            and call_attempts>=:maximum and version=:version"""),
                    {"owner": config.owner_id, "event": row["followup_id"],
                     "maximum": config.max_call_attempts,
                     "version": row["event_version"] + 1},
                )
            await repo.activity(
                "whatsapp_" + status, "WhatsApp delivery: " + status,
                followup_id=row["followup_id"],
                metadata={"message_id": str(message_id)},
            )
    return Response(status_code=204)
