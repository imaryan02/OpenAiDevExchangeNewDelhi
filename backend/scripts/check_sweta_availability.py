"""Exercise the same availability tool used by chat and voice."""

import asyncio
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.agent.tools import ToolExecutor
from app.core.config import Settings
from app.db.session import get_session_factory


async def main() -> None:
    settings = Settings()
    assert settings.database_url
    assert settings.voice_organization_id
    assert settings.voice_actor_id
    zone = ZoneInfo("Asia/Kolkata")
    start = datetime(2026, 9, 11, tzinfo=zone)
    end = datetime(2026, 9, 26, tzinfo=zone)
    factory = get_session_factory(settings.database_url)
    async with factory() as session:
        result = await ToolExecutor(
            session,
            UUID(str(settings.voice_organization_id)),
            actor_id=UUID(str(settings.voice_actor_id)),
            settings=settings,
        ).execute(
            "search_availability",
            {
                "from_at": start.isoformat(),
                "to_at": end.isoformat(),
                "doctor_name": "Dr Shweta",
            },
        )
    print("ok=", result.get("ok"))
    print("matched_doctor=", result.get("matched_doctor"))
    sessions = result.get("sessions")
    print("session_count=", len(sessions) if isinstance(sessions, list) else 0)


if __name__ == "__main__":
    asyncio.run(main())
