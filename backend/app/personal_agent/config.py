from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PersonalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"), env_prefix="PERSONAL_AGENT_", extra="ignore"
    )
    enabled: bool = False
    owner_id: UUID | None = None
    registered_phone: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{7,14}$")
    outbound_enabled: bool = False
    callback_provider: Literal["voicelink", "twilio"] = "twilio"
    voicelink_api_token: str | None = None
    whatsapp_enabled: bool = False
    demo_controls_enabled: bool = False
    worker_interval_seconds: float = Field(default=1, ge=0.25, le=10)
    scheduler_enabled: bool = False
    lease_seconds: int = Field(default=120, ge=30, le=600)
    max_lateness_seconds: int = Field(default=900, ge=60, le=86400)
    retry_seconds: int = Field(default=300, ge=30, le=3600)
    memory_days: int = Field(default=7, ge=1, le=30)
    max_call_attempts: int = Field(default=2, ge=1, le=3)
    max_call_seconds: int = Field(default=600, ge=60, le=1800)
    whatsapp_content_sid: str | None = None


@lru_cache
def get_personal_settings() -> PersonalSettings:
    return PersonalSettings()
