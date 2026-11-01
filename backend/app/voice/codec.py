import io
import struct
import wave
from collections import deque
from dataclasses import dataclass


def mulaw_to_pcm16_sample(value: int) -> int:
    encoded = (~value) & 0xFF
    sign = encoded & 0x80
    exponent = (encoded >> 4) & 0x07
    mantissa = encoded & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


def pcm16_sample_to_mulaw(sample: int) -> int:
    sign = 0x80 if sample < 0 else 0
    magnitude = min(abs(sample), 32635) + 0x84
    exponent = max(0, min(7, magnitude.bit_length() - 8))
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa)) & 0xFF


def mulaw8k_to_wav(payload: bytes) -> bytes:
    pcm = bytearray()
    for value in payload:
        pcm.extend(struct.pack("<h", mulaw_to_pcm16_sample(value)))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes(pcm))
    return output.getvalue()


def pcm24k_to_mulaw8k(payload: bytes) -> bytes:
    usable = len(payload) - (len(payload) % 6)
    samples = struct.unpack(f"<{usable // 2}h", payload[:usable]) if usable else ()
    output = bytearray()
    for index in range(0, len(samples), 3):
        group = samples[index : index + 3]
        if len(group) == 3:
            output.append(pcm16_sample_to_mulaw(sum(group) // 3))
    return bytes(output)


def alaw_to_pcm16_sample(value: int) -> int:
    encoded = value ^ 0x55
    mantissa = encoded & 0x0F
    exponent = (encoded & 0x70) >> 4
    sample = (mantissa << 4) + 8
    if exponent:
        sample += 0x100
        sample <<= exponent - 1
    return sample if encoded & 0x80 else -sample


def pcm16_sample_to_alaw(sample: int) -> int:
    mask = 0xD5
    if sample < 0:
        mask = 0x55
        sample = -sample - 8
    sample = max(0, min(sample, 32635))
    if sample < 256:
        encoded = sample >> 4
    else:
        exponent = min(7, sample.bit_length() - 8)
        encoded = (exponent << 4) | ((sample >> (exponent + 3)) & 0x0F)
    return encoded ^ mask


def alaw8k_to_wav(payload: bytes) -> bytes:
    pcm = bytearray()
    for value in payload:
        pcm.extend(struct.pack("<h", alaw_to_pcm16_sample(value)))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes(pcm))
    return output.getvalue()


def pcm24k_to_alaw8k(payload: bytes) -> bytes:
    usable = len(payload) - (len(payload) % 6)
    samples = struct.unpack(f"<{usable // 2}h", payload[:usable]) if usable else ()
    output = bytearray()
    for index in range(0, len(samples), 3):
        group = samples[index : index + 3]
        if len(group) == 3:
            output.append(pcm16_sample_to_alaw(sum(group) // 3))
    return bytes(output)


def alaw8k_to_pcm24k(payload: bytes) -> bytes:
    """Expand 8 kHz A-law samples into 24 kHz PCM16 for the Realtime boundary."""
    output = bytearray()
    for value in payload:
        sample = struct.pack("<h", alaw_to_pcm16_sample(value))
        output.extend(sample * 3)
    return bytes(output)


class Pcm24kToAlaw8k:
    """Stateful PCM conversion so a Realtime delta cannot split a sample group."""

    def __init__(self) -> None:
        self._pending = bytearray()

    def feed(self, payload: bytes) -> bytes:
        self._pending.extend(payload)
        usable = len(self._pending) - (len(self._pending) % 6)
        if not usable:
            return b""
        converted = pcm24k_to_alaw8k(bytes(self._pending[:usable]))
        del self._pending[:usable]
        return converted


def mulaw_energy(payload: bytes) -> float:
    if not payload:
        return 0.0
    return sum(abs(mulaw_to_pcm16_sample(value)) for value in payload) / len(payload)


@dataclass(frozen=True)
class TurnEvent:
    speech_started: bool = False
    utterance: bytes | None = None


class MulawTurnDetector:
    """Finalize telephone turns after sustained speech followed by silence."""

    def __init__(
        self,
        *,
        energy_threshold: float = 500.0,
        min_speech_frames: int = 10,
        end_silence_frames: int = 20,
        max_frames: int = 600,
        preroll_frames: int = 10,
    ) -> None:
        self._threshold = energy_threshold
        self._minimum = min_speech_frames
        self._end_silence = end_silence_frames
        self._maximum = max_frames
        self._preroll: deque[bytes] = deque(maxlen=preroll_frames)
        self._frames: list[bytes] = []
        self._speaking = False
        self._speech_frames = 0
        self._silence_frames = 0

    def feed(self, frame: bytes) -> TurnEvent:
        voiced = mulaw_energy(frame) >= self._threshold
        if not self._speaking:
            self._preroll.append(frame)
            if not voiced:
                return TurnEvent()
            self._speaking = True
            self._frames = list(self._preroll)
            self._speech_frames = 1
            self._silence_frames = 0
            return TurnEvent(speech_started=True)

        self._frames.append(frame)
        if voiced:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1
        if self._silence_frames < self._end_silence and len(self._frames) < self._maximum:
            return TurnEvent()

        utterance = b"".join(self._frames) if self._speech_frames >= self._minimum else None
        self.reset()
        return TurnEvent(utterance=utterance)

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def reset(self) -> None:
        self._preroll.clear()
        self._frames = []
        self._speaking = False
        self._speech_frames = 0
        self._silence_frames = 0


class AlawTurnDetector(MulawTurnDetector):
    """Finalize G.711 A-law telephone turns after sustained silence."""

    def __init__(
        self,
        *,
        energy_threshold: float = 500.0,
        min_speech_frames: int = 10,
        end_silence_frames: int = 15,
        max_frames: int = 600,
        preroll_frames: int = 10,
        onset_frames: int = 1,
    ) -> None:
        super().__init__(
            energy_threshold=energy_threshold,
            min_speech_frames=min_speech_frames,
            end_silence_frames=end_silence_frames,
            max_frames=max_frames,
            preroll_frames=preroll_frames,
        )
        self._onset_frames = max(1, onset_frames)
        self._onset_run = 0
        self._onset_reported = False

    def reset(self) -> None:
        super().reset()
        self._onset_run = 0
        self._onset_reported = False

    def feed(self, frame: bytes) -> TurnEvent:
        energy = (
            sum(abs(alaw_to_pcm16_sample(value)) for value in frame) / len(frame)
            if frame
            else 0.0
        )
        voiced = energy >= self._threshold
        if not self._speaking:
            self._preroll.append(frame)
            if not voiced:
                return TurnEvent()
            self._speaking = True
            self._frames = list(self._preroll)
            self._speech_frames = 1
            self._silence_frames = 0
            self._onset_run = 1
            self._onset_reported = self._onset_frames == 1
            return TurnEvent(speech_started=self._onset_reported)

        self._frames.append(frame)
        if voiced:
            self._speech_frames += 1
            self._silence_frames = 0
            self._onset_run += 1
        else:
            self._silence_frames += 1
            self._onset_run = 0
        speech_started = not self._onset_reported and self._onset_run >= self._onset_frames
        if speech_started:
            self._onset_reported = True
        if self._silence_frames < self._end_silence and len(self._frames) < self._maximum:
            return TurnEvent(speech_started=speech_started)

        utterance = b"".join(self._frames) if self._speech_frames >= self._minimum else None
        self.reset()
        return TurnEvent(utterance=utterance)
