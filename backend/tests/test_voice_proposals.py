import pytest

from app.voice.proposals import booking_proposal
from app.voice.session import CallStateError


def test_booking_proposal_never_exposes_the_signed_offer_token() -> None:
    result = {
        "ok": True,
        "offer_token": "private-signed-token",
        "offer": {
            "patient_name": "Aryan", "doctor_name": "Dr Amit", "location_name": "Main",
            "session_date": "Tuesday", "session_time": "5 PM IST", "fee_minor": 50000,
            "currency": "INR", "payment_method": "CASH", "language": "en-IN",
        },
    }
    proposal = booking_proposal(result)

    assert "private-signed-token" not in proposal.readback_text
    assert proposal.version != "private-signed-token"
    assert "Aryan" in proposal.readback_text


def test_booking_proposal_rejects_failed_or_incomplete_offer() -> None:
    with pytest.raises(CallStateError):
        booking_proposal({"ok": False})
