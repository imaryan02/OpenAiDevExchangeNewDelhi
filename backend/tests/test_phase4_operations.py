from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.dialogue import confirmation_reply
from app.agent.tools import ToolExecutor
from app.core.config import Settings


def test_dialogue_cancellation_and_reschedule_replies() -> None:
    # English cancellation
    cancel_payload_en = {
        "ok": True,
        "status": "CANCELLED",
        "booking_reference": "GM-12345",
        "patient_name": "Aryan",
        "language": "en",
    }
    reply_en = confirmation_reply(cancel_payload_en)
    assert "GM-12345" in reply_en
    assert "Aryan" in reply_en
    assert "has been cancelled" in reply_en

    # Hindi cancellation
    cancel_payload_hi = {
        "ok": True,
        "status": "CANCELLED",
        "booking_reference": "GM-12345",
        "patient_name": "Aryan",
        "language": "hi",
    }
    reply_hi = confirmation_reply(cancel_payload_hi)
    assert "GM-12345" in reply_hi
    assert "Aryan ji ke liye" in reply_hi
    assert "cancel kar diya gaya hai" in reply_hi

    # English rescheduling
    resched_payload_en = {
        "ok": True,
        "status": "RESCHEDULED",
        "replacement_reference": "GM-99999",
        "replacement_token": 5,
        "language": "en",
    }
    reply_resched_en = confirmation_reply(resched_payload_en)
    assert "GM-99999" in reply_resched_en
    assert "token number is 5" in reply_resched_en
    assert "rescheduled" in reply_resched_en

    # Hindi rescheduling
    resched_payload_hi = {
        "ok": True,
        "status": "RESCHEDULED",
        "replacement_reference": "GM-99999",
        "replacement_token": 5,
        "language": "hi",
    }
    reply_resched_hi = confirmation_reply(resched_payload_hi)
    assert "GM-99999" in reply_resched_hi
    assert "Naya token number 5" in reply_resched_hi
    assert "reschedule ho gaya hai" in reply_resched_hi


@pytest.mark.asyncio
async def test_cancel_appointment_authorized_caller() -> None:
    org = uuid4()
    app_id = uuid4()
    session = MagicMock(spec=AsyncSession)

    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = 1

    mock_row = MagicMock()
    mock_row.mappings.return_value.one_or_none.return_value = {
        "id": app_id,
        "version": 1,
        "status": "CONFIRMED",
        "booking_reference": "GM-CANC-01",
        "token_number": 3,
        "patient_name": "Aryan Gupta",
        "doctor_name": "Dr Amit Kumar",
    }

    mock_cancelled = MagicMock()
    mock_cancelled.mappings.return_value.one.return_value = {
        "appointment_id": app_id,
        "booking_reference": "GM-CANC-01",
        "status": "CANCELLED",
        "version": 2,
    }

    session.execute = AsyncMock(side_effect=[
        MagicMock(),  # set_config
        mock_auth,    # auth_check
        mock_row,     # find_query
        mock_cancelled,  # cancel_appointment
    ])
    session.commit = AsyncMock()

    executor = ToolExecutor(
        session,
        org,
        actor_id=uuid4(),
        settings=Settings(_env_file=None),
        caller_phone_e164="+919876543210",
    )

    result = await executor.execute(
        "cancel_appointment",
        {"booking_reference": "GM-CANC-01", "reason": "Change of plans"},
    )
    assert result["ok"] is True
    assert result["status"] == "CANCELLED"
    assert result["booking_reference"] == "GM-CANC-01"
    assert result["patient_name"] == "Aryan Gupta"


@pytest.mark.asyncio
async def test_cancel_appointment_unauthorized_caller_denied() -> None:
    org = uuid4()
    session = MagicMock(spec=AsyncSession)

    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = None

    session.execute = AsyncMock(side_effect=[
        MagicMock(),  # set_config
        mock_auth,    # auth_check
    ])

    executor = ToolExecutor(
        session,
        org,
        actor_id=uuid4(),
        settings=Settings(_env_file=None),
        caller_phone_e164="+919999999999",
    )

    result = await executor.execute(
        "cancel_appointment",
        {"booking_reference": "GM-OTHER-USER", "reason": "Testing"},
    )
    assert result["ok"] is False
    assert "Access denied" in str(result["error"])


@pytest.mark.asyncio
async def test_cancel_appointment_already_cancelled_idempotent() -> None:
    org = uuid4()
    session = MagicMock(spec=AsyncSession)

    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = 1

    mock_row = MagicMock()
    mock_row.mappings.return_value.one_or_none.return_value = {
        "id": uuid4(),
        "version": 2,
        "status": "CANCELLED",
        "booking_reference": "GM-ALREADY-CANCELLED",
        "token_number": None,
        "patient_name": "Aryan",
        "doctor_name": "Dr Amit Kumar",
    }

    session.execute = AsyncMock(side_effect=[
        MagicMock(),
        mock_auth,
        mock_row,
    ])

    executor = ToolExecutor(
        session,
        org,
        actor_id=uuid4(),
        settings=Settings(_env_file=None),
        caller_phone_e164="+919876543210",
    )

    result = await executor.execute(
        "cancel_appointment",
        {"booking_reference": "GM-ALREADY-CANCELLED"},
    )
    assert result["ok"] is True
    assert result.get("already_cancelled") is True
    assert result["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_reschedule_appointment_same_session_idempotent() -> None:
    org = uuid4()
    session_id = uuid4()
    slot_id = None
    session = MagicMock(spec=AsyncSession)

    mock_row = MagicMock()
    mock_row.mappings.return_value.one_or_none.return_value = {
        "id": uuid4(),
        "version": 1,
        "status": "CONFIRMED",
        "booking_reference": "GM-SAME-SESSION",
        "session_id": session_id,
        "slot_id": slot_id,
        "assignment_id": uuid4(),
        "patient_name": "Sunita",
        "doctor_name": "Dr Sweta Gupta",
    }

    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = 1

    session.execute = AsyncMock(side_effect=[
        MagicMock(),
        mock_row,
        mock_auth,
    ])

    executor = ToolExecutor(
        session,
        org,
        actor_id=uuid4(),
        settings=Settings(_env_file=None),
        caller_phone_e164="+919876543210",
    )

    result = await executor.execute(
        "reschedule_appointment",
        {"booking_reference": "GM-SAME-SESSION", "new_session_id": str(session_id)},
    )
    assert result["ok"] is True
    assert result.get("already_scheduled") is True
    assert "already scheduled" in str(result["message"])


@pytest.mark.asyncio
async def test_reschedule_appointment_cutoff_passed_rejected() -> None:
    org = uuid4()
    old_session_id = uuid4()
    new_session_id = uuid4()
    session = MagicMock(spec=AsyncSession)

    mock_row = MagicMock()
    mock_row.mappings.return_value.one_or_none.return_value = {
        "id": uuid4(),
        "version": 1,
        "status": "CONFIRMED",
        "booking_reference": "GM-OLD-SESSION",
        "session_id": old_session_id,
        "slot_id": None,
        "assignment_id": uuid4(),
        "patient_name": "Sunita",
        "doctor_name": "Dr Sweta Gupta",
    }

    mock_auth = MagicMock()
    mock_auth.scalar_one_or_none.return_value = 1

    mock_target = MagicMock()
    mock_target.mappings.return_value.one_or_none.return_value = {
        "id": new_session_id,
        "starts_at": datetime.now(UTC) + timedelta(minutes=10),
        "ends_at": datetime.now(UTC) + timedelta(hours=2),
        "status": "SCHEDULED",
        "booking_mode": "SESSION_TOKEN",
        "max_patients": 20,
        "booking_cutoff_minutes": 30,
        "assignment_id": uuid4(),
        "doctor_name": "Dr Sweta Gupta",
    }

    session.execute = AsyncMock(side_effect=[
        MagicMock(),
        mock_row,
        mock_auth,
        mock_target,
    ])

    executor = ToolExecutor(
        session,
        org,
        actor_id=uuid4(),
        settings=Settings(_env_file=None),
        caller_phone_e164="+919876543210",
    )

    result = await executor.execute(
        "reschedule_appointment",
        {"booking_reference": "GM-OLD-SESSION", "new_session_id": str(new_session_id)},
    )
    assert result["ok"] is False
    assert "cutoff" in str(result["error"]).lower()
