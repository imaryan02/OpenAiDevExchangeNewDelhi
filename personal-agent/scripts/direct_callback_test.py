"""Inspect callbacks, or submit one owner-authorized direct VoiceLink test."""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from sqlalchemy import text
from app.core.config import Settings
from app.db.session import get_session_factory
from app.personal_agent.config import PersonalSettings
from app.personal_agent.callbacks import VoiceLinkCallbacks
from app.personal_agent.worker import Claim, PersonalScheduler, DispatchResult

async def main(call=False):
    settings, config = Settings(), PersonalSettings()
    print(json.dumps({"enabled": config.enabled, "outbound": config.outbound_enabled,
        "scheduler": config.scheduler_enabled, "token_present": bool(config.voicelink_api_token),
        "pepper_present": bool(settings.verification_code_pepper),
        "phone": config.registered_phone, "did": settings.voicelink_phone_number}))
    sessions = get_session_factory(settings.database_url)
    async with sessions.begin() as session:
        rows = await session.execute(text("""select f.id,f.status,f.call_attempts,f.next_action_at,
            a.status as attempt_status,a.error_code,a.provider_call_id
            from public.personal_agent_followups f left join public.personal_agent_attempts a
            on a.followup_id=f.id and a.owner_id=f.owner_id
            where f.owner_id=:owner order by f.created_at desc,a.created_at desc limit 8"""),
            {"owner":config.owner_id})
        print(json.dumps([dict(r) for r in rows.mappings()], default=str))
        if not call:
            return
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
            and a.status in ('queued','submitting','accepted','ringing','in-progress','unknown'))"""), {'owner':config.owner_id})).scalar_one()
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
        outcome=await VoiceLinkCallbacks(settings,config).dispatch(claim)
    except Exception as exc:
        outcome=DispatchResult('unknown',error_code=type(exc).__name__)
    await scheduler.finish(claim,outcome)
    print(json.dumps({'event_id':str(event),'attempt_id':str(attempt),'status':outcome.status,'error':outcome.error_code}))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--call',action='store_true',help='Place exactly one real call to the registered owner')
    asyncio.run(main(parser.parse_args().call))
