"""Apply only the additive caller-history migration using configured Supabase credentials.

Run from the repository root. Never prints connection strings or caller numbers.
"""
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings


async def main():
    settings = Settings()
    if not settings.database_url:
        raise RuntimeError("Database configuration is missing")
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    host = urlparse(url).hostname or ""
    if not host.endswith((".supabase.co", ".supabase.com")):
        raise RuntimeError("Configured database is not a Supabase host")
    connection = await asyncpg.connect(url, timeout=15, command_timeout=45)
    try:
        migration = ROOT / "supabase/migrations/20260927000400_voice_caller_history.sql"
        await connection.execute(migration.read_text(encoding="utf-8-sig"))
        verification = ROOT / "supabase/verification/20260927000400_voice_caller_history_checks.sql"
        for query in verification.read_text(encoding="utf-8-sig").split(";"):
            if query.strip():
                rows = await connection.fetch(query)
                for row in rows:
                    print(dict(row))
        organization = await connection.fetchval(
            "select organization_id from public.voice_observability_calls limit 1"
        )
        if organization:
            from app.api.routes.voice_observability import _list_calls
            result = await _list_calls(str(organization), 50, 0, None, None,
                                       None, None, "", "", None)
            calls = result["calls"]
            print({"call_list_query_verified": isinstance(calls, list)})
        print("Caller-history migration applied and verified.")
    finally:
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:  # noqa: BLE001 - redact credential-bearing errors
        # Exception messages can include database connection details.
        print(f"Caller-history migration could not complete ({type(error).__name__}).")
        sys.exit(1)
