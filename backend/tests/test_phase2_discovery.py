from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import (
    ToolExecutor,
    _match_doctor,
    _normalize_doctor_name,
)
from app.core.config import Settings


def test_doctor_name_normalization() -> None:
    assert _normalize_doctor_name("Dr. Amit Sharma") == "amit sharma"
    assert _normalize_doctor_name("Doctor   Sweta  Gupta ") == "sweta gupta"
    assert _normalize_doctor_name("डॉक्टर अमित") == "अमित"


def test_ambiguous_doctor_detection() -> None:
    available = ["Dr Amit Kumar", "Dr Amit Sharma", "Dr Sweta Gupta"]
    resolved, candidates = _match_doctor("Dr Amit", available)
    assert resolved is None
    assert "Dr Amit Kumar" in candidates
    assert "Dr Amit Sharma" in candidates

    # Unambiguous specific match
    resolved, candidates = _match_doctor("Dr Amit Sharma", available)
    assert resolved == "Dr Amit Sharma"
    assert candidates == []

    # Unambiguous single prefix match
    resolved, candidates = _match_doctor("Dr Sweta", available)
    assert resolved == "Dr Sweta Gupta"
    assert candidates == []


@pytest.mark.asyncio
async def test_search_availability_returns_ambiguous_doctor_error() -> None:
    org = uuid4()
    session = MagicMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.mappings.return_value = [
        {"display_name": "Dr Amit Kumar"},
        {"display_name": "Dr Amit Sharma"},
    ]
    session.execute = AsyncMock(return_value=mock_result)

    executor = ToolExecutor(
        session,
        org,
        actor_id=uuid4(),
        settings=Settings(_env_file=None, verification_code_pepper="test-pepper"),
    )

    now = datetime.now(UTC)
    result = await executor.execute(
        "search_availability",
        {
            "doctor_name": "Dr Amit",
            "from_at": now.isoformat(),
            "to_at": (now + timedelta(days=2)).isoformat(),
        },
    )

    assert result["ok"] is False
    assert result["error"] == "AMBIGUOUS_DOCTOR"
    assert "Dr Amit Kumar" in result["candidates"]  # type: ignore[operator]
    assert "Dr Amit Sharma" in result["candidates"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_caller_phone_binding_enforcement() -> None:
    org, actor = uuid4(), uuid4()
    session = MagicMock(spec=AsyncSession)

    bound_caller = "+919876543210"
    unauthorized_phone = "+919111111111"

    executor = ToolExecutor(
        session,
        org,
        actor_id=actor,
        settings=Settings(_env_file=None, verification_code_pepper="test-pepper"),
        caller_phone_e164=bound_caller,
    )

    # 1. lookup_caller_family with mismatch
    res1 = await executor.execute("lookup_caller_family", {"phone_e164": unauthorized_phone})
    assert res1["ok"] is False
    assert "mismatch" in str(res1["error"])

    # 2. start_phone_verification with mismatch
    res2 = await executor.execute("start_phone_verification", {"phone_e164": unauthorized_phone})
    assert res2["ok"] is False
    assert "mismatch" in str(res2["error"])

    # 3. list_upcoming_appointments with mismatch
    res3 = await executor.execute("list_upcoming_appointments", {"phone_e164": unauthorized_phone})
    assert res3["ok"] is False
    assert "mismatch" in str(res3["error"])

    # 4. prepare_booking_offer with mismatch
    res4 = await executor.execute(
        "prepare_booking_offer",
        {
            "phone_e164": unauthorized_phone,
            "patient_name": "Test Patient",
            "relationship": "SELF",
            "session_id": str(uuid4()),
        },
    )
    assert res4["ok"] is False
    assert "mismatch" in str(res4["error"])


@pytest.mark.asyncio
async def test_get_clinic_information_tool() -> None:
    org = uuid4()
    session = MagicMock(spec=AsyncSession)

    org_row = MagicMock()
    org_row.mappings.return_value.one_or_none.return_value = {
        "name": "Geeta Medicine",
        "organization_type": "CLINIC",
        "timezone": "Asia/Kolkata",
    }
    loc_row = MagicMock()
    loc_row.mappings.return_value = [{"name": "Main Branch", "address": "Civil Lines, Delhi"}]
    dept_row = MagicMock()
    dept_row.mappings.return_value = [{"name": "General Medicine"}, {"name": "Gynaecology"}]

    session.execute = AsyncMock(side_effect=[org_row, loc_row, dept_row])

    executor = ToolExecutor(
        session,
        org,
        actor_id=uuid4(),
        settings=Settings(_env_file=None, verification_code_pepper="test-pepper"),
    )

    # All topics
    info = await executor.execute("get_clinic_information", {"topic": "all"})
    assert info["ok"] is True
    assert info["clinic_name"] == "Geeta Medicine"
    assert info["timezone"] == "Asia/Kolkata"
    assert len(info["locations"]) == 1  # type: ignore[arg-type]
    assert len(info["departments"]) == 2  # type: ignore[arg-type]
    assert "CASH" in info["payment_modes"]  # type: ignore[operator]
    assert "112" in str(info["emergency_policy"])


@pytest.mark.asyncio
async def test_confirm_booking_verifies_fee_consistency() -> None:
    org, actor, patient, contact, phone, assignment, session_id = (uuid4() for _ in range(7))
    session = MagicMock(spec=AsyncSession)

    executor = ToolExecutor(
        session,
        org,
        actor_id=actor,
        settings=Settings(_env_file=None, verification_code_pepper="test-pepper"),
    )

    # Doctor assignment has changed fee from 50000 to 60000
    assignment_mock = MagicMock()
    assignment_mock.mappings.return_value.one_or_none.return_value = {
        "fee_minor": 60000,
        "currency": "INR",
    }
    session.execute = AsyncMock(return_value=assignment_mock)

    offer_payload = {
        "organization_id": str(org),
        "actor_id": str(actor),
        "patient_id": str(patient),
        "contact_id": str(contact),
        "phone_id": str(phone),
        "phone_e164": "+919876543210",
        "assignment_id": str(assignment),
        "fee_minor": 50000,
        "currency": "INR",
        "session_id": str(session_id),
        "slot_id": None,
        "payment_method": "CASH",
        "language": "hi-IN",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "nonce": "test-nonce",
    }
    token = executor._sign_offer(offer_payload)
    assert token is not None

    result = await executor.execute("confirm_booking_offer", {"offer_token": token})
    assert result["ok"] is False
    assert "fee has changed" in str(result["error"])
