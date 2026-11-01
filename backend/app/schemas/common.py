from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    detail: str | None = None
