from sqlalchemy.exc import DBAPIError

from app.services.booking_errors import translate_booking_db_error


def database_error(message: str) -> DBAPIError:
    return DBAPIError(None, None, Exception(message), False)


def test_capacity_conflict_has_a_stable_safe_code() -> None:
    translated = translate_booking_db_error(database_error("session capacity is full"))

    assert translated is not None
    assert translated.code == "SESSION_FULL"
    assert translated.status_code == 409


def test_exact_slot_conflict_has_a_stable_safe_code() -> None:
    translated = translate_booking_db_error(
        database_error('duplicate key violates "appointments_active_exact_slot_idx"')
    )

    assert translated is not None
    assert translated.code == "SLOT_UNAVAILABLE"


def test_unknown_database_failure_is_not_misclassified() -> None:
    assert translate_booking_db_error(database_error("connection disappeared")) is None


def test_missing_consent_has_a_stable_safe_code() -> None:
    translated = translate_booking_db_error(
        database_error("explicit booking consent is required")
    )

    assert translated is not None
    assert translated.code == "CONSENT_REQUIRED"
