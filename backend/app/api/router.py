from fastapi import APIRouter

from app.api.routes import (
    agent,
    availability,
    bookings,
    configuration,
    health,
    me,
    patients,
    presentation,
    voice,
    voice_observability,
)
from app.personal_agent.messaging import router as personal_whatsapp_router
from app.personal_agent.routes import router as personal_agent_router

api_router = APIRouter()
api_router.include_router(personal_agent_router)
api_router.include_router(personal_whatsapp_router)
api_router.include_router(presentation.router, prefix="/v1", tags=["presentation"])
api_router.include_router(health.router, tags=["health"])
api_router.include_router(me.router, prefix="/v1", tags=["identity"])
api_router.include_router(availability.router, prefix="/v1", tags=["availability"])
api_router.include_router(bookings.router, prefix="/v1", tags=["bookings"])
api_router.include_router(configuration.router, prefix="/v1/configuration", tags=["configuration"])
api_router.include_router(patients.router, prefix="/v1", tags=["patients"])
api_router.include_router(agent.router, prefix="/v1", tags=["agent"])
api_router.include_router(voice.router, prefix="/v1", tags=["voice"])
api_router.include_router(voice_observability.router, prefix="/v1", tags=["voice observability"])
