"""Run the opt-in Supabase tests after a bounded connection preflight."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings


async def preflight() -> bool:
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not configured.")
        return False
    engine = create_async_engine(url, connect_args={"timeout": 12})
    try:
        async with engine.connect() as connection:
            user_exists = (await connection.execute(
                text("select exists(select 1 from auth.users)")
            )).scalar_one()
            if not user_exists:
                print("Supabase connection succeeded, but an Auth user is required for test setup.")
                return False
        print("Supabase connection and Auth-user preflight passed.")
        return True
    except Exception as error:
        # Never print a connection URL or credential-bearing exception payload.
        print(f"Supabase connection failed: {type(error).__name__}")
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if not asyncio.run(preflight()):
        raise SystemExit(1)
    os.environ["RUN_G2_INTEGRATION_TESTS"] = "1"
    test_file = Path(__file__).resolve().parents[1] / "tests" / "test_g2_database.py"
    raise SystemExit(pytest.main([str(test_file), "-v", "-ra", "--tb=short", *sys.argv[1:]]))
