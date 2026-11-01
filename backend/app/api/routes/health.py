from fastapi import APIRouter, Response, status

from app.schemas.common import HealthResponse
from app.services.health import database_is_ready

router = APIRouter()


@router.get("/health/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
async def readiness(response: Response) -> HealthResponse:
    ready, detail = await database_is_ready()
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", detail=detail)
    return HealthResponse(status="ok")
