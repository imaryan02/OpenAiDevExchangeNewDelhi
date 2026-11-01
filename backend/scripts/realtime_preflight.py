"""Run a safe OpenAI Realtime connection/configuration check.

Run from backend: ../.venv/Scripts/python.exe scripts/realtime_preflight.py
It sends no caller audio and registers no appointment tools.
"""

import asyncio
import json

from app.core.config import Settings
from app.integrations.openai_realtime import preflight


async def main() -> None:
    result = await preflight(Settings())
    print(
        json.dumps(
            {
                "ok": True,
                "model": result.model,
                "session_id_present": result.session_id is not None,
                "voice": result.voice,
                "input_format": result.input_format,
                "output_format": result.output_format,
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
