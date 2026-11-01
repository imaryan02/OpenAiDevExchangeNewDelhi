import asyncio
import base64

import pytest

from app.core.config import Settings
from app.voice.voicelink_gateway import VoiceLinkVoiceGateway


@pytest.mark.asyncio
async def test_greeting_sends_audio_before_synthesis_finishes_and_without_filler_lock() -> None:
    first_sent = asyncio.Event()
    release_synthesis = asyncio.Event()
    sent = []

    class Audio:
        async def stream_synthesize_alaw(self, text):
            yield b"\xd5" * 160
            await release_synthesis.wait()
            yield b"\xd5" * 160

    gateway = VoiceLinkVoiceGateway(Settings.model_construct(), Audio())
    gateway._stream_sid = "startup-stream"
    text = "Startup streaming regression test"
    key = gateway._speech_cache_key(text)
    gateway._filler_cache.pop(key, None)

    class Socket:
        async def send_json(self, payload):
            sent.append(payload)
            if payload["event"] == "media":
                first_sent.set()
            elif payload["event"] == "mark":
                gateway._playback_done.set()

    async with gateway._filler_lock:
        task = asyncio.create_task(gateway._play_greeting(Socket(), text))
        try:
            await asyncio.wait_for(first_sent.wait(), timeout=1)
            assert not task.done()
            assert key not in gateway._filler_cache
            release_synthesis.set()
            await asyncio.wait_for(task, timeout=1)
            assert gateway._filler_cache[key] == b"\xd5" * 320
            assert [p["event"] for p in sent] == ["media", "media", "mark"]
            assert all(p["stream_sid"] == "startup-stream" for p in sent)
            assert base64.b64decode(sent[0]["media"]["payload"]) == b"\xd5" * 160
            sent.clear()
            await gateway._play_greeting(Socket(), text)
            assert [p["event"] for p in sent] == ["media", "media", "mark"]
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            gateway._filler_cache.pop(key, None)


@pytest.mark.asyncio
async def test_failed_greeting_stream_does_not_cache_partial_audio() -> None:
    class Audio:
        async def stream_synthesize_alaw(self, text):
            yield b"\xd5" * 160
            raise TimeoutError("TTS stalled")

    class Socket:
        async def send_json(self, payload):
            pass

    gateway = VoiceLinkVoiceGateway(Settings.model_construct(), Audio())
    text = "Failed startup regression test"
    key = gateway._speech_cache_key(text)
    with pytest.raises(TimeoutError):
        await gateway._play_greeting(Socket(), text)
    assert key not in gateway._filler_cache
