"""Bounded correlation of asynchronous caller transcripts with captured speech."""

from dataclasses import dataclass
from datetime import datetime

from app.voice.session import CallStateError


@dataclass
class CallerItem:
    item_id: str
    started_at: datetime
    stopped: bool = False
    transcript: str | None = None
    delivered: bool = False


class CallerItems:
    def __init__(self, limit: int = 256) -> None:
        self.items: dict[str, CallerItem] = {}
        self.limit = limit

    def start(self, item_id: str, at: datetime) -> None:
        if not item_id or at.tzinfo is None:
            raise CallStateError("Caller item requires identity and timestamp.")
        if item_id in self.items:
            return
        if len(self.items) >= self.limit:
            raise CallStateError("Caller item capacity exceeded.")
        self.items[item_id] = CallerItem(item_id, at)

    def stop(self, item_id: str) -> None:
        self._require(item_id).stopped = True

    def transcribe(self, item_id: str, text: str) -> None:
        item = self._require(item_id)
        if item.transcript is None:
            item.transcript = text

    def ready(self) -> list[CallerItem]:
        result = []
        for item in self.items.values():
            if item.delivered:
                continue
            if not item.stopped or item.transcript is None:
                break
            item.delivered = True
            result.append(item)
        return result

    def _require(self, item_id: str) -> CallerItem:
        if item_id not in self.items:
            raise CallStateError("Unknown caller audio item.")
        return self.items[item_id]
