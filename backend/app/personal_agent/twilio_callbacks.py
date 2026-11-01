"""Twilio callbacks bound to durable Friday attempts and the registered owner."""

from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import text

from app.core.config import Settings
from app.db.session import get_session_factory
from app.personal_agent.callbacks import binding
from app.personal_agent.config import PersonalSettings
from app.personal_agent.worker import Claim, DispatchResult


def configured(settings: Settings) -> bool:
    return bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and settings.twilio_phone_number
        and settings.public_backend_url
        and settings.verification_code_pepper
        and settings.database_url
        and settings.realtime_configured
    )


class TwilioCallbacks:
    def __init__(self, settings: Settings, config: PersonalSettings):
        self.settings, self.config = settings, config

    async def dispatch(self, claim: Claim) -> DispatchResult:
        s, c = self.settings, self.config
        if not (
            configured(s)
            and c.enabled
            and c.outbound_enabled
            and c.registered_phone
            and claim.owner_id == c.owner_id
        ):
            return DispatchResult("failed", error_code="TWILIO_NOT_CONFIGURED")
        async with get_session_factory(s.database_url or "")() as session:
            destination = (
                await session.execute(
                    text("""select p.phone_e164
                from public.personal_agent_profiles p
                join public.personal_agent_followups f on f.owner_id=p.owner_id
                join public.personal_agent_attempts a
                  on a.followup_id=f.id and a.owner_id=f.owner_id
                where p.owner_id=:owner and p.generation=:generation
                and f.generation=:generation and f.id=:event and f.version=:version
                and f.lease_token=:token and f.status='in_progress'
                and a.id=:attempt and a.status='submitting'"""),
                    {
                        "owner": claim.owner_id,
                        "generation": claim.generation,
                        "event": claim.event_id,
                        "version": claim.version,
                        "token": claim.token,
                        "attempt": claim.attempt_id,
                    },
                )
            ).scalar_one_or_none()
        if destination != c.registered_phone:
            return DispatchResult("failed", error_code="OWNER_DESTINATION_CHANGED")
        base = str(s.public_backend_url).rstrip("/")
        query = urlencode({"binding": binding(s.verification_code_pepper or "", claim.attempt_id)})
        async with httpx.AsyncClient(
            auth=(s.twilio_account_sid or "", s.twilio_auth_token or ""), timeout=20
        ) as client:
            response = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Calls.json",
                data={
                    "From": s.twilio_phone_number or "",
                    "To": destination,
                    "Url": f"{base}/v1/twilio/personal-voice?{query}",
                    "Method": "POST",
                    "StatusCallback": f"{base}/v1/twilio/personal-status?{query}",
                    "StatusCallbackMethod": "POST",
                    "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
                    "Timeout": "30",
                    "TimeLimit": str(c.max_call_seconds),
                },
            )
        if 400 <= response.status_code < 500:
            return DispatchResult("failed", error_code=f"TWILIO_HTTP_{response.status_code}")
        try:
            payload: Any = response.json()
        except ValueError:
            return DispatchResult("unknown", error_code="TWILIO_RESPONSE_INVALID")
        if response.status_code != 201 or not isinstance(payload, dict) or not payload.get("sid"):
            return DispatchResult("unknown", error_code="TWILIO_ACCEPTANCE_UNCONFIRMED")
        return DispatchResult("accepted", provider_call_id=str(payload["sid"]))
