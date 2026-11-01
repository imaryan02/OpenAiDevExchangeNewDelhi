from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.errors import ApiError


@lru_cache
def get_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(database_url, pool_pre_ping=True, hide_parameters=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session(
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[AsyncSession, None]:
    if settings.database_url is None:
        raise ApiError(
            code="DATABASE_NOT_CONFIGURED",
            message="Database is not configured.",
            status_code=503,
        )
    session_factory = get_session_factory(settings.database_url)
    async with session_factory() as session:
        yield session
