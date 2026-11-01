import asyncio
from datetime import timedelta
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl

from app.api.routes import voice as voice_route
from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.integrations.openai_audio import OpenAIAudioClient
from app.main import create_app
from app.personal_agent.config import PersonalSettings
from app.security.auth import Principal
from app.voice.codec import (
    AlawTurnDetector,
    MulawTurnDetector,
    alaw_to_pcm16_sample,
    mulaw_energy,
    pcm16_sample_to_alaw,
    pcm16_sample_to_mulaw,
    pcm24k_to_alaw8k,
    pcm24k_to_mulaw8k,
)
from app.voice.security import (
    create_stream_binding,
    twilio_signature,
    valid_twilio_signature,
    verify_stream_binding,
)
from app.voice.voicelink_gateway import (
    VoiceLinkVoiceGateway,
    _is_outbound_media,
    _is_self_echo,
    _normalize_e164_phone,
    _split_sentences,
)

ORGANIZATION_ID = UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = UUID("33333333-3333-3333-3333-333333333333")


def _voice_settings() -> Settings:
    return Settings.model_construct(
        database_url="postgresql+asyncpg://unused",
        openai_api_key="openai-secret",
        openai_model="gpt-4o-mini",
        openai_transcription_model="gpt-4o-mini-transcribe",
        openai_tts_model="gpt-4o-mini-tts",
        openai_tts_voice="coral",
        twilio_account_sid="AC-test",
        twilio_auth_token="twilio-secret",
        twilio_phone_number="+18312286492",
        public_backend_url=AnyHttpUrl("https://voice.example"),
        public_websocket_url="wss://voice.example/v1/twilio/media",
        voice_organization_id=ORGANIZATION_ID,
        voice_actor_id=ACTOR_ID,
        verification_code_pepper="binding-secret",
    )


def test_mulaw_turn_detector_finalizes_speech_after_silence() -> None:
    detector = MulawTurnDetector(
        energy_threshold=100,
        min_speech_frames=3,
        end_silence_frames=3,
        preroll_frames=1,
    )
    speech = bytes([pcm16_sample_to_mulaw(5000)]) * 160
    silence = bytes([0xFF]) * 160

    assert detector.feed(speech).speech_started is True
    detector.feed(speech)
    detector.feed(speech)
    detector.feed(silence)
    detector.feed(silence)
    completed = detector.feed(silence)

    assert completed.utterance is not None
    assert mulaw_energy(silence) == 0


def test_pcm_downsampling_outputs_twilio_rate() -> None:
    one_second_pcm = (b"\x00\x00\x10\x27\x00\x00") * 8000
    assert len(pcm24k_to_mulaw8k(one_second_pcm)) == 8000


def test_alaw_codec_and_turn_detector_support_voicelink_audio() -> None:
    encoded = pcm16_sample_to_alaw(5000)
    assert abs(alaw_to_pcm16_sample(encoded) - 5000) < 500
    assert 0 <= pcm16_sample_to_alaw(-1) <= 255
    assert 0 <= pcm16_sample_to_alaw(-32768) <= 255

    one_second_pcm = (b"\x00\x00\x10\x27\x00\x00") * 8000
    assert len(pcm24k_to_alaw8k(one_second_pcm)) == 8000

    detector = AlawTurnDetector(
        energy_threshold=100,
        min_speech_frames=3,
        end_silence_frames=3,
        preroll_frames=1,
    )
    speech = bytes([encoded]) * 160
    silence = bytes([pcm16_sample_to_alaw(0)]) * 160
    assert detector.feed(speech).speech_started is True
    detector.feed(speech)
    detector.feed(speech)
    detector.feed(silence)
    detector.feed(silence)
    assert detector.feed(silence).utterance is not None


def test_voicelink_normalizes_caller_id_and_ignores_outbound_track() -> None:
    assert _normalize_e164_phone("8529586946") == "+918529586946"
    assert _normalize_e164_phone("00918529586946") == "+918529586946"
    assert _normalize_e164_phone("unknown") == ""
    assert _is_outbound_media({"media": {"track": "outbound_track"}}) is True
    assert _is_outbound_media({"media": {"track": "inbound"}}) is False
    assert _is_outbound_media({"media": {"direction": "playback"}}) is True
    assert _is_outbound_media({"media": {"source": "bot"}}) is True
    assert _is_outbound_media({}) is False


def test_voicelink_detects_and_suppresses_self_echo() -> None:
    greeting = "Namaste. Geeta Medicine mein aapka swagat hai. Main aapki appointment mein kaise madad kar sakti hoon?"
    reply = "Dr. Sweta kal shaam 5 se 7 baje uplabdh hain."
    recent = [greeting, reply]

    # Echo reflections matching recent bot speech
    assert _is_self_echo("Namaste Geeta Medicine mein aapka swagat hai", recent) is True
    assert _is_self_echo("Dr. Sweta kal shaam 5 se 7 baje uplabdh hain", recent) is True
    assert _is_self_echo("Dr Sweta kal shaam 5 se 7 baje uplabdh", recent) is True

    reply2 = "Dr. Sweta available hain aaj 9 se 10 baje ke beech. Kya aap appointment book karana chahte hain?"
    recent2 = [greeting, reply, reply2]
    assert _is_self_echo("kya aap appointment book karana chahte hain", recent2) is True
    assert _is_self_echo("appointment book karana chahte hain", recent2) is True
    assert _is_self_echo("kya appointment book karana chahte hain", recent2) is True

    # Real caller speech (never falsely suppressed)
    assert _is_self_echo("Dr Sweta se milna hai", recent2) is False
    assert _is_self_echo("Haan", recent2) is False
    assert _is_self_echo("Theek hai", recent2) is False
    assert _is_self_echo("Mujhe appointment book karana hai", recent2) is False
    assert _is_self_echo("", recent2) is False


def test_twilio_signature_and_stream_binding_reject_tampering() -> None:
    url = "https://voice.example/v1/twilio/voice"
    parameters = {"CallSid": "CA-test", "From": "+919800000001"}
    signature = twilio_signature(url, parameters, "twilio-secret")
    assert valid_twilio_signature(url, parameters, signature, "twilio-secret") is True
    assert valid_twilio_signature(url, parameters, signature + "x", "twilio-secret") is False

    binding = create_stream_binding(
        call_sid="CA-test",
        caller="+919800000001",
        called="+18312286492",
        organization_id=ORGANIZATION_ID,
        actor_id=ACTOR_ID,
        secret="binding-secret",
        lifetime=timedelta(minutes=1),
    )
    assert verify_stream_binding(binding, "binding-secret") == {
        "call_sid": "CA-test",
        "caller": "+919800000001",
        "called": "+18312286492",
        "organization_id": str(ORGANIZATION_ID),
        "actor_id": str(ACTOR_ID),
    }
    assert verify_stream_binding(binding + "x", "binding-secret") is None


@pytest.mark.asyncio
async def test_openai_audio_adapter_uses_transcription_and_raw_pcm() -> None:
    observed: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request.url.path)
        assert request.headers["authorization"] == "Bearer openai-secret"
        if request.url.path.endswith("/transcriptions"):
            return httpx.Response(200, json={"text": "Namaste"})
        return httpx.Response(200, content=b"\x00\x00\x00\x00\x00\x00")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        audio = OpenAIAudioClient(_voice_settings(), client)
        transcript = await audio.transcribe_mulaw(bytes([0xFF]) * 160)
        outbound = await audio.synthesize_mulaw("Hello")
        streamed = b"".join([chunk async for chunk in audio.stream_synthesize_alaw("Hello")])

    assert transcript == "Namaste"
    assert len(outbound) == 1
    assert len(streamed) == 1
    assert observed == [
        "/v1/audio/transcriptions",
        "/v1/audio/speech",
        "/v1/audio/speech",
    ]


def test_signed_inbound_voice_webhook_returns_bound_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _voice_settings()
    monkeypatch.setattr(voice_route, "get_settings", lambda: settings)
    parameters = {
        "CallSid": "CA-test",
        "AccountSid": "AC-test",
        "From": "+919800000001",
        "To": "+18312286492",
    }
    public_url = "https://voice.example/v1/twilio/voice"
    signature = twilio_signature(public_url, parameters, "twilio-secret")
    get_settings.cache_clear()
    response = TestClient(create_app()).post(
        "/v1/twilio/voice",
        data=parameters,
        headers={"X-Twilio-Signature": signature},
    )

    assert response.status_code == 200
    assert "You are speaking with the A I receptionist" in response.text
    assert 'url="wss://voice.example/v1/twilio/media"' in response.text
    assert 'name="binding"' in response.text


def test_owner_button_dials_only_registered_phone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _voice_settings()
    settings = settings.model_copy(update={"database_url": "postgresql+asyncpg://unused"})
    owner = UUID("44444444-4444-4444-4444-444444444444")
    personal = PersonalSettings.model_construct(
        enabled=True, owner_id=owner, registered_phone="+919800000002"
    )
    monkeypatch.setattr(voice_route, "get_settings", lambda: settings)
    monkeypatch.setattr(voice_route, "get_personal_settings", lambda: personal)
    voice_route._last_test_call_at.clear()
    sent: dict[str, str] = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, data):
            sent.update(data)
            return httpx.Response(201, json={"sid": "CA-test-call"})

    monkeypatch.setattr(voice_route.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    result = asyncio.run(voice_route.start_receptionist_test_call(Principal(owner, None)))
    assert result == {"status": "queued", "call_sid": "CA-test-call"}
    assert sent["To"] == "+918529586946"
    assert sent["Url"] == "https://voice.example/v1/twilio/voice"
    with pytest.raises(ApiError) as denied:
        asyncio.run(voice_route.start_receptionist_test_call(
            Principal(UUID("55555555-5555-5555-5555-555555555555"), None)
        ))
    assert denied.value.status_code == 403


def test_signed_outbound_voice_webhook_uses_destination_as_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _voice_settings()
    monkeypatch.setattr(voice_route, "get_settings", lambda: settings)
    parameters = {
        "CallSid": "CA-outbound-test",
        "AccountSid": "AC-test",
        "From": "+18312286492",
        "To": "+918529586946",
        "Direction": "outbound-api",
    }
    public_url = "https://voice.example/v1/twilio/voice"
    signature = twilio_signature(public_url, parameters, "twilio-secret")
    get_settings.cache_clear()
    response = TestClient(create_app()).post(
        "/v1/twilio/voice",
        data=parameters,
        headers={"X-Twilio-Signature": signature},
    )

    assert response.status_code == 200
    assert "You are speaking with the A I receptionist" in response.text
    assert 'name="binding"' in response.text


def test_inbound_voice_webhook_rejects_unsigned_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(voice_route, "get_settings", _voice_settings)
    response = TestClient(create_app()).post(
        "/v1/twilio/voice",
        data={"CallSid": "CA-test", "From": "+919800000001", "To": "+18312286492"},
    )
    assert response.status_code == 403


def test_split_sentences_preserves_titles_and_numbers() -> None:
    text = "Dr. Sweta Sharma kal subah 10 baje available hain. Kya main aapke liye yeh slot confirm kar doon?"
    sentences = _split_sentences(text)
    assert len(sentences) == 2
    assert sentences[0] == "Dr. Sweta Sharma kal subah 10 baje available hain."
    assert sentences[1] == "Kya main aapke liye yeh slot confirm kar doon?"

    text_with_number = "Appointment ka samay 10.30 baje hai aur Mr. Aryan ka slot book hai."
    sentences2 = _split_sentences(text_with_number)
    assert len(sentences2) == 1
    assert "10.30" in sentences2[0]
    assert "Mr. Aryan" in sentences2[0]

    assert _split_sentences("") == []
    assert _split_sentences("Haanji.") == ["Haanji."]


@pytest.mark.asyncio
async def test_voicelink_comfort_filler_caching_and_synthesis() -> None:
    settings = _voice_settings()
    synthesized_texts: list[str] = []

    class MockAudio:
        async def synthesize_alaw(self, text: str) -> bytes:
            synthesized_texts.append(text)
            return b"\x55" * 160

        async def stream_synthesize_alaw(self, text: str):
            yield b"\x55" * 160

    gateway = VoiceLinkVoiceGateway(settings, audio=MockAudio())  # type: ignore

    # First call: uncached, invokes synthesize_alaw
    audio1 = await gateway._get_filler_audio("Ji Aryan ji, ek second...")
    assert audio1 == b"\x55" * 160
    assert "Ji Aryan ji, ek second..." in synthesized_texts

    # Second call: cached, returns immediately without re-synthesizing
    synthesized_count = len(synthesized_texts)
    audio2 = await gateway._get_filler_audio("Ji Aryan ji, ek second...")
    assert audio2 == audio1
    assert len(synthesized_texts) == synthesized_count

    # The entire reply shares one synthesis context, avoiding sentence-level voice resets.
    chunks = [
        c
        async for c in gateway._stream_text_alaw(
            "Dr. Sweta kal 10 baje available hain. Kya main book kar doon?"
        )
    ]
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_voicelink_barge_in_aborts_playback() -> None:
    settings = _voice_settings()
    sent_messages: list[dict] = []

    class MockWs:
        async def send_json(self, data: dict) -> None:
            sent_messages.append(data)

    gateway = VoiceLinkVoiceGateway(settings)
    mock_ws = MockWs()

    async def long_stream():
        for i in range(10):
            if i == 3:
                gateway._active_mark = ""
            yield b"\x55" * 160

    await gateway._play_stream(mock_ws, long_stream())  # type: ignore

    # Should have stopped sending once _active_mark was cleared (at 3 chunks)
    media_messages = [m for m in sent_messages if m.get("event") == "media"]
    assert len(media_messages) == 3
    # Mark event should not be sent when barged in
    mark_messages = [m for m in sent_messages if m.get("event") == "mark"]
    assert len(mark_messages) == 0
