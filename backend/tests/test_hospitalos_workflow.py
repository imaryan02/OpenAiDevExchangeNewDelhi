from app.hospitalos.workflow import capacity_available, token_hash


def test_tracking_token_is_hashed_without_storing_plaintext() -> None:
    token = "a" * 43
    assert token_hash(token) != token
    assert len(token_hash(token)) == 64
    assert token_hash(token) == token_hash(token)


def test_atomic_hold_capacity_math() -> None:
    assert capacity_available(ed_ready=2, icu_ready=1, ed_held=1, icu_held=0, needs_icu=True)
    assert not capacity_available(ed_ready=2, icu_ready=1, ed_held=2, icu_held=0, needs_icu=False)
    assert not capacity_available(ed_ready=2, icu_ready=1, ed_held=1, icu_held=1, needs_icu=True)
    assert capacity_available(ed_ready=2, icu_ready=1, ed_held=1, icu_held=1, needs_icu=False)
