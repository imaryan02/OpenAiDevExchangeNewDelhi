from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette import status


class ErrorResponse(BaseModel):
    code: str
    message: str
    correlation_id: str | None = None
    details: dict[str, Any] | None = None


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    response = ErrorResponse(
        code=exc.code,
        message=exc.message,
        correlation_id=getattr(request.state, "correlation_id", None),
        details=exc.details,
    )
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(exclude_none=True))
