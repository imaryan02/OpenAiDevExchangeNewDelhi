from fastapi import FastAPI

from app.api.routes import voice
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_voice_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    application = FastAPI(
        title="AI Receptionist Voice Gateway",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.include_router(voice.router, prefix="/v1", tags=["voice"])

    @application.get("/health/live")
    async def voice_liveness() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_voice_app()
