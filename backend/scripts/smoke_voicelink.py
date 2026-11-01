"""Local end-to-end smoke check for the VoiceLink greeting path."""

import asyncio
import json
from uuid import uuid4

from websockets.asyncio.client import connect

from app.core.config import Settings


async def main() -> None:
    settings = Settings()
    assert settings.voicelink_stream_secret
    assert settings.voicelink_phone_number
    call_id = str(uuid4())
    url = (
        "ws://127.0.0.1:8002/v1/voicelink/media"
        f"?token={settings.voicelink_stream_secret}"
    )
    async with connect(url, open_timeout=5) as socket:
        await socket.send(json.dumps({"event": "connected"}))
        await socket.send(
            json.dumps(
                {
                    "event": "start",
                    "start": {
                        "stream_sid": f"smoke-{call_id}",
                        "call_sid": call_id,
                        "from": "+919800000001",
                        "to": settings.voicelink_phone_number,
                        "media_format": {
                            "encoding": "audio/alaw",
                            "sample_rate": 8000,
                        },
                    },
                }
            )
        )
        while True:
            reply = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
            if reply.get("event") == "media":
                print("voicelink_greeting_media=ok")
                break
        await socket.send(json.dumps({"event": "stop"}))


if __name__ == "__main__":
    asyncio.run(main())
