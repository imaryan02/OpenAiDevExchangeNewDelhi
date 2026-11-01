"""Place one VoiceLink outbound probe and retain its queue and callback evidence.

Dry run by default. --call creates one short-lived Friday callback for the
configured owner and prints only non-secret provider and database status.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import httpx
from sqlalchemy import text
from app.core.config import Settings
from app.db.session import get_session_factory
from app.personal_agent.config import PersonalSettings
from app.personal_agent.callbacks import ADD_LEAD_URL, binding
from app.personal_agent.worker import Claim, PersonalScheduler, DispatchResult
from app.voice.voicelink_gateway import _phone_digits


def stamp():
    return datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds")


async def dispatch_probe(settings, config, claim, destination, national_number=False,
                         omit_call_limit=False):
    destination_digits = _phone_digits(destination)
    if national_number:
        if len(destination_digits) != 12 or not destination_digits.startswith("91"):
            raise ValueError("Expected an Indian E.164 destination for the national-number probe")
        destination_digits = destination_digits[2:]
    body = {
        "did_number": _phone_digits(settings.voicelink_phone_number),
        "customer_number": destination_digits,
        "country_code": "91",
        "call_limit": 1,
        "custom_parameters": json.dumps({
            "friday_binding": binding(settings.verification_code_pepper, claim.attempt_id)
        }),
    }
    # Diagnostic only: VoiceLink's unit/meaning for this field is unverified.
    # Do not increase it: it might control retries rather than call duration.
    if omit_call_limit:
        body.pop("call_limit")
    # --national-number matches the production format; the default preserves
    # the historical 12-digit request for controlled comparisons.
    # Never print the signed binding or token.
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            ADD_LEAD_URL, json=body,
            headers={"Authorization": f"Bearer {config.voicelink_api_token}"},
        )
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    data = payload.get("data") if isinstance(payload, dict) else None
    queue_id = data.get("outbound_queue_id") if isinstance(data, dict) else None
    print(json.dumps({"time_ist": stamp(), "http_status": response.status_code,
                      "api_accepted": payload.get("status") if isinstance(payload, dict) else None,
                      "message": payload.get("message") if isinstance(payload, dict) else None,
                      "outbound_queue_id": queue_id}, default=str), flush=True)
    if response.status_code in (400, 401, 403, 404, 422):
        return DispatchResult("failed", error_code=f"VOICELINK_HTTP_{response.status_code}")
    if response.status_code >= 500 or response.status_code not in (200, 201, 202):
        return DispatchResult("unknown", error_code=f"VOICELINK_HTTP_{response.status_code}")
    if not isinstance(payload, dict):
        return DispatchResult("unknown", error_code="VOICELINK_RESPONSE_INVALID")
    if payload.get("status") is not True:
        return DispatchResult("failed", error_code="VOICELINK_LEAD_REJECTED")
    if not queue_id:
        return DispatchResult("unknown", error_code="VOICELINK_QUEUE_ID_MISSING")
    return DispatchResult("accepted")

async def main(call=False, national_number=False, inspect_event=None, omit_call_limit=False):
    settings, config = Settings(), PersonalSettings()
    print(json.dumps({"time_ist": stamp(), "number_format": "national" if national_number else "e164_digits",
        "call_limit": "provider_default" if omit_call_limit else 1,
        "enabled": config.enabled, "outbound": config.outbound_enabled,
        "scheduler": config.scheduler_enabled, "token_present": bool(config.voicelink_api_token),
        "pepper_present": bool(settings.verification_code_pepper),
        "phone": config.registered_phone, "did": settings.voicelink_phone_number}), flush=True)
    sessions = get_session_factory(settings.database_url)
    async with sessions.begin() as session:
        rows = await session.execute(text("""select f.id,f.status,f.call_attempts,f.next_action_at,
            a.status as attempt_status,a.error_code,a.provider_call_id
            from public.personal_agent_followups f left join public.personal_agent_attempts a
            on a.followup_id=f.id and a.owner_id=f.owner_id
            where f.owner_id=:owner order by f.created_at desc,a.created_at desc limit 8"""),
            {"owner":config.owner_id})
        print(json.dumps([dict(r) for r in rows.mappings()], default=str), flush=True)
        if inspect_event:
            event_id = str(UUID(inspect_event))
            calls = await session.execute(text("""select provider_call_id,direction,status,started_at,ended_at
                from public.personal_agent_calls where owner_id=:owner and followup_id=:event
                order by started_at desc"""), {"owner": config.owner_id, "event": event_id})
            events = await session.execute(text("""select event_type,description,created_at
                from public.personal_agent_events where owner_id=:owner and
                (followup_id=:event or call_id in
                 (select id from public.personal_agent_calls where owner_id=:owner and followup_id=:event))
                order by created_at desc limit 20"""), {"owner": config.owner_id, "event": event_id})
            memory = await session.execute(text("""select speaker,content,created_at
                from public.personal_agent_memory where owner_id=:owner and call_id in
                (select id from public.personal_agent_calls where owner_id=:owner and followup_id=:event)
                order by created_at"""), {"owner": config.owner_id, "event": event_id})
            print(json.dumps({"event_id": event_id,
                "calls": [dict(row) for row in calls.mappings()],
                "events": [dict(row) for row in events.mappings()],
                "memory": [dict(row) for row in memory.mappings()]}, default=str), flush=True)
        if not call:
            return
        if not config.voicelink_api_token or not settings.voicelink_phone_number:
            raise RuntimeError('VoiceLink token or DID is missing')
        if settings.voicelink_phone_number != '+919429397279':
            raise RuntimeError('VoiceLink DID does not match the authorized caller number')
        if config.registered_phone != '+918529586946':
            raise RuntimeError('Test destination does not match authorized owner')
        profile = (await session.execute(text("select generation,phone_e164 from public.personal_agent_profiles where owner_id=:owner for update"), {"owner":config.owner_id})).mappings().one()
        if profile['phone_e164'] != config.registered_phone:
            raise RuntimeError('Profile phone mismatch')
        active = (await session.execute(text("""select exists(select 1 from public.personal_agent_calls
            where owner_id=:owner and status='active' and heartbeat_at>now()-interval '60 seconds')
            or exists(select 1 from public.personal_agent_attempts a join public.personal_agent_followups f
            on f.id=a.followup_id and f.owner_id=a.owner_id where a.owner_id=:owner
            and f.status in ('in_progress','awaiting_acknowledgment')
            and a.status in ('queued','submitting','accepted','ringing','in-progress','unknown')
            and a.created_at>now()-interval '5 minutes')"""), {'owner':config.owner_id})).scalar_one()
        if active:
            raise RuntimeError('An unresolved or active callback exists; inspect before another call')
        event, attempt, token = uuid4(), uuid4(), uuid4()
        args={'owner':config.owner_id,'event':event,'attempt':attempt,'token':token,'gen':profile['generation'], 'budget':config.max_call_attempts-1}
        await session.execute(text("""insert into public.personal_agent_followups
            (id,owner_id,generation,title,context,status,call_attempts,lease_token,lease_until)
            values (:event,:owner,:gen,'Direct callback test',
            'The owner requested one direct callback test. Greet Aryan and ask whether he can hear Friday.',
            'in_progress',:budget,:token,now()+interval '120 seconds')"""),args)
        await session.execute(text("""insert into public.personal_agent_attempts
            (id,owner_id,followup_id,generation,event_version) values (:attempt,:owner,:event,:gen,1)"""),args)
    claim=Claim(config.owner_id,event,attempt,profile['generation'],1,token)
    config=config.model_copy(update={'enabled':True,'outbound_enabled':True})
    scheduler=PersonalScheduler(sessions,config,settings)
    if not await scheduler.submitting(claim):
        raise RuntimeError('Test claim could not be submitted')
    try:
        outcome=await dispatch_probe(settings,config,claim,profile['phone_e164'],national_number,
                                     omit_call_limit)
    except Exception as exc:
        # The message here identifies local probe mistakes without exposing
        # request headers, the signed binding, or provider response bodies.
        print(json.dumps({'probe_error_type': type(exc).__name__,
                          'probe_error_detail': str(exc)[:240]}), flush=True)
        outcome=DispatchResult('unknown',error_code=type(exc).__name__)
    await scheduler.finish(claim,outcome)
    print(json.dumps({'event_id':str(event),'attempt_id':str(attempt),'status':outcome.status,'error':outcome.error_code}), flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--call',action='store_true',help='Place exactly one real call to the registered owner')
    parser.add_argument('--national-number',action='store_true',
                        help='Send the 10-digit customer_number with country_code 91')
    parser.add_argument('--inspect-event',type=str,help='Read call and event evidence for one follow-up ID')
    parser.add_argument('--omit-call-limit',action='store_true',
                        help='Diagnostic: omit the undocumented call_limit field; provider defaults apply')
    args=parser.parse_args()
    asyncio.run(main(args.call,args.national_number,args.inspect_event,args.omit_call_limit))
