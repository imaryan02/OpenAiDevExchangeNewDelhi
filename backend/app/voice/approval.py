"""Conservative recognition of explicit caller approval after a completed readback."""

from __future__ import annotations

import re


def _normalize(transcript: str) -> str:
    return " ".join(re.sub(r"[^\w\s\u0900-\u097f]+", " ", transcript.casefold()).split())


def is_explicit_approval(transcript: str) -> bool:
    normalized = _normalize(transcript)
    if not normalized:
        return False
    # These phrases authorize a change only after the server-owned readback has
    # fully played and VoiceLink has acknowledged its carrier mark. Keep them in
    # sync with the confirmation examples in realtime_prompt.txt.
    phrases = (
        "yes",
        "yes confirm",
        "yes please confirm",
        "please confirm",
        "confirm",
        "confirm it",
        "go ahead confirm",
        "haan",
        "haan ji",
        "haanji",
        "ji haan",
        "haan confirm",
        "haan kar dijiye",
        "haan book kar dijiye",
        "kar dijiye",
        "confirm kar dijiye",
        "haan ji confirm",
        "haan ji kar dijiye",
        "haanji kar dijiye",
        "yes please",
        "yes kar dijiye",
        "bilkul confirm",
        "bilkul kar dijiye",
        "book kar do",
        "hn book kar do",
        "hn thik hai book kar do",
        "hn theek hai book kar do",
        "ठीक है बुक कर दो",
        "ठीक है बुक कर दीजिए",
        "book kar dijiye",
        "जी हाँ",
        "जी हां",
        "हाँ",
        "हां",
        "हाँ जी",
        "हां जी",
        "हाँ कन्फर्म",
        "हां कन्फर्म",
        "हाँ कर दीजिए",
        "हां कर दीजिए",
        "हाँ जी कर दीजिए",
        "हां जी कर दीजिए",
        "बुक कर दो",
        "बुक कर दीजिए",
    )
    if normalized in phrases:
        return True

    negative_or_correction = (
        "no", "not", "don t", "do not", "nahi", "nahin", "mat", "wait", "change",
        "instead", "but", "lekin", "par", "cancel", "wrong", "galat", "badal",
        "नहीं", "नही", "मत", "रुको", "बदल", "गलत", "कैंसिल",
    )
    if any(token in normalized.split() for token in negative_or_correction):
        return False

    affirmative = ("yes", "haan", "han", "haanji", "bilkul", "हाँ", "हां")
    confirmation_action = (
        "confirm", "book", "kar dijiye", "kar do", "कन्फर्म", "बुक", "कर दीजिए", "कर दो"
    )
    return any(token in normalized.split() for token in affirmative) and any(
        action in normalized for action in confirmation_action
    )


def invalidates_pending_offer(transcript: str) -> bool:
    """Return true only for a clear rejection or correction, not an unclear reply."""
    normalized = _normalize(transcript)
    if not normalized:
        return False
    clarification_context = (
        "repeat", "again", "hear", "heard", "audio", "voice", "awaaz", "awaz", "sunai",
        "samajh", "dobara", "फिर", "दोबारा", "आवाज", "सुनाई", "समझ",
    )
    if any(marker in normalized for marker in clarification_context):
        return False
    rejection_or_correction = (
        "no", "nope", "nahi", "nahin", "mat", "wait", "change", "instead", "cancel",
        "wrong", "galat", "badal", "different", "another", "नहीं", "नही", "मत", "रुको",
        "बदल", "गलत", "कैंसिल",
    )
    words = set(normalized.split())
    return any(marker in words or marker in normalized for marker in rejection_or_correction)
