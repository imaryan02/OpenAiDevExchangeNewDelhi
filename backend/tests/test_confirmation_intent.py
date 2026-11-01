import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.voice.confirmation_intent import ConfirmationIntent, ConfirmationIntentClassifier


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", list(ConfirmationIntent))
async def test_structured_intent_validated_and_readback_supplied(monkeypatch, intent):
    async def post(self, url, **kwargs):
        payload = kwargs["json"]
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert json.loads(payload["messages"][1]["content"]) == {
            "readback": "Appointment tomorrow; confirm?", "caller_reply": "hn book kar do",
        }
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({"intent": intent})},
        }]})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    classifier = ConfirmationIntentClassifier(Settings.model_construct(openai_api_key="test"))
    assert await classifier.classify(
        readback="Appointment tomorrow; confirm?", transcript="hn book kar do",
    ) == intent


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {}, {"choices": [{"finish_reason": "length", "message": {"content": '{"intent":"CONFIRM"}'}}]},
    {"choices": [{"finish_reason": "stop", "message": {"refusal": "refused"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": '{"intent":"UNKNOWN"}'}}]},
])
async def test_invalid_or_refused_classification_never_confirms(monkeypatch, body):
    response = httpx.Response(200, request=httpx.Request("POST", "https://example.test"), json=body)
    monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
    classifier = ConfirmationIntentClassifier(Settings.model_construct(openai_api_key="test"))
    assert await classifier.classify(readback="Summary", transcript="yes") == ConfirmationIntent.UNCLEAR


@pytest.mark.asyncio
async def test_timeout_never_confirms(monkeypatch):
    monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(side_effect=httpx.ReadTimeout("timeout")))
    classifier = ConfirmationIntentClassifier(Settings.model_construct(openai_api_key="test"))
    assert await classifier.classify(readback="Summary", transcript="yes") == ConfirmationIntent.UNCLEAR
