import pytest

from app.voice.approval import invalidates_pending_offer, is_explicit_approval


@pytest.mark.parametrize(
    "text",
    [
        "Yes, please confirm.",
        "yes",
        "haan",
        "ji haan",
        "haan kar dijiye",
        "haan ji kar dijiye",
        "haanji kar dijiye",
        "kar dijiye",
        "Confirm it",
        "book kar do",
        "hn book kar do",
        "hn thik hai book kar do",
        "hn theek hai book kar do",
        "हाँ ठीक है बुक कर दो",
        "हां ठीक है बुक कर दो",
        "ठीक है बुक कर दो",
        "हाँ",
        "हाँ कर दीजिए",
        "हां जी कर दीजिए",
    ],
)
def test_explicit_approval_requires_clear_confirmation(text: str) -> None:
    assert is_explicit_approval(text)


@pytest.mark.parametrize("text", ["okay", "theek hai", "maybe later", "yes, but change the time"])
def test_short_or_ambiguous_reply_is_not_approval(text: str) -> None:
    assert not is_explicit_approval(text)


@pytest.mark.parametrize("text", ["no", "nahi", "doctor change karna hai", "गलत time hai"])
def test_rejection_or_correction_invalidates_pending_offer(text: str) -> None:
    assert invalidates_pending_offer(text)


@pytest.mark.parametrize("text", ["okay", "could you repeat", "awaaz nahi aayi"])
def test_unclear_reply_keeps_pending_offer_available(text: str) -> None:
    assert not invalidates_pending_offer(text)
