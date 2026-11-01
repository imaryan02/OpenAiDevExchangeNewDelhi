from typing import Any, cast

import pytest

from app.core.config import Settings
from app.core.errors import ApiError
from app.services.outbox import dispatch_outbox_once


class Result:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    def mappings(self) -> "Result":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_failure", [False, True])
async def test_outbox_commits_lease_before_send_and_records_result(
    monkeypatch: pytest.MonkeyPatch, provider_failure: bool
) -> None:
    events: list[str] = []

    class Session:
        claims = 0

        async def execute(self, statement: Any, parameters: Any = None) -> Result:
            query = str(statement)
            if "claim_outbox" in query:
                events.append("claim")
                self.claims += 1
                return Result({"id": "job", "lease_token": "lease", "organization_id": "org",
                               "aggregate_id": "appointment", "job_type": "APPOINTMENT_CONFIRMED"}
                              if self.claims == 1 else None)
            if "complete_outbox" in query:
                events.append("complete")
                return Result(None)
            if "fail_outbox" in query:
                events.append("fail")
                assert parameters["code"] == "WHATSAPP_PROVIDER_ERROR"
                return Result(None)
            events.append("recipient")
            assert "phone.messaging_consent=true" in query and "phone.status='ACTIVE'" in query
            return Result({"booking_reference": "GM-TEST", "patient_name": "Synthetic Patient",
                           "doctor_name": "Dr Demo", "starts_at": "2026-10-01",
                           "phone_e164": "+919000000000"})

        async def commit(self) -> None:
            events.append("commit")

        async def rollback(self) -> None:
            events.append("rollback")

    class Client:
        def __init__(self, settings: Settings) -> None:
            pass

        async def send(self, phone: str, body: str) -> None:
            events.append("send")
            assert events[:3] == ["claim", "commit", "recipient"]
            if provider_failure:
                raise ApiError("WHATSAPP_PROVIDER_ERROR", "Provider unavailable", 502)

    monkeypatch.setattr("app.services.outbox.TwilioWhatsAppClient", Client)
    settings = Settings.model_construct(
        twilio_account_sid="test", twilio_auth_token="test", twilio_whatsapp_from="test"
    )
    delivered = await dispatch_outbox_once(cast(Any, Session()), settings)
    assert delivered == (0 if provider_failure else 1)
    expected = ["rollback", "fail", "commit"] if provider_failure else ["complete", "commit"]
    assert events[4:4 + len(expected)] == expected


@pytest.mark.asyncio
async def test_outbox_does_not_claim_without_provider_configuration() -> None:
    settings = Settings.model_construct(twilio_account_sid=None, twilio_auth_token=None)
    assert await dispatch_outbox_once(cast(Any, None), settings) == 0
