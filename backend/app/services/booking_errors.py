from sqlalchemy.exc import DBAPIError

from app.core.errors import ApiError

_BOOKING_FAILURES: tuple[tuple[str, str, str], ...] = (
    (
        "explicit booking consent is required",
        "CONSENT_REQUIRED",
        "Confirm the patient, doctor, schedule, location, and fee before booking.",
    ),
    (
        "consent channel must match booking source",
        "CONSENT_SOURCE_MISMATCH",
        "The booking confirmation channel does not match its source.",
    ),
    ("session capacity is full", "SESSION_FULL", "This session has reached capacity."),
    ("new session is full", "SESSION_FULL", "This session has reached capacity."),
    ("appointments_active_exact_slot_idx", "SLOT_UNAVAILABLE", "This slot is no longer available."),
    ("new slot is unavailable", "SLOT_UNAVAILABLE", "This slot is no longer available."),
    ("booking cutoff has passed", "BOOKING_CUTOFF_PASSED", "The booking cutoff has passed."),
    (
        "idempotency key was reused with a different request",
        "IDEMPOTENCY_CONFLICT",
        "This request key was already used for different booking details.",
    ),
    (
        "appointment hold is not eligible for confirmation",
        "HOLD_EXPIRED_OR_INVALID",
        "The appointment hold expired or can no longer be confirmed.",
    ),
    (
        "appointment changed; reload before cancelling",
        "APPOINTMENT_VERSION_CONFLICT",
        "The appointment changed. Refresh it before cancelling.",
    ),
    (
        "appointment is not eligible for rescheduling",
        "RESCHEDULE_NOT_ALLOWED",
        "The appointment can no longer be rescheduled with these details.",
    ),
    (
        "replacement must differ from original appointment",
        "RESCHEDULE_SAME_OFFER",
        "Choose a different appointment time.",
    ),
    (
        "fee change requires staff review",
        "FEE_REVIEW_REQUIRED",
        "The replacement has a different fee and requires staff review.",
    ),
    (
        "appointment_sessions_doctor_time_exclusion",
        "DOCTOR_SCHEDULE_CONFLICT",
        "This doctor already has a conflicting schedule session during this time window.",
    ),
)


def translate_booking_db_error(error: DBAPIError) -> ApiError | None:
    database_message = str(error.orig).lower()
    for fragment, code, message in _BOOKING_FAILURES:
        if fragment in database_message:
            return ApiError(code=code, message=message, status_code=409)
    return None
