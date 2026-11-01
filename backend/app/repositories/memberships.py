from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_session_factory


@dataclass(frozen=True)
class Membership:
    organization_id: UUID
    role: str


async def list_active_memberships(user_id: UUID) -> list[Membership]:
    settings = get_settings()
    if settings.database_url is None:
        return []
    session_factory = get_session_factory(settings.database_url)
    statement = text(
        """
        select organization_id, role
        from public.organization_users
        where auth_user_id = :user_id and active = true
        order by organization_id
        """
    )
    async with session_factory() as session:
        result = await session.execute(statement, {"user_id": user_id})
        return [Membership(organization_id=row.organization_id, role=row.role) for row in result]
