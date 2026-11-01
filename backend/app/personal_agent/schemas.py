from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfileInput(Input):
    phone_e164: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    timezone: str = "Asia/Kolkata"
    language: Literal["adaptive", "english", "hinglish"] = "adaptive"
    whatsapp_fallback: bool = False

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Choose a valid timezone.") from exc
        return value


class ModeInput(Input):
    mode: Literal["receptionist", "personal_agent"]


class TaskInput(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def aware_time(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Include a timezone in due_at.")
        return value


class TaskUpdate(TaskInput):
    status: Literal["pending", "completed"] = "pending"
    version: int = Field(ge=1)


class ReminderInput(Input):
    title: str = Field(min_length=1, max_length=200)
    delay_seconds: int = Field(ge=10, le=86400)
    context: str = Field(default="", max_length=1000)
    task_ids: list[UUID] = Field(default_factory=list, max_length=20)


class FollowupAction(Input):
    action: Literal["acknowledge", "cancel", "reschedule"]
    version: int = Field(ge=1)
    delay_seconds: int | None = Field(default=None, ge=10, le=86400)
