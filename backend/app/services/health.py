from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_session_factory


async def database_is_ready() -> tuple[bool, str | None]:
    settings = get_settings()
    if settings.database_url is None:
        return False, "database_not_configured"
    try:
        session_factory = get_session_factory(settings.database_url)
        async with session_factory() as session:
            await session.execute(text("select 1"))
        return True, None
    except Exception:
        pass
    return False, "database_unavailable"
