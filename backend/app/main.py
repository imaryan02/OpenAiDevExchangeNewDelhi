import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette import status

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import ApiError, ErrorResponse, api_error_handler
from app.core.logging import configure_logging
from app.core.request_context import CorrelationIdMiddleware
from app.services.booking_errors import translate_booking_db_error
from app.services.maintenance import run_maintenance

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    from app.observability.capture import configure
    from app.observability.telemetry import configure as configure_telemetry
    from app.observability.telemetry import shutdown as shutdown_telemetry
    capture = configure(settings.database_url)
    telemetry_provider = configure_telemetry()
    task = asyncio.create_task(run_maintenance(settings)) if settings.database_url else None
    from app.personal_agent.worker import start_worker

    personal_task = start_worker(settings)
    try:
        yield
    finally:
        if personal_task is not None:
            personal_task.cancel()
            with suppress(asyncio.CancelledError):
                await personal_task
        if capture is not None:
            await capture.stop()
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await asyncio.to_thread(shutdown_telemetry, telemetry_provider)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    app = FastAPI(title="AI Receptionist API", version="0.1.0", docs_url="/docs", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=bool(settings.cors_origins),
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    )
    app.add_exception_handler(ApiError, api_error_handler)

    @app.exception_handler(DBAPIError)
    async def booking_database_error(request: Request, exc: DBAPIError) -> JSONResponse:
        translated = translate_booking_db_error(exc)
        if translated is not None:
            return await api_error_handler(request, translated)
        logger.exception("Database operation failed for %s: %s", request.url.path, exc)
        response = ErrorResponse(
            code="DATABASE_OPERATION_FAILED",
            message="The database could not complete this operation.",
            correlation_id=getattr(request.state, "correlation_id", None),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response.model_dump(exclude_none=True),
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error for %s: %s", request.url.path, exc)
        response = ErrorResponse(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            correlation_id=getattr(request.state, "correlation_id", None),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response.model_dump(exclude_none=True),
        )

    app.include_router(api_router)
    return app


app = create_app()
