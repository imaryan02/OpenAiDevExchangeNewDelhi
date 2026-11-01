from datetime import UTC, datetime

import pytest

from app.voice.caller_items import CallerItems
from app.voice.session import CallStateError


def test_transcripts_delivered_once_in_speech_order_with_original_timestamp() -> None:
    items = CallerItems()
    at = datetime(2026, 9, 13, tzinfo=UTC)
    items.start("first", at)
    items.start("second", at)
    items.stop("first")
    items.stop("second")
    items.transcribe("second", "no Wednesday")
    assert items.ready() == []
    items.transcribe("first", "confirm")
    ready = items.ready()
    assert [item.item_id for item in ready] == ["first", "second"]
    assert ready[0].started_at == at
    items.transcribe("first", "duplicate")
    assert items.ready() == []


def test_unknown_items_and_overload_fail_closed() -> None:
    items = CallerItems(limit=1)
    with pytest.raises(CallStateError):
        items.transcribe("unknown", "confirm")
    items.start("first", datetime.now(UTC))
    with pytest.raises(CallStateError, match="capacity"):
        items.start("second", datetime.now(UTC))
