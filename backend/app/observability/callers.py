"""Caller identity validation; never accept arbitrary carrier payload as a number."""
import re


def valid_caller_number(value: str | None) -> str | None:
    return value if value and re.fullmatch(r"\+[1-9][0-9]{7,14}", value) else None


def phone_search_digits(value: str) -> str:
    if not value.strip():
        return ""
    if not re.fullmatch(r"[+\d\s().-]+", value):
        raise ValueError("Use a phone number with at least 4 digits.")
    digits = re.sub(r"\D", "", value)
    if not 4 <= len(digits) <= 15:
        raise ValueError("Use 4 to 15 digits to search caller numbers.")
    return digits
