import json
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.errors import ApiError


@dataclass(frozen=True)
class WhatsAppDelivery:
    provider_message_id: str
    status: str


class TwilioWhatsAppClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def send(
        self,
        to_phone_e164: str,
        body: str,
        *,
        status_callback: str | None = None,
        content_sid: str | None = None,
    ) -> WhatsAppDelivery:
        if not self._settings.twilio_whatsapp_configured:
            raise ApiError(
                code="WHATSAPP_NOT_CONFIGURED",
                message="Twilio WhatsApp is not configured on the backend.",
                status_code=503,
            )
        if not self._is_e164(to_phone_e164):
            raise ApiError(
                code="INVALID_NOTIFICATION_PHONE",
                message="A valid E.164 notification number is required.",
                status_code=422,
            )
        message = body.strip()
        if not message or len(message) > 1_600:
            raise ApiError(
                code="INVALID_NOTIFICATION_MESSAGE",
                message="The WhatsApp message must contain 1 to 1600 characters.",
                status_code=422,
            )

        account_sid = self._settings.twilio_account_sid or ""
        auth_token = self._settings.twilio_auth_token or ""
        sender = self._normalize_whatsapp(self._settings.twilio_whatsapp_from or "")
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        request = {
            "To": self._normalize_whatsapp(to_phone_e164),
            "From": sender,
        }
        if content_sid:
            request["ContentSid"] = content_sid
            request["ContentVariables"] = json.dumps({"1": message})
        else:
            request["Body"] = message
        if status_callback:
            request["StatusCallback"] = status_callback
        try:
            if self._client is not None:
                response = await self._client.post(
                    url,
                    data=request,
                    auth=(account_sid, auth_token),
                )
            else:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.post(
                        url,
                        data=request,
                        auth=(account_sid, auth_token),
                    )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ApiError(
                code="WHATSAPP_PROVIDER_ERROR",
                message="WhatsApp delivery could not be completed.",
                status_code=502,
            ) from error

        provider_message_id = str(payload.get("sid", "")).strip()
        if not provider_message_id:
            raise ApiError(
                code="WHATSAPP_PROVIDER_ERROR",
                message="WhatsApp delivery returned an invalid provider response.",
                status_code=502,
            )
        return WhatsAppDelivery(
            provider_message_id=provider_message_id,
            status=str(payload.get("status", "accepted")),
        )

    @staticmethod
    def _normalize_whatsapp(phone: str) -> str:
        value = phone.strip()
        return value if value.startswith("whatsapp:") else f"whatsapp:{value}"

    @staticmethod
    def _is_e164(phone: str) -> bool:
        value = phone.strip()
        return value.startswith("+") and value[1:].isdigit() and 8 <= len(value[1:]) <= 15
