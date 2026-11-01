"""Server-owned wording for consequential appointment readbacks."""

from __future__ import annotations

from typing import Any

from app.voice.session import CallStateError


def booking_readback(offer: dict[str, Any]) -> str:
    required = ("patient_name", "doctor_name", "location_name", "session_date", "session_time")
    if any(not str(offer.get(field, "")).strip() for field in required):
        raise CallStateError("Booking readback is missing a required appointment detail.")
    patient = str(offer["patient_name"]).strip()
    doctor = str(offer["doctor_name"]).strip()
    location = str(offer["location_name"]).strip()
    date = str(offer["session_date"]).strip()
    appointment_time = str(offer["session_time"]).strip()
    fee_minor = offer.get("fee_minor")
    currency = str(offer.get("currency") or "INR").strip().upper()
    payment = str(offer.get("payment_method") or "CASH").strip().upper()
    language = str(offer.get("language") or "en-IN").strip()
    fee = _format_fee(fee_minor, currency)
    hindi_payment_text = "payment clinic par hogi" if payment == "CASH" else f"payment method {payment} hoga"
    english_payment_text = "payment due at the clinic" if payment == "CASH" else f"payment method {payment}"

    if language.startswith("hi"):
        details = (
            f"{patient} ke liye {doctor} ke saath {date}, {appointment_time}, "
            f"{location} mein appointment hai"
        )
        if fee:
            details += f". Consultation fee {fee} hai aur {hindi_payment_text}."
        return f"Kripya details suniye. {details} Kya main ise confirm kar doon?"

    details = f"an appointment for {patient} with {doctor} on {date}, {appointment_time}, at {location}"
    if fee:
        details += f". The consultation fee is {fee}, with {english_payment_text}."
    return f"Please listen to the details. This is {details} Do you want me to confirm it?"


def _format_fee(value: object, currency: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, (int, float, str)):
        raise CallStateError("Booking readback fee is invalid.")
    try:
        minor = int(value)
    except (TypeError, ValueError):
        raise CallStateError("Booking readback fee is invalid.") from None
    if minor < 0:
        raise CallStateError("Booking readback fee is invalid.")
    if currency == "INR":
        rupees, paise = divmod(minor, 100)
        if paise == 0:
            return f"{rupees} rupaye"
        return f"{rupees} rupaye {paise} paise"
    return f"{currency} {minor / 100:.2f}"
