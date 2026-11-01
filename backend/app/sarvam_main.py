from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import sarvam
from app.core.config import get_settings
from app.core.errors import ApiError, ErrorResponse, api_error_handler
from app.core.logging import configure_logging


def create_sarvam_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    application = FastAPI(
        title="AI Receptionist Sarvam Tool Gateway",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.add_exception_handler(ApiError, api_error_handler)

    @application.exception_handler(Exception)
    async def unhandled_error(request: Request, _: Exception) -> JSONResponse:
        response = ErrorResponse(code="INTERNAL_ERROR", message="The tool request failed.")
        return JSONResponse(status_code=500, content=response.model_dump(exclude_none=True))

    application.include_router(sarvam.router, prefix="/v1/sarvam", tags=["sarvam"])

    @application.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_sarvam_app()
