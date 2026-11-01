import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID


def twilio_signature(url: str, parameters: Mapping[str, str], auth_token: str) -> str:
    signed = url + "".join(f"{key}{parameters[key]}" for key in sorted(parameters))
    digest = hmac.new(auth_token.encode(), signed.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def valid_twilio_signature(
    url: str, parameters: Mapping[str, str], supplied: str | None, auth_token: str | None
) -> bool:
    if not supplied or not auth_token:
        return False
    expected = twilio_signature(url, parameters, auth_token)
    return hmac.compare_digest(expected, supplied)


def create_stream_binding(
    *,
    call_sid: str,
    caller: str,
    called: str,
    organization_id: UUID,
    actor_id: UUID,
    secret: str,
    lifetime: timedelta = timedelta(minutes=10),
) -> str:
    payload = {
        "call_sid": call_sid,
        "caller": caller,
        "called": called,
        "organization_id": str(organization_id),
        "actor_id": str(actor_id),
        "expires_at": int((datetime.now(UTC) + lifetime).timestamp()),
    }
    encoded = (
        base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )
    signature = hmac.new(
        secret.encode(), f"voice-stream:{encoded}".encode(), hashlib.sha256
    ).digest()
    return f"{encoded}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def verify_stream_binding(token: str, secret: str) -> dict[str, str] | None:
    try:
        encoded, supplied = token.split(".", 1)
        expected = hmac.new(
            secret.encode(), f"voice-stream:{encoded}".encode(), hashlib.sha256
        ).digest()
        supplied_bytes = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
        if not hmac.compare_digest(expected, supplied_bytes):
            return None
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw)
        if not isinstance(payload, dict) or int(payload["expires_at"]) <= int(
            datetime.now(UTC).timestamp()
        ):
            return None
        required = {"call_sid", "caller", "called", "organization_id", "actor_id"}
        if not required.issubset(payload):
            return None
        return {key: str(payload[key]) for key in required}
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
