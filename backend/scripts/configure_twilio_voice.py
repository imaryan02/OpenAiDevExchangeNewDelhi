import asyncio
import json

import httpx

from app.core.config import Settings


async def main() -> None:
    settings = Settings()
    if not settings.twilio_voice_configured:
        raise SystemExit("Voice settings are incomplete.")
    account_sid = settings.twilio_account_sid or ""
    auth_token = settings.twilio_auth_token or ""
    phone = settings.twilio_phone_number or ""
    webhook = f"{str(settings.public_backend_url).rstrip('/')}/v1/twilio/voice"
    base = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
    async with httpx.AsyncClient(auth=(account_sid, auth_token), timeout=20) as client:
        lookup = await client.get(
            f"{base}/IncomingPhoneNumbers.json",
            params={"PhoneNumber": phone, "PageSize": "20"},
        )
        lookup.raise_for_status()
        records = lookup.json().get("incoming_phone_numbers", [])
        matches = [item for item in records if item.get("phone_number") == phone]
        if len(matches) != 1:
            raise SystemExit("Configured Twilio phone number was not found exactly once.")
        phone_sid = str(matches[0]["sid"])
        update = await client.post(
            f"{base}/IncomingPhoneNumbers/{phone_sid}.json",
            data={"VoiceUrl": webhook, "VoiceMethod": "POST"},
        )
        update.raise_for_status()
        configured = update.json()
    print(
        json.dumps(
            {
                "twilio_voice_webhook_configured": configured.get("voice_url") == webhook,
                "voice_method": configured.get("voice_method"),
                "phone_last_four": phone[-4:],
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
