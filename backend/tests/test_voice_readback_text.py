import pytest

from app.voice.readback_text import booking_readback
from app.voice.session import CallStateError


def test_booking_readback_includes_all_critical_details_in_hinglish() -> None:
    text = booking_readback(
        {
            "patient_name": "Aryan Gupta", "doctor_name": "Dr Amit Kumar",
            "location_name": "Main Clinic", "session_date": "Tuesday, 16 September",
            "session_time": "5:00 PM to 7:00 PM IST", "fee_minor": 50000,
            "currency": "INR", "payment_method": "CASH", "language": "hi-IN",
        }
    )

    for detail in ("Aryan Gupta", "Dr Amit Kumar", "Main Clinic", "Tuesday, 16 September", "5:00 PM to 7:00 PM IST", "500 rupaye"):
        assert detail in text
    assert "Kya main ise confirm kar doon?" in text


def test_booking_readback_requires_every_critical_detail() -> None:
    with pytest.raises(CallStateError, match="missing"):
        booking_readback({"patient_name": "Aryan"})


@pytest.mark.parametrize("language", ["hi-IN", "en-IN"])
@pytest.mark.parametrize("minor,spoken", [(500, "5 rupaye"), (50000, "500 rupaye")])
def test_currency_units_do_not_change_with_language(language, minor, spoken):
    text = booking_readback({"patient_name": "Test", "doctor_name": "Doctor",
                            "location_name": "Clinic", "session_date": "Monday",
                            "session_time": "3 PM to 7 PM", "fee_minor": minor,
                            "currency": "INR", "language": language})
    assert spoken in text
