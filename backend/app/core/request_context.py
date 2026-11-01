from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                structlog.get_logger().exception(
                    "unhandled_request_error",
                    method=request.method,
                    path=request.url.path,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
                response = JSONResponse(
                    status_code=500,
                    content={
                        "code": "INTERNAL_ERROR",
                        "message": "The backend could not complete this request.",
                        "correlation_id": correlation_id,
                        "details": {"error_type": type(exc).__name__},
                    },
                )
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Correlation-ID"] = correlation_id
        return response
