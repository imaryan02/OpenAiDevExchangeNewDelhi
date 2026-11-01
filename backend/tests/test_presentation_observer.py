"""Observer regression checks: real boundaries, no payload leakage or false outcomes."""
from uuid import uuid4

import pytest

from app.agent.tools import ToolExecutor
from app.api.routes import presentation as presentation_route
from app.core.config import Settings
from app.repositories.memberships import Membership
from app.security.auth import Principal
from app.voice import presentation as p


@pytest.fixture
def scope(monkeypatch):
    store = p.PresentationStore()
    monkeypatch.setattr(p, "store", store)
    settings = Settings.model_construct(
        presentation_enabled=True, presentation_demo_callers=["+919800000001"],
        presentation_show_transcripts=False, voice_organization_id=uuid4(),
    )
    with p.presentation_scope(settings):
        p.start_call("+919800000001", "realtime")
        yield store.calls[next(iter(store.calls))]["events"]


def test_identity_and_audio_are_observed_without_phone_or_audio_payload(scope):
    p.audio_transfer("input", 160)
    p.audio_transfer("input", 160)
    p.response_fragment("Private patient detail")
    assert scope[1]["kind"] == "identity_received"
    assert "+919800000001" not in str(scope)
    assert "Private patient" not in str(scope)
    assert len([e for e in scope if e["kind"] == "audio_transferred"]) == 1


@pytest.mark.asyncio
async def test_database_wrapper_marks_actual_return_and_failure(scope):
    class Database:
        async def execute(self, statement):
            if statement == "fail":
                raise RuntimeError("private database message")
            return "result"

    executor = object.__new__(ToolExecutor)
    executor._session = Database()
    with p.tool_scope("lookup_caller_family", "backend"):
        assert await executor._query("success") == "result"
        with pytest.raises(RuntimeError):
            await executor._query("fail")
    rows = [e for e in scope if e["kind"].startswith("database_")]
    assert [e["kind"] for e in rows] == [
        "database_started", "database_completed", "database_started", "database_failed",
    ]
    assert all(e["origin"] == "backend" and e["tool"] == "lookup_caller_family" for e in rows)
    assert len({e["operation_id"] for e in rows}) == 1
    completed_rows = [e for e in rows if e["kind"] in {"database_completed", "database_failed"}]
    assert all(e["details"]["duration_ms"] >= 0 for e in completed_rows)
    assert "private database message" not in str(scope)
    assert not any(e["kind"] == "committed" for e in scope)


def test_manifest_and_selection_are_distinct_from_execution(scope):
    p.available_tools(["search_availability", "made_up_integration"])
    p.selected_tool("search_availability")
    assert scope[-2]["tools"] == ["search_availability"]
    assert scope[-1]["kind"] == "tool_selected"
    assert not any(e["kind"] == "tool_started" for e in scope)


def test_tool_arguments_are_allowlisted_for_the_live_view():
    safe = p.safe_arguments({
        "doctor_name": "Dr Sweta",
        "date": "Monday",
        "time": "10:00 AM",
        "patient_name": "Private Person",
        "phone": "+919800000001",
        "offer_token": "secret-token",
    })

    assert safe == {
        "doctor_name": "Dr Sweta",
        "session_date": "Monday",
        "session_time": "10:00 AM",
    }
    assert "Private Person" not in str(safe)
    assert "+919800000001" not in str(safe)
    assert "secret-token" not in str(safe)


def test_unenrolled_call_never_starts_trace(monkeypatch):
    store = p.PresentationStore()
    monkeypatch.setattr(p, "store", store)
    settings = Settings.model_construct(presentation_enabled=True, presentation_demo_callers=[],
                                        voice_organization_id=uuid4())
    with p.presentation_scope(settings):
        p.start_call("+919800000001", "realtime")
        p.audio_transfer("input", 160)
    assert not store.calls


@pytest.mark.asyncio
async def test_live_observer_allows_an_active_non_admin_member(monkeypatch):
    organization_id = uuid4()
    user_id = uuid4()

    async def fake_memberships(_: object) -> list[Membership]:
        return [Membership(organization_id=organization_id, role="RECEPTIONIST")]

    settings = Settings.model_construct(presentation_enabled=True)
    monkeypatch.setattr(presentation_route, "get_settings", lambda: settings)
    monkeypatch.setattr(presentation_route, "list_active_memberships", fake_memberships)

    organization = await presentation_route.authorize(
        organization_id,
        Principal(user_id=user_id, email="demo@example.com"),
    )

    assert organization == str(organization_id)


@pytest.mark.asyncio
async def test_call_list_reports_safe_capture_configuration(monkeypatch):
    organization_id = uuid4()
    settings = Settings.model_construct(
        presentation_enabled=True,
        presentation_demo_callers=["+919800000001"],
        voice_organization_id=organization_id,
    )
    monkeypatch.setattr(presentation_route, "get_settings", lambda: settings)

    response = await presentation_route.calls(str(organization_id))

    assert response["observer"] == {
        "capture_enabled": True,
        "enrolled_caller_count": 1,
        "voice_organization_matches": True,
    }
    assert "+919800000001" not in str(response)
