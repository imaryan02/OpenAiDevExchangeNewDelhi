import asyncio

import httpx

from app.core.config import Settings
from app.voice.security import twilio_signature


async def main() -> None:
    settings = Settings()
    if not settings.twilio_voice_configured or not settings.twilio_auth_token:
        raise SystemExit("Voice settings are incomplete.")
    url = f"{str(settings.public_backend_url).rstrip('/')}/v1/twilio/voice"
    parameters = {
        "CallSid": "CA00000000000000000000000000000000",
        "AccountSid": settings.twilio_account_sid or "",
        "From": "+919800000001",
        "To": settings.twilio_phone_number or "",
    }
    signature = twilio_signature(url, parameters, settings.twilio_auth_token)
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            url,
            data=parameters,
            headers={"X-Twilio-Signature": signature},
        )
    response.raise_for_status()
    expected_stream = f'url="{settings.public_websocket_url}"'
    if expected_stream not in response.text or 'name="binding"' not in response.text:
        raise SystemExit("Voice webhook returned unexpected TwiML.")
    print("signed_public_voice_webhook=passed")


if __name__ == "__main__":
    asyncio.run(main())
