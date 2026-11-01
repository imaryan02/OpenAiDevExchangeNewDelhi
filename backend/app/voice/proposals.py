"""Convert validated appointment offers into non-secret voice proposals."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.voice.readback_text import booking_readback
from app.voice.session import CallStateError


@dataclass(frozen=True)
class BookingProposal:
    version: str
    readback_text: str


def booking_proposal(tool_result: dict[str, object]) -> BookingProposal:
    if tool_result.get("ok") is not True:
        raise CallStateError("A successful booking offer is required for a voice proposal.")
    token = tool_result.get("offer_token")
    offer = tool_result.get("offer")
    if not isinstance(token, str) or not token or not isinstance(offer, dict):
        raise CallStateError("Booking offer is incomplete.")
    typed_offer: dict[str, Any] = dict(offer)
    return BookingProposal(
        version=hashlib.sha256(token.encode()).hexdigest(),
        readback_text=booking_readback(typed_offer),
    )
