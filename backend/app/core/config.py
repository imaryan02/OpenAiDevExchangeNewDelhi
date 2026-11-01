from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_environment: str = Field(default="development", alias="APP_ENVIRONMENT")
    app_log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    supabase_url: AnyHttpUrl | None = Field(default=None, alias="SUPABASE_URL")
    supabase_publishable_key: str | None = Field(default=None, alias="SUPABASE_PUBLISHABLE_KEY")
    supabase_jwt_audience: str = Field(default="authenticated", alias="SUPABASE_JWT_AUDIENCE")
    supabase_jwt_secret: str | None = Field(default=None, alias="SUPABASE_JWT_SECRET")
    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str | None = Field(default=None, alias="OPENAI_MODEL")
    twilio_account_sid: str | None = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_from: str | None = Field(default=None, alias="TWILIO_WHATSAPP_FROM")
    twilio_phone_number: str | None = Field(default=None, alias="TWILIO_PHONE_NUMBER")
    fallback_receptionist_number: str | None = Field(
        default=None, alias="FALLBACK_RECEPTIONIST_NUMBER"
    )
    public_backend_url: AnyHttpUrl | None = Field(default=None, alias="PUBLIC_BACKEND_URL")
    public_websocket_url: str | None = Field(default=None, alias="PUBLIC_WEBSOCKET_URL")
    voicelink_phone_number: str | None = Field(default=None, alias="VOICELINK_PHONE_NUMBER")
    voicelink_stream_secret: str | None = Field(default=None, alias="VOICELINK_STREAM_SECRET")
    voice_organization_id: UUID | None = Field(default=None, alias="VOICE_ORGANIZATION_ID")
    voice_actor_id: UUID | None = Field(default=None, alias="VOICE_ACTOR_ID")
    openai_transcription_model: str = Field(
        default="gpt-4o-mini-transcribe", alias="OPENAI_TRANSCRIPTION_MODEL"
    )
    openai_tts_model: str = Field(default="gpt-4o-mini-tts", alias="OPENAI_TTS_MODEL")
    openai_tts_voice: str = Field(default="coral", alias="OPENAI_TTS_VOICE")
    openai_tts_speed: float = Field(default=0.95, ge=0.25, le=4.0, alias="OPENAI_TTS_SPEED")
    openai_realtime_model: str = Field(
        default="gpt-realtime-2.1", alias="OPENAI_REALTIME_MODEL"
    )
    openai_realtime_voice: str = Field(default="marin", alias="OPENAI_REALTIME_VOICE")
    openai_realtime_connect_timeout_seconds: float = Field(
        default=15.0, ge=1.0, le=60.0, alias="OPENAI_REALTIME_CONNECT_TIMEOUT_SECONDS"
    )
    voice_engine: Literal["chained", "realtime"] = Field(
        default="chained", alias="VOICE_ENGINE"
    )
    presentation_enabled: bool = Field(default=False, alias="PRESENTATION_ENABLED")
    presentation_show_transcripts: bool = Field(
        default=False, alias="PRESENTATION_SHOW_TRANSCRIPTS"
    )
    voice_transcript_capture_enabled: bool = Field(
        default=False, alias="VOICE_TRANSCRIPT_CAPTURE_ENABLED"
    )
    voice_transcript_retention_days: int = Field(
        default=7, ge=1, le=90, alias="VOICE_TRANSCRIPT_RETENTION_DAYS"
    )
    hospitalos_demo_enabled: bool = Field(default=False, alias="HOSPITALOS_DEMO_ENABLED")
    presentation_demo_callers: list[str] = Field(
        default_factory=list, alias="PRESENTATION_DEMO_CALLERS"
    )
    voice_realtime_canary_callers: list[str] = Field(
        default_factory=list, alias="VOICE_REALTIME_CANARY_CALLERS"
    )
    voice_readback_ack_timeout_seconds: float = Field(
        default=30.0, ge=5.0, le=120.0, alias="VOICE_READBACK_ACK_TIMEOUT_SECONDS"
    )
    # Fallback presentation details for voice only. The active organization record is
    # preferred at call start; these values keep a carrier call usable if that lookup
    # is temporarily unavailable.
    voice_clinic_name: str | None = Field(
        default=None, max_length=120, alias="VOICE_CLINIC_NAME"
    )
    voice_pronunciation_guidance: str | None = Field(
        default=None, max_length=400, alias="VOICE_PRONUNCIATION_GUIDANCE"
    )

    @field_validator("voice_realtime_canary_callers", "presentation_demo_callers")
    @classmethod
    def validate_canary_callers(cls, callers: list[str]) -> list[str]:
        for caller in callers:
            if not (caller.startswith("+") and caller[1:].isascii()
                    and caller[1:].isdigit() and 8 <= len(caller[1:]) <= 15
                    and caller[1] != "0"):
                raise ValueError("Canary callers must use full E.164 phone numbers.")
        return list(dict.fromkeys(callers))

    @field_validator("voice_clinic_name", "voice_pronunciation_guidance")
    @classmethod
    def normalize_voice_prompt_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None
    voice_max_pending_turns: int = Field(
        default=8, ge=1, le=64, alias="VOICE_MAX_PENDING_TURNS"
    )
    voice_max_queued_turn_age_seconds: float = Field(
        default=15.0, ge=1.0, le=120.0, alias="VOICE_MAX_QUEUED_TURN_AGE_SECONDS"
    )
    sarvam_tool_secret: str | None = Field(default=None, alias="SARVAM_TOOL_SECRET")
    sarvam_voice_api_key: str | None = Field(default=None, alias="SARVAM_VOICE_API_KEY")
    sarvam_organization_id: UUID | None = Field(default=None, alias="SARVAM_ORGANIZATION_ID")
    sarvam_workspace_id: UUID | None = Field(default=None, alias="SARVAM_WORKSPACE_ID")
    sarvam_agent_id: str | None = Field(default=None, alias="SARVAM_AGENT_ID")
    sarvam_agent_version: int | None = Field(default=None, alias="SARVAM_AGENT_VERSION")
    sarvam_connection_id: str | None = Field(default=None, alias="SARVAM_CONNECTION_ID")
    sarvam_phone_number: str | None = Field(default=None, alias="SARVAM_PHONE_NUMBER")
    verification_code_pepper: str | None = Field(
        default=None, alias="VERIFICATION_CODE_PEPPER"
    )

    @property
    def twilio_whatsapp_configured(self) -> bool:
        return all(
            (
                self.twilio_account_sid,
                self.twilio_auth_token,
                self.twilio_whatsapp_from,
            )
        )

    @property
    def twilio_voice_configured(self) -> bool:
        return all(
            (
                self.twilio_account_sid,
                self.twilio_auth_token,
                self.twilio_phone_number,
                self.public_backend_url,
                self.public_websocket_url,
                self.voice_organization_id,
                self.voice_actor_id,
            )
        )

    @property
    def voicelink_voice_configured(self) -> bool:
        return all(
            (
                self.database_url,
                self.voicelink_phone_number,
                self.voicelink_stream_secret,
                self.voice_organization_id,
                self.voice_actor_id,
                self.verification_code_pepper,
            )
        )

    @property
    def realtime_configured(self) -> bool:
        return bool(
            self.openai_api_key
            and self.openai_realtime_model
            and self.openai_realtime_voice
        )

    @property
    def sarvam_tools_configured(self) -> bool:
        return all(
            (
                self.database_url,
                self.sarvam_tool_secret,
                self.voice_organization_id,
                self.voice_actor_id,
            )
        )

    @property
    def supabase_issuer(self) -> str | None:
        if self.supabase_url is None:
            return None
        return f"{str(self.supabase_url).rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str | None:
        issuer = self.supabase_issuer
        if issuer is None:
            return None
        return f"{issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
