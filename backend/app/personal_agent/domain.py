"""Small deterministic contracts; provider lifecycle does not resolve personal work."""

from datetime import UTC, datetime
from typing import Literal

EventStatus = Literal[
    "pending",
    "scheduled",
    "in_progress",
    "awaiting_acknowledgment",
    "resolved",
    "cancelled",
    "needs_attention",
]
FINAL_EVENTS = frozenset({"resolved", "cancelled"})
FINAL_CALLS = frozenset({"completed", "busy", "no-answer", "failed", "canceled"})
MESSAGE_RANK = {
    "queued": 0,
    "accepted": 1,
    "sending": 2,
    "sent": 3,
    "delivered": 4,
    "read": 5,
    "failed": 4,
    "undelivered": 4,
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def next_message_status(current: str, incoming: str) -> str:
    """Late/duplicate callbacks cannot regress delivered evidence or retry failures."""
    if incoming not in MESSAGE_RANK:
        return current
    if current in {"delivered", "read"} and incoming in {"failed", "undelivered"}:
        return current
    if current in {"failed", "undelivered"} and incoming not in {"delivered", "read"}:
        return current
    return incoming if MESSAGE_RANK[incoming] >= MESSAGE_RANK.get(current, -1) else current
