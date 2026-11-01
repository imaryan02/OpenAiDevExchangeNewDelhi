"""Measure a synthetic VoiceLink greeting without dialing or booking an appointment."""

import argparse
import asyncio
import json
import time
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import uuid4

from websockets.asyncio.client import connect

from app.core.config import Settings


async def probe(url: str, caller: str) -> None:
    settings = Settings()
    if not settings.voicelink_stream_secret or not settings.voicelink_phone_number:
        raise SystemExit("Local VoiceLink settings are missing.")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.query or parts.fragment:
        raise SystemExit("Supply the HTTPS backend origin without a query or fragment.")
    target = urlunsplit((
        "wss", parts.netloc, "/v1/voicelink/media",
        urlencode({"token": settings.voicelink_stream_secret}), "",
    ))
    call_id = f"startup-probe-{uuid4()}"
    started = time.monotonic()
    try:
        async with connect(target, open_timeout=15, close_timeout=2) as socket:
            print(f"handshake_ms={round((time.monotonic() - started) * 1000)}", flush=True)
            await socket.send(json.dumps({"event": "start", "start": {
                "stream_sid": call_id, "call_sid": call_id, "from": caller,
                "to": settings.voicelink_phone_number,
                "media_format": {"encoding": "audio/alaw", "sample_rate": 8000},
            }}))
            deadline = time.monotonic() + 30
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                event = json.loads(await asyncio.wait_for(socket.recv(), remaining))
                if event.get("event") == "media":
                    print(f"first_audio_ms={round((time.monotonic() - started) * 1000)}")
                    print(f"call_id={call_id}")
                    await socket.send(json.dumps({"event": "stop"}))
                    return
    except Exception as error:
        # URLs contain a secret; never print the exception or request object.
        print(f"startup_failed={type(error).__name__}")
        print(f"call_id={call_id}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="HTTPS backend origin")
    parser.add_argument("--caller", default="+919800000001", help="Synthetic E.164 caller ID")
    arguments = parser.parse_args()
    asyncio.run(probe(arguments.url, arguments.caller))
