import json
import math
import struct

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.integrations.openai_audio import SPEECH_INSTRUCTIONS, OpenAIAudioClient
from app.voice.codec import pcm24k_to_alaw8k
from app.voice.voicelink_gateway import VoiceLinkVoiceGateway


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["gpt-4o-mini-tts", "tts-1", "tts-1-hd"])
async def test_buffered_and_streamed_speech_use_same_profile_and_keep_full_text(model: str) -> None:
    observed = []
    text = "Doctor Amit kal available hain. " * 35 + "Kya yeh samay theek hai?"
    settings = Settings.model_construct(openai_api_key="test", openai_tts_model=model)

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(json.loads(request.content))
        return httpx.Response(200, content=b"\x00" * 960)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        audio = OpenAIAudioClient(settings, client)
        await audio.synthesize_alaw(text)
        gateway = VoiceLinkVoiceGateway(settings, audio)
        assert b"".join([c async for c in gateway._stream_text_alaw(text)])

    assert len(observed) == 2  # one request per reply, even with multiple sentences
    assert observed[0] == observed[1]
    assert observed[0]["input"] == text  # no old 900-character truncation
    assert observed[0]["speed"] == 0.95
    assert observed[0]["response_format"] == "pcm"
    if model == "gpt-4o-mini-tts":
        assert observed[0]["instructions"] == SPEECH_INSTRUCTIONS
    else:
        assert "instructions" not in observed[0]


@pytest.mark.asyncio
async def test_speech_errors_are_not_swallowed_and_long_readbacks_are_not_truncated() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    settings = Settings.model_construct(openai_api_key="test")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        audio = OpenAIAudioClient(settings, client)
        gateway = VoiceLinkVoiceGateway(settings, audio)
        with pytest.raises(ApiError):
            _ = [c async for c in gateway._stream_text_alaw("First sentence. Second sentence.")]
        with pytest.raises(ApiError):
            await audio.synthesize_alaw("x" * 4097)


@pytest.mark.asyncio
async def test_cached_speech_isolated_by_voice_speed_model_and_clinic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(VoiceLinkVoiceGateway, "_filler_cache", {})
    observed = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(json.loads(request.content))
        return httpx.Response(200, content=b"\x00" * 960)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for overrides in [{}, {"openai_tts_speed": 0.9}, {"openai_tts_voice": "nova"},
                          {"openai_tts_model": "tts-1"}, {"voice_organization_id": "other"}]:
            settings = Settings.model_construct(openai_api_key="test", **overrides)
            gateway = VoiceLinkVoiceGateway(settings, OpenAIAudioClient(settings, client))
            first = await gateway._get_filler_audio("Namaste. How can I help?")
            assert first == await gateway._get_filler_audio("Namaste. How can I help?")
    assert len(observed) == 5


@pytest.mark.asyncio
async def test_streaming_resampling_preserves_duration_and_samples_across_network_boundaries() -> None:
    # One second of a 440-Hz tone: odd network boundaries must not shift PCM alignment.
    pcm = b"".join(struct.pack("<h", round(10000 * math.sin(2 * math.pi * 440 * i / 24000)))
                   for i in range(24000))

    class FragmentedPCM(httpx.AsyncByteStream):
        async def __aiter__(self):
            for offset in range(0, len(pcm), 137):
                yield pcm[offset:offset + 137]

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=FragmentedPCM())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        audio = OpenAIAudioClient(Settings.model_construct(openai_api_key="test"), client)
        streamed = b"".join([c async for c in audio.stream_synthesize_alaw("Test.")])
    assert len(streamed) == 8000
    assert streamed == pcm24k_to_alaw8k(pcm)
