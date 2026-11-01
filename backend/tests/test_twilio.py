import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.integrations.twilio import TwilioWhatsAppClient


def _settings() -> Settings:
    return Settings.model_construct(
        twilio_account_sid="AC-test",
        twilio_auth_token="secret",
        twilio_whatsapp_from="whatsapp:+14155238886",
    )


@pytest.mark.asyncio
async def test_twilio_whatsapp_adapter_normalizes_recipient_and_hides_credentials() -> None:
    observed: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["body"] = request.content.decode()
        observed["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(201, json={"sid": "SM-test", "status": "queued"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        delivery = await TwilioWhatsAppClient(_settings(), http_client).send(
            "+918529586946",
            "Your synthetic appointment is confirmed.",
        )

    assert delivery.provider_message_id == "SM-test"
    assert delivery.status == "queued"
    assert "To=whatsapp%3A%2B918529586946" in observed["body"]
    assert "From=whatsapp%3A%2B14155238886" in observed["body"]
    assert observed["authorization"].startswith("Basic ")
    assert "secret" not in observed["authorization"]


@pytest.mark.asyncio
async def test_twilio_whatsapp_adapter_requires_backend_configuration() -> None:
    settings = Settings.model_construct(
        twilio_account_sid=None,
        twilio_auth_token=None,
        twilio_whatsapp_from=None,
    )

    with pytest.raises(ApiError) as error:
        await TwilioWhatsAppClient(settings).send("+918529586946", "Hello")

    assert error.value.code == "WHATSAPP_NOT_CONFIGURED"
