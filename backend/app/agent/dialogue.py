"""Small deterministic rules for consequential parts of a spoken conversation."""

import re
import unicodedata
from typing import Any

from langchain_core.messages import AnyMessage


def caller_utterance(messages: list[AnyMessage]) -> str:
    latest = next((m for m in reversed(messages) if m.type == "human"), None)
    if latest is None or not isinstance(latest.content, str):
        return ""
    # Compatibility with the existing voice adapter's transcript envelope.
    content = latest.content.strip()
    if content.startswith("Caller said:"):
        return content.removeprefix("Caller said:").strip()
    if content.startswith(("[Voice call started.", "[Trusted voice")):
        return content.split("\nCaller said:", 1)[-1].strip()
    return content


def explicit_confirmation(
    messages: list[AnyMessage],
    offer: dict[str, Any] | None = None,
) -> bool:
    utterance = caller_utterance(messages)
    if "?" in utterance:
        return False
    normalized = unicodedata.normalize("NFC", utterance.casefold())
    normalized = re.sub(r"[^\w\s\u0900-\u097f]", " ", normalized)
    normalized = " ".join(normalized.split())
    # A caller can repeat the already-selected name while accepting. Only remove
    # exact names from the server's active offer; a different name stays unaccepted.
    for field in ("doctor_name", "patient_name"):
        name = str((offer or {}).get(field) or "").casefold()
        name = " ".join(re.sub(r"[^\w\s\u0900-\u097f]", " ", name).split())
        if name:
            normalized = re.sub(
                rf"(?<!\w)(?:for\s+)?{re.escape(name)}(?:\s+(?:ka|ke liye|ke saath))?(?!\w)",
                " ",
                normalized,
            )
    words = normalized.split()
    vocatives = {"sir", "maam", "madam", "mam", "bhaiya", "bhai", "didi", "sahab", "saheb"}
    normalized = " ".join(word for word in words if word not in vocatives)
    # Full utterance matching deliberately excludes extra patient/date/name clauses.
    english = (
        r"(?:(?:yes|yeah|yep|okay|ok|sure|done)\s+)?"
        r"(?:please\s+)?(?:you can\s+)?"
        r"(?:confirm(?:\s+(?:it|booking|the appointment|the booking))?"
        r"|book (?:it|the appointment)|proceed(?: with the booking)?|go ahead|do it)"
    )
    if re.fullmatch(english, normalized):
        return True
    if normalized in {
        "yes",
        "yeah",
        "yep",
        "yes please",
        "sure",
        "okay",
        "ok",
        "yes okay",
        "yes ok",
        "haan",
        "han",
        "ha",
        "haanji",
        "haan ji",
        "ji haan",
        "ji",
        "bilkul",
        "haan bilkul",
        "haanji bilkul",
        "theek hai",
        "thik hai",
        "theek hai ji",
        "thik hai ji",
        "sahi hai",
        "chalega",
        "हाँ",
        "हां",
        "जी हाँ",
        "जी हां",
        "हाँ जी",
        "हां जी",
        "जी",
        "बिलकुल",
        "बिल्कुल",
        "ठीक है",
        "सही है",
    }:
        return True
    hinglish = (
        r"(?:(?:haan(?: ji)?|haanji|ji haan|bilkul|haan bilkul|haanji bilkul|"
        r"theek hai(?: ji)?|thik hai(?: ji)?|sahi hai)\s+)?"
        r"(?:please\s+|kripya\s+)?(?:booking\s+)?(?:book\s+|confirm\s+)?"
        r"(?:kar|kr) (?:do|dijiye|dijie|dena)"
    )
    hindi = (
        r"(?:(?:जी हाँ|जी हां|हाँ जी|हां जी|हाँ|हां|ठीक है|बिलकुल|बिल्कुल)\s+)?"
        r"(?:बुक\s+|कन्फर्म\s+|कंफर्म\s+)?कर (?:दीजिए|दीजिये|दो)"
    )
    return bool(re.fullmatch(hinglish, normalized) or re.fullmatch(hindi, normalized))


def offer_readback(offer: dict[str, Any]) -> str | None:
    required = ("patient_name", "doctor_name", "location_name", "session_date", "session_time")
    if not all(offer.get(field) for field in required):
        return None
    hindi = str(offer.get("language", "en")).startswith("hi")
    patient, doctor, location, day, window = (str(offer[field]) for field in required)
    token_mode = offer.get("booking_mode") in {"SESSION_WINDOW", "SESSION_TOKEN"}
    if hindi:
        timing = "Yeh token session hai, exact consultation time nahi. " if token_mode else ""
        return (
            f"{patient} ji ke liye {doctor}, {location}, {day}, {window}. "
            f"{timing}Kya main yeh appointment confirm kar doon?"
        )
    timing = "This is a token session, not an exact consultation time. " if token_mode else ""
    return (
        f"For {patient}, with {doctor} at {location}, {day}, {window}. "
        f"{timing}Shall I confirm this appointment?"
    )


def confirmation_reply(payload: dict[str, Any]) -> str:
    hindi = str(payload.get("language", "en")).startswith("hi")
    if payload.get("ok") is not True:
        return (
            "Abhi booking confirm nahi ho paayi. Ek baar availability dobara check karein?"
            if hindi
            else "I could not confirm that booking. Shall I check availability again?"
        )
    if payload.get("status") == "CANCELLED":
        reference = str(payload.get("booking_reference") or "").strip()
        patient = str(payload.get("patient_name") or "").strip()
        if hindi:
            patient_txt = f" ({patient} ji ke liye)" if patient else ""
            return f"Aapka appointment {reference}{patient_txt} cancel kar diya gaya hai."
        patient_txt = f" for {patient}" if patient else ""
        return f"Your appointment {reference}{patient_txt} has been cancelled."
    if payload.get("status") == "RESCHEDULED" or payload.get("replacement_reference"):
        reference = str(payload.get("replacement_reference") or "").strip()
        token = payload.get("replacement_token")
        if hindi:
            token_text = f" Naya token number {token} hai." if token is not None else ""
            return f"Aapka appointment reschedule ho gaya hai.{token_text} Naya booking reference {reference} hai."
        token_text = f" Your new token number is {token}." if token is not None else ""
        return f"Your appointment has been rescheduled.{token_text} New booking reference is {reference}."
    reference = str(payload.get("booking_reference") or "").strip()
    if not reference or payload.get("status") != "CONFIRMED":
        return (
            "Booking ka result verify nahi ho paaya. Kripya reception se check kar lein."
            if hindi
            else "I could not verify the booking result. Please check with reception."
        )
    token = payload.get("token_number")
    if hindi:
        token_text = f" Aapka token number {token} hai." if token is not None else ""
        return f"Aapki appointment confirm ho gayi hai.{token_text} Booking reference {reference}."
    token_text = f" Your token number is {token}." if token is not None else ""
    return f"Your appointment is confirmed.{token_text} Booking reference {reference}."
