from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import ReceptionAgent
from app.api.routes.patients import require_booking_staff
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.security.auth import Principal, get_current_principal

router = APIRouter()


class AgentChatRequest(BaseModel):
    organization_id: UUID
    thread_id: UUID
    message: str = Field(min_length=1, max_length=2_000)


@router.post("/agent/chat")
async def chat_with_reception_agent(
    payload: AgentChatRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    await require_booking_staff(session, payload.organization_id, principal.user_id)
    return await ReceptionAgent(settings).respond(
        payload.message,
        session,
        payload.organization_id,
        principal.user_id,
        payload.thread_id,
    )
