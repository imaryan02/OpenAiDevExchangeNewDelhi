from pathlib import Path
from secrets import token_urlsafe


def upsert(lines: list[str], key: str, value: str, *, only_when_blank: bool = False) -> None:
    prefix = f"{key}="
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            if not only_when_blank or not line[len(prefix) :].strip():
                lines[index] = f"{prefix}{value}"
            return
    lines.append(f"{prefix}{value}")


env_path = Path(__file__).resolve().parents[1] / ".env"
env_lines = env_path.read_text(encoding="utf-8").splitlines()
upsert(env_lines, "VOICELINK_PHONE_NUMBER", "+919429397279")
upsert(env_lines, "VOICELINK_STREAM_SECRET", token_urlsafe(32), only_when_blank=True)
env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
print("VoiceLink phone number and private stream token are configured in backend/.env.")
