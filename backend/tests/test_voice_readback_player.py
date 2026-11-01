import asyncio
import base64

import pytest

from app.voice.readback import PlaybackStatus, ReadbackPlaybackLedger
from app.voice.readback_player import ControlledReadbackPlayer
from app.voice.session import CallStateError


@pytest.mark.asyncio
async def test_readback_player_sends_isolated_media_and_matching_mark() -> None:
    sent: list[dict[str, object]] = []

    class Audio:
        async def synthesize_alaw(self, text: str) -> bytes:
            assert text == "Please confirm the appointment."
            return b"a" * 320

    async def send(payload: dict[str, object]) -> None:
        sent.append(payload)

    player = ControlledReadbackPlayer(ReadbackPlaybackLedger(), Audio())
    segment = await player.play(
        proposal_id="proposal-1", text="Please confirm the appointment.", send=send
    )
    acknowledged = player.acknowledge(segment.id)

    media = [item for item in sent if item["event"] == "media"]
    assert len(media) == 2
    assert base64.b64decode(media[0]["media"]["payload"]) == b"a" * 160  # type: ignore[index]
    assert sent[-1] == {"event": "mark", "mark": {"name": segment.id}}
    assert acknowledged.status == PlaybackStatus.ACKNOWLEDGED


@pytest.mark.asyncio
async def test_readback_player_does_not_leave_failed_tts_segment_authorizable() -> None:
    class Audio:
        async def synthesize_alaw(self, text: str) -> bytes:
            raise RuntimeError("provider unavailable")

    async def send(payload: dict[str, object]) -> None:
        return None

    player = ControlledReadbackPlayer(ReadbackPlaybackLedger(), Audio())
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await player.play(proposal_id="proposal-1", text="Please confirm.", send=send)
    with pytest.raises(CallStateError, match="stale or invalid"):
        player.acknowledge("readback-missing")


@pytest.mark.asyncio
async def test_interruption_during_synthesis_sends_no_audio_or_mark() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    sent = []

    class Audio:
        async def synthesize_alaw(self, text):
            entered.set()
            await release.wait()
            return b"a" * 320

    async def send(payload):
        sent.append(payload)

    player = ControlledReadbackPlayer(ReadbackPlaybackLedger(), Audio())
    task = asyncio.create_task(player.play(proposal_id="p", text="details", send=send))
    await entered.wait()
    player.interrupt()
    release.set()
    with pytest.raises(CallStateError):
        await task
    assert sent == []


@pytest.mark.asyncio
async def test_cancellation_invalidates_and_fast_mark_ack_is_accepted() -> None:
    ledger = ReadbackPlaybackLedger()

    class Audio:
        async def synthesize_alaw(self, text):
            return b"a" * 160

    player = ControlledReadbackPlayer(ledger, Audio())
    registered = []

    async def send(payload):
        if payload["event"] == "mark":
            assert registered == [payload["mark"]["name"]]
            player.acknowledge(registered[0])

    segment = await player.play(proposal_id="p", text="details", send=send, on_prepared=registered.append)
    assert ledger.is_acknowledged(segment.id, proposal_id="p")
