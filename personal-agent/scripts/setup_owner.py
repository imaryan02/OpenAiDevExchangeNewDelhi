"""Register the configured Personal AI owner. Only personal tables are written.

Run from repo root with --apply. No seeds, calls or messages are created.
Existing language/timezone/fallback preferences are preserved; mode is receptionist.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


async def setup(apply: bool) -> dict[str, object]:
    from app.core.config import Settings
    from app.db.session import get_session_factory
    from app.personal_agent.config import PersonalSettings
    from app.personal_agent.repository import PersonalRepository
    from app.personal_agent.schemas import ProfileInput
    from sqlalchemy import text

    config = PersonalSettings()
    settings = Settings()
    if not config.owner_id or not config.registered_phone or not settings.database_url:
        return {"ok": False, "reason": "owner_phone_or_database_missing"}
    if not apply:
        return {
            "ok": True,
            "apply": False,
            "owner_configured": True,
            "registered_phone_configured": True,
        }
    sessions = get_session_factory(settings.database_url)
    async with sessions.begin() as session:
        owner_exists = await session.execute(
            text("select exists(select 1 from auth.users where id=:owner)"),
            {"owner": config.owner_id},
        )
        if not owner_exists.scalar_one():
            return {"ok": False, "reason": "auth_owner_not_found"}
        result = await session.execute(
            text(
                "select * from public.personal_agent_profiles where owner_id=:owner for update"
            ),
            {"owner": config.owner_id},
        )
        previous = result.mappings().one_or_none()
        repo = PersonalRepository(session, config.owner_id)
        if previous is None or previous["phone_e164"] != config.registered_phone:
            data = ProfileInput(
                phone_e164=config.registered_phone,
                timezone=previous["timezone"] if previous else "Asia/Kolkata",
                language=previous["language"] if previous else "adaptive",
                whatsapp_fallback=previous["whatsapp_fallback"] if previous else False,
            )
            await repo.save_profile(data)
        profile = await repo.profile()
        if profile["mode"] != "receptionist":
            profile = await repo.set_mode("receptionist")
    # A separate transaction verifies the saved state after commit.
    async with sessions() as session:
        saved = await PersonalRepository(session, config.owner_id).profile()
    return {
        "ok": True,
        "profile_committed": True,
        "owner_matches": saved["owner_id"] == config.owner_id,
        "phone_matches": saved["phone_e164"] == config.registered_phone,
        "mode": saved["mode"],
        "timezone": saved["timezone"],
        "whatsapp_fallback": saved["whatsapp_fallback"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        report = asyncio.run(setup(args.apply))
    except Exception as error:
        # Database/network exception messages can include connection details.
        report = {"ok": False, "error_type": type(error).__name__}
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["ok"] else 1)
