"""Normalize provider usage objects without copying request content."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def openai_usage_record(
    *, operation: str, model: str, request_id: str, identity_source: str,
    usage: Mapping[str, Any],
) -> dict[str, Any] | None:
    kind = usage.get("type")
    record: dict[str, Any] = {
        "operation": operation,
        "model": model,
        "request_id": request_id,
        "identity_source": identity_source,
    }
    if kind == "duration":
        seconds = usage.get("seconds")
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0:
            return {**record, "usage_type": "duration", "duration_seconds": seconds}
        return None
    if kind not in {None, "tokens"}:
        return None
    for source, target in (
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = usage.get(source)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            record[target] = value
    for section, key, target in (
        ("input_token_details", "audio_tokens", "input_audio_tokens"),
        ("input_token_details", "cached_tokens", "cached_input_tokens"),
        ("output_token_details", "audio_tokens", "output_audio_tokens"),
    ):
        details = usage.get(section)
        value = details.get(key) if isinstance(details, dict) else None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            record[target] = value
    if "input_tokens" not in record and "output_tokens" not in record:
        return None
    return {**record, "usage_type": "tokens"}
