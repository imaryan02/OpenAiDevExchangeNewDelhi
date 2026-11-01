import asyncio

from app.core.config import Settings
from app.integrations.openai_audio import OpenAIAudioClient


async def main() -> None:
    audio = OpenAIAudioClient(Settings())
    synthesized = await audio.synthesize_mulaw(
        "Hello. This is the A I receptionist for Geeta Medicine."
    )
    if len(synthesized) < 800:
        raise SystemExit("Speech generation returned too little audio.")
    transcript = await audio.transcribe_mulaw(synthesized)
    if not transcript:
        raise SystemExit("Transcription returned no text.")
    print(
        f"openai_audio_round_trip=passed outbound_mulaw_bytes={len(synthesized)} "
        f"transcript_chars={len(transcript)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
