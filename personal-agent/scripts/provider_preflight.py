"""Read-only Twilio capability check. Does not dial, send messages or modify routing.

Run from repo root: .venv/Scripts/python.exe personal-agent/scripts/provider_preflight.py
Add --remote to check account/number records. Prints capability flags, never credentials.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


async def inspect(remote: bool) -> dict[str, Any]:
    from app.core.config import Settings

    settings = Settings()
    report: dict[str, Any] = {
        "twilio_credentials_present": bool(
            settings.twilio_account_sid and settings.twilio_auth_token
        ),
        "twilio_voice_number_present": bool(settings.twilio_phone_number),
        "whatsapp_sender_present": bool(settings.twilio_whatsapp_from),
        "public_voice_url_present": bool(settings.public_backend_url),
        "public_stream_url_present": bool(settings.public_websocket_url),
        "voicelink_outbound_adapter": "not_implemented",
        "actual_call_acceptance": "not_checked",
        "whatsapp_delivery": "not_checked",
        "remote_requested": remote,
    }
    if not remote or not report["twilio_credentials_present"]:
        return report
    account = settings.twilio_account_sid or ""
    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account}"
    try:
        async with httpx.AsyncClient(
            auth=(account, settings.twilio_auth_token or ""), timeout=12
        ) as client:
            response = await client.get(endpoint + ".json")
            report["account_http_status"] = response.status_code
            if response.status_code != 200:
                return report
            payload = response.json()
            report["account_active"] = payload.get("status") == "active"
            report["trial_account"] = payload.get("type") == "Trial"
            if settings.twilio_phone_number:
                numbers = await client.get(
                    endpoint + "/IncomingPhoneNumbers.json",
                    params={
                        "PhoneNumber": settings.twilio_phone_number,
                        "PageSize": 20,
                    },
                )
                report["number_lookup_http_status"] = numbers.status_code
                if numbers.status_code == 200:
                    entries = numbers.json().get("incoming_phone_numbers", [])
                    match = next(
                        (
                            entry
                            for entry in entries
                            if entry.get("phone_number") == settings.twilio_phone_number
                        ),
                        None,
                    )
                    report["twilio_number_owned"] = match is not None
                    report["twilio_number_voice_capable"] = bool(
                        match and match.get("capabilities", {}).get("voice")
                    )
                    report["existing_voicelink_number_matches_twilio_number"] = (
                        settings.voicelink_phone_number == settings.twilio_phone_number
                    )
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        report["remote_error_type"] = type(exc).__name__
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--remote", action="store_true", help="Read account and number records"
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(inspect(args.remote)), indent=2))
