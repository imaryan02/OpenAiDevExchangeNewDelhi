from fastapi import FastAPI

from app.api.routes import presentation, voice
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_voicelink_app() -> FastAPI:
    """Build the minimal public app used by the VoiceLink media tunnel."""
    settings = get_settings()
    configure_logging(settings.app_log_level)
    application = FastAPI(
        title="AI Receptionist VoiceLink Gateway",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.include_router(voice.router, prefix="/v1", tags=["voice"])
    application.include_router(presentation.router, prefix="/v1", tags=["presentation"])

    @application.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_voicelink_app()
