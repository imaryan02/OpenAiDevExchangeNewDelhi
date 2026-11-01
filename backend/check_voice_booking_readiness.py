"""Read-only database checks for the configured voice booking deployment."""
import asyncio
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            functions = (await connection.execute(text(
                "select proname from pg_proc join pg_namespace n on n.oid=pronamespace "
                "where n.nspname='public' and proname in "
                "('create_simulated_appointment_hold','confirm_simulated_appointment')"
            ))).scalars().all()
            actor = (await connection.execute(text(
                "select count(*) from public.organization_users "
                "where organization_id=:org and auth_user_id=:actor"
            ), {
                "org": settings.voice_organization_id, "actor": settings.voice_actor_id,
            })).scalar_one()
            constraints = (await connection.execute(text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid='public.payment_attempts'::regclass and contype='c'"
            ))).scalars().all()
            print(json.dumps({
                "database_reachable": True,
                "booking_functions": sorted(set(functions)),
                "voice_actor_membership_exists": bool(actor),
                "due_at_clinic_supported": any("DUE_AT_CLINIC" in row for row in constraints),
            }))
    except Exception as error:
        # Connection exceptions can include credentials or database endpoints.
        print(json.dumps({"check_failed": type(error).__name__}))
        raise SystemExit(1) from None
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
