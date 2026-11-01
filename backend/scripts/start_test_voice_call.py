"""Place a Twilio trial call to a verified test phone.

Usage:
    python scripts/start_test_voice_call.py --to +91XXXXXXXXXX
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing {name} in backend/.env")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", required=True, help="Verified destination in E.164 format")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parents[1]
    load_env(backend_dir / ".env")

    account_sid = required("TWILIO_ACCOUNT_SID")
    auth_token = required("TWILIO_AUTH_TOKEN")
    from_number = required("TWILIO_PHONE_NUMBER")
    public_url = required("PUBLIC_BACKEND_URL").rstrip("/")

    body = urllib.parse.urlencode(
        {
            "To": args.to,
            "From": from_number,
            "Url": f"{public_url}/v1/twilio/voice",
            "Method": "POST",
            "StatusCallback": f"{public_url}/v1/twilio/stream-status",
            "StatusCallbackMethod": "POST",
            "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
        },
        doseq=True,
    ).encode()
    endpoint = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Authorization": f"Basic {auth}"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status == 201:
                print("Twilio accepted the call. Answer your phone to start the AI test.")
                return 0
            print(f"Twilio returned HTTP {response.status}.")
            return 1
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        print(f"Twilio rejected the call (HTTP {exc.code}): {details}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
