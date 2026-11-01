from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.main import create_app
from app.personal_agent import routes
from app.personal_agent.config import PersonalSettings, get_personal_settings
from app.personal_agent.domain import next_message_status
from app.personal_agent.repository import PersonalRepository
from app.personal_agent.schemas import ProfileInput, ReminderInput, TaskInput
from app.security.auth import Principal, get_current_principal

OWNER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")


def client(config: PersonalSettings, user: UUID | None = OWNER) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_personal_settings] = lambda: config
    app.dependency_overrides[get_settings] = lambda: Settings.model_construct(database_url=None)
    if user is not None:
        app.dependency_overrides[get_current_principal] = lambda: Principal(user, None)
    return TestClient(app)


def test_anonymous_cannot_access_personal_data() -> None:
    response = client(PersonalSettings(_env_file=None), None).get("/v1/personal-agent/tasks")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize("path", ["/profile", "/tasks", "/snapshot", "/memory", "/readiness"])
def test_other_owner_denied_before_database(path: str) -> None:
    response = client(PersonalSettings(_env_file=None, enabled=True, owner_id=OWNER), OTHER).get(
        "/v1/personal-agent" + path
    )
    assert response.status_code == 403
    assert response.json()["code"] == "PERSONAL_ACCESS_DENIED"


def test_feature_off_prevents_data_access() -> None:
    response = client(PersonalSettings(_env_file=None, owner_id=OWNER)).get(
        "/v1/personal-agent/tasks"
    )
    assert response.status_code == 503
    assert response.json()["code"] == "PERSONAL_DISABLED"


def test_readiness_distinguishes_voice_code_from_live_acceptance() -> None:
    response = client(PersonalSettings(_env_file=None)).get("/v1/personal-agent/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["current_user_id"] == str(OWNER)
    assert not data["owner_configured"]
    assert data["voice_routing_implemented"]
    assert data["callback_implemented"]
    assert not data["voicelink_outbound_configured"]
    assert not data["outbound_enabled"]
    assert not data["scheduler_enabled"]
    assert not data["provider_acceptance_verified"]


@pytest.mark.parametrize(
    "payload",
    [
        {"phone_e164": "919999999999"},
        {"phone_e164": "+09999999999"},
        {"phone_e164": "+919999999999", "timezone": "Imaginary/Timezone"},
        {"phone_e164": "+919999999999", "owner_id": str(OTHER)},
    ],
)
def test_profile_rejects_invalid_identity_and_owner_override(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ProfileInput.model_validate(payload)


def test_task_requires_aware_time_and_nonblank_title() -> None:
    with pytest.raises(ValidationError):
        TaskInput(title="   ")
    with pytest.raises(ValidationError):
        TaskInput.model_validate({"title": "Meeting", "due_at": "2026-09-28T10:00:00"})


def test_reminder_rejects_unbounded_or_instant_delays() -> None:
    for delay in (-1, 0, 9, 86401):
        with pytest.raises(ValidationError):
            ReminderInput(title="Update", delay_seconds=delay)


@pytest.mark.parametrize(
    ("current", "incoming", "expected"),
    [
        ("delivered", "sent", "delivered"),
        ("read", "failed", "read"),
        ("accepted", "delivered", "delivered"),
        ("failed", "queued", "failed"),
        ("sent", "unknown_status", "sent"),
        ("failed", "delivered", "delivered"),
    ],
)
def test_message_evidence_handles_out_of_order_callbacks(
    current: str,
    incoming: str,
    expected: str,
) -> None:
    assert next_message_status(current, incoming) == expected


@pytest.mark.asyncio
async def test_task_conflict_preserves_data_and_uses_owner() -> None:
    session = AsyncMock()
    # SQLAlchemy's result-access methods are synchronous.
    from unittest.mock import MagicMock

    session.execute.return_value = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    repo = PersonalRepository(session, OWNER)
    repo.profile = AsyncMock(return_value={})
    with pytest.raises(ApiError) as error:
        await repo.delete_task(OTHER, 3)
    assert error.value.code == "TASK_CHANGED"
    assert session.execute.await_args.args[1] == {"owner": OWNER, "id": OTHER, "version": 3}
    assert session.execute.await_count == 1


def test_failed_commit_does_not_return_success(monkeypatch: pytest.MonkeyPatch) -> None:
    session = AsyncMock()
    session.commit.side_effect = ApiError("COMMIT_FAILED", "Could not save.", 503)

    class Factory:
        def __call__(self):
            return session

    session.__aenter__.return_value = session
    monkeypatch.setattr(routes, "get_session_factory", lambda _: Factory())
    monkeypatch.setattr(
        PersonalRepository, "create_task", AsyncMock(return_value={"title": "Saved?"})
    )
    test_client = client(PersonalSettings(_env_file=None, enabled=True, owner_id=OWNER))
    test_client.app.dependency_overrides[get_settings] = lambda: Settings.model_construct(
        database_url="postgresql+asyncpg://unused"
    )
    response = test_client.post("/v1/personal-agent/tasks", json={"title": "Saved?"})
    assert response.status_code == 503
    assert response.json()["code"] == "COMMIT_FAILED"
    session.rollback.assert_awaited_once()


def test_receptionist_liveness_still_available_with_personal_disabled() -> None:
    response = client(PersonalSettings(_env_file=None)).get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
