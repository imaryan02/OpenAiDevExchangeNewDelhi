from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.routes import me as me_route
from app.core.config import get_settings
from app.main import create_app
from app.repositories.memberships import Membership
from app.security.auth import Principal, get_current_principal


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_liveness_has_correlation_id() -> None:
    client = TestClient(create_app())
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "detail": None}
    assert response.headers["X-Correlation-ID"]


def test_readiness_reports_unconfigured_database() -> None:
    client = TestClient(create_app())
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "detail": "database_not_configured"}


def test_me_requires_a_bearer_token() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/me")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_me_returns_the_authenticated_principal_without_a_database() -> None:
    app = create_app()
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=UUID("11111111-1111-1111-1111-111111111111"),
        email="staff@example.com",
    )
    client = TestClient(app)

    response = client.get("/v1/me")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "email": "staff@example.com",
        "memberships": [],
    }


def test_me_serializes_an_active_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = UUID("11111111-1111-1111-1111-111111111111")
    organization_id = UUID("22222222-2222-2222-2222-222222222222")

    async def fake_memberships(_: UUID) -> list[Membership]:
        return [Membership(organization_id=organization_id, role="ORG_ADMIN")]

    monkeypatch.setattr(me_route, "list_active_memberships", fake_memberships)
    app = create_app()
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id=user_id,
        email="staff@example.com",
    )

    response = TestClient(app).get("/v1/me")

    assert response.status_code == 200
    assert response.json()["memberships"] == [
        {"organization_id": str(organization_id), "role": "ORG_ADMIN"}
    ]
