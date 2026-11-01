from datetime import date, time
from typing import Any
from uuid import uuid4

import pytest

from app.api.routes.configuration import ensure_schedule_does_not_overlap
from app.core.errors import ApiError
from app.services.schedule_generation import generate_sessions


class Result:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        scalar: object | None = None,
        first: object | None = None,
    ) -> None:
        self.rows = rows or []
        self.scalar = scalar
        self.first_value = first

    def mappings(self) -> list[dict[str, Any]]:
        return self.rows

    def scalar_one_or_none(self) -> object | None:
        return self.scalar

    def first(self) -> object | None:
        return self.first_value


class FakeSession:
    def __init__(self, results: list[Result]) -> None:
        self.results = results
        self.calls: list[dict[str, Any] | None] = []

    async def execute(self, _statement: object, parameters: dict[str, Any] | None = None) -> Result:
        self.calls.append(parameters)
        return self.results.pop(0)


def stored_weekday(day: date) -> int:
    return (day.weekday() + 1) % 7


@pytest.mark.asyncio
async def test_closed_exception_suppresses_generated_session() -> None:
    target = date.today()
    assignment_id = uuid4()
    session = FakeSession(
        [
            Result(
                rows=[
                    {
                        "assignment_id": assignment_id,
                        "doctor_id": uuid4(),
                        "weekday": stored_weekday(target),
                        "local_starts_at": time(10),
                        "local_ends_at": time(12),
                        "booking_mode": "SESSION_TOKEN",
                        "slot_minutes": None,
                        "max_patients": 30,
                        "booking_cutoff_minutes": 30,
                        "effective_from": target,
                        "effective_until": None,
                        "timezone": "Asia/Kolkata",
                    }
                ]
            ),
            Result(
                rows=[
                    {
                        "assignment_id": assignment_id,
                        "local_date": target,
                        "exception_type": "CLOSED",
                        "local_starts_at": None,
                        "local_ends_at": None,
                    }
                ]
            ),
        ]
    )

    created = await generate_sessions(session, str(uuid4()), target)  # type: ignore[arg-type]

    assert created == 0
    assert len(session.calls) == 2


@pytest.mark.asyncio
async def test_replacement_hours_override_weekly_times() -> None:
    target = date.today()
    assignment_id = uuid4()
    generated_session_id = uuid4()
    session = FakeSession(
        [
            Result(
                rows=[
                    {
                        "assignment_id": assignment_id,
                        "doctor_id": uuid4(),
                        "weekday": stored_weekday(target),
                        "local_starts_at": time(10),
                        "local_ends_at": time(12),
                        "booking_mode": "SESSION_TOKEN",
                        "slot_minutes": None,
                        "max_patients": 30,
                        "booking_cutoff_minutes": 30,
                        "effective_from": target,
                        "effective_until": None,
                        "timezone": "Asia/Kolkata",
                    }
                ]
            ),
            Result(
                rows=[
                    {
                        "assignment_id": assignment_id,
                        "local_date": target,
                        "exception_type": "REPLACEMENT_HOURS",
                        "local_starts_at": time(14),
                        "local_ends_at": time(16),
                    }
                ]
            ),
            Result(scalar=generated_session_id),
        ]
    )

    created = await generate_sessions(session, str(uuid4()), target)  # type: ignore[arg-type]

    assert created == 1
    insert_parameters = session.calls[2]
    assert insert_parameters is not None
    assert insert_parameters["starts"].hour == 14
    assert insert_parameters["ends"].hour == 16


@pytest.mark.asyncio
async def test_weekly_overlap_is_rejected_before_generation() -> None:
    session = FakeSession([Result(first=(1,))])

    with pytest.raises(ApiError) as error:
        await ensure_schedule_does_not_overlap(
            session,  # type: ignore[arg-type]
            uuid4(),
            uuid4(),
            1,
            time(10),
            time(12),
            date.today(),
            None,
        )

    assert error.value.code == "SCHEDULE_OVERLAP"
