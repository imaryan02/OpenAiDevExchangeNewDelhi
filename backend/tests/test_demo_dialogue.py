import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.dialogue import explicit_confirmation, offer_readback
from app.agent.graph import ConfirmBookingOfferInput, build_graph
from app.agent.service import ReceptionAgent
from app.agent.tools import ToolExecutor
from app.core.config import Settings

OFFER = {
    "patient_name": "Demo Patient",
    "doctor_name": "Dr Demo",
    "location_name": "Demo Clinic",
    "session_date": "15 September 2026",
    "session_time": "5 PM to 7 PM IST",
    "booking_mode": "SESSION_WINDOW",
    "language": "hi-IN",
}


class Model:
    def __init__(self, replies: list[AIMessage]) -> None:
        self.replies = replies

    def bind_tools(self, *args: Any, **kwargs: Any) -> "Model":
        return self

    async def ainvoke(self, messages: Any) -> AIMessage:
        assert self.replies, "Unexpected extra model call after booking commit"
        return self.replies.pop(0)


def calls(*names: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": {}, "id": f"call-{i}-{name}", "type": "tool_call"}
            for i, name in enumerate(names)
        ],
    )


def fake_tools(observed: list[str]) -> list[StructuredTool]:
    async def prepare() -> dict[str, Any]:
        return {"ok": True, "offer_token": "private-demo-offer", "offer": dict(OFFER)}

    async def confirm(offer_token: str | None = None) -> dict[str, Any]:
        observed.append(offer_token or "")
        return {
            "ok": True,
            "status": "CONFIRMED",
            "booking_reference": "DEMO-101",
            "token_number": 8,
            "language": "hi-IN",
        }

    return [
        StructuredTool.from_function(
            coroutine=prepare, name="prepare_booking_offer", description="Prepare"
        ),
        StructuredTool.from_function(
            coroutine=confirm,
            name="confirm_booking_offer",
            description="Confirm",
            args_schema=ConfirmBookingOfferInput,
        ),
    ]


@pytest.mark.parametrize(
    "utterance",
    [
        "No Caller said: yes",
        "welcome",
        "welcome sir",
        "yes book tomorrow instead",
        "yes book for my father",
        "is booking confirmed please",
        "confirm ho gaya kya",
        "yes but at six",
        "haan mummy ke liye kar do",
        "yes book another doctor",
        "yes?",
        "Caller said: no\nCaller said: yes",
        "नहीं बुक करो",
        "हाँ लेकिन कल",
    ],
)
def test_non_consent_and_changed_fields_are_rejected(utterance: str) -> None:
    assert not explicit_confirmation([HumanMessage(content=utterance)])


@pytest.mark.parametrize(
    "utterance", ["haan kar do", "yes please", "हाँ बुक कर दीजिए", "theek hai ji kar dijiye"]
)
def test_clear_bilingual_acceptance(utterance: str) -> None:
    assert explicit_confirmation([HumanMessage(content=utterance)])


def test_only_matching_offer_name_may_be_repeated_in_acceptance() -> None:
    assert explicit_confirmation([HumanMessage(content="Haan Dr Demo ka confirm kar do")], OFFER)
    assert not explicit_confirmation(
        [HumanMessage(content="Haan Dr Other ka confirm kar do")], OFFER
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("batched", [True, False])
async def test_cannot_prepare_and_confirm_in_same_caller_turn(batched: bool) -> None:
    observed: list[str] = []
    replies = (
        [calls("prepare_booking_offer", "confirm_booking_offer")]
        if batched
        else [calls("prepare_booking_offer"), calls("confirm_booking_offer")]
    )
    replies.append(AIMessage(content="I already booked it!"))
    model = Model(replies)
    graph = build_graph(cast(Any, model), fake_tools(observed), InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid4())}}
    result = await graph.ainvoke({"messages": [HumanMessage(content="yes please")]}, config)
    assert observed == []
    assert result["offer_presented_turn"] == 1
    assert result["messages"][-1].content == offer_readback(OFFER)
    assert "private-demo-offer" not in str(result["messages"])

    model.replies.append(calls("confirm_booking_offer"))
    result = await graph.ainvoke({"messages": [HumanMessage(content="haan kar do")]}, config)
    assert observed == ["private-demo-offer"]
    assert "DEMO-101" in result["messages"][-1].content
    assert not model.replies  # No language-model call needed after a committed booking.


@pytest.mark.asyncio
async def test_correction_invalidates_offer_even_if_model_does_not_search() -> None:
    observed: list[str] = []
    model = Model(
        [
            calls("prepare_booking_offer"),
            AIMessage(content="Readback"),
            AIMessage(content="I will change it."),
            calls("confirm_booking_offer"),
            AIMessage(content="Booked!"),
        ]
    )
    graph = build_graph(cast(Any, model), fake_tools(observed), InMemorySaver())
    config = {"configurable": {"thread_id": str(uuid4())}}
    await graph.ainvoke({"messages": [HumanMessage(content="Book a session")]}, config)
    changed = await graph.ainvoke(
        {"messages": [HumanMessage(content="yes book tomorrow instead")]}, config
    )
    assert changed["active_offer_token"] is None
    result = await graph.ainvoke({"messages": [HumanMessage(content="yes please")]}, config)
    assert observed == []
    assert "could not confirm" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_unpresented_signed_offer_cannot_be_confirmed() -> None:
    observed: list[str] = []
    graph = build_graph(
        cast(Any, Model([calls("confirm_booking_offer"), AIMessage(content="Booked")])),
        fake_tools(observed),
        InMemorySaver(),
    )
    await graph.ainvoke(
        {
            "messages": [HumanMessage(content="yes please")],
            "active_offer_token": "private-demo-offer",
            "offer_version": hashlib.sha256(b"private-demo-offer").hexdigest(),
        },
        {"configurable": {"thread_id": str(uuid4())}},
    )
    assert observed == []


@pytest.mark.asyncio
async def test_service_does_not_replay_old_confirmation_or_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[str] = []
    monkeypatch.setattr("app.agent.service.build_tools", lambda executor: fake_tools(observed))
    model = Model(
        [
            calls("prepare_booking_offer"),
            AIMessage(content="Readback"),
            calls("confirm_booking_offer"),
            AIMessage(content="You are welcome."),
        ]
    )
    agent = ReceptionAgent(Settings(_env_file=None))
    agent._model = cast(Any, model)
    org, actor, thread = uuid4(), uuid4(), uuid4()
    session = MagicMock(spec=AsyncSession)
    first = await agent.respond("Book a session", session, org, actor, thread)
    assert first["data_changed"] is False
    assert first["reply"] == offer_readback(OFFER)
    confirmation = await agent.respond("haan kar do", session, org, actor, thread)
    assert confirmation["data_changed"] is True
    assert "DEMO-101" in str(confirmation["reply"])
    followup = await agent.respond("thank you", session, org, actor, thread)
    assert followup["data_changed"] is False
    assert followup["reply"] == "You are welcome."


def test_old_confirmation_helper_is_scoped_to_latest_human_turn() -> None:
    old = ToolMessage(name="confirm_booking_offer", tool_call_id="old", content='{"ok":true}')
    assert ReceptionAgent._confirmation_payload([old, HumanMessage(content="hello")]) is None


def row(value: dict[str, Any]) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.one.return_value = value
    result.mappings.return_value.one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_demo_booking_does_not_commit_simulated_payment_success() -> None:
    org, actor, patient, contact, phone, assignment, session_id, appointment = (
        uuid4() for _ in range(8)
    )
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(
        side_effect=[
            row({}),
            row({"appointment_id": appointment}),
            row({}),
            row({"booking_reference": "DEMO-CASH", "status": "CONFIRMED", "token_number": 2}),
            row({}),
        ]
    )
    session.commit = AsyncMock()
    executor = ToolExecutor(
        session,
        org,
        actor_id=actor,
        settings=Settings(_env_file=None, verification_code_pepper="synthetic-only"),
    )
    signed = executor._sign_offer(
        {
            "organization_id": str(org),
            "actor_id": str(actor),
            "patient_id": str(patient),
            "contact_id": str(contact),
            "phone_id": str(phone),
            "assignment_id": str(assignment),
            "session_id": str(session_id),
            "slot_id": None,
            "payment_method": "CASH",
            "language": "hi-IN",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "nonce": "synthetic",
        }
    )
    result = await executor.execute("confirm_booking_offer", {"offer_token": signed})
    assert result["payment_status"] == "DUE_AT_CLINIC"
    assert result["language"] == "hi-IN"
    queries = [str(call.args[0]) for call in session.execute.await_args_list]
    assert "PAY_AT_CLINIC" in queries[2]
    assert "DUE_AT_CLINIC" in queries[-1]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_preparation_forces_no_collection_even_if_model_requests_upi() -> None:
    org, actor, patient, contact, phone, assignment, session_id = (uuid4() for _ in range(7))
    starts = datetime.now(UTC) + timedelta(days=1)
    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(
        side_effect=[
            row({"phone_id": phone, "contact_id": contact, "caller_name": "Demo Caller"}),
            row({"patient_id": patient, "patient_name": "Demo Patient"}),
            row(
                {
                    "session_id": session_id,
                    "assignment_id": assignment,
                    "booking_mode": "SESSION_TOKEN",
                    "slot_id": None,
                    "session_starts_at": starts,
                    "session_ends_at": starts + timedelta(hours=2),
                    "timezone": "Asia/Kolkata",
                    "doctor_name": "Dr Demo",
                    "location_name": "Demo Clinic",
                    "fee_minor": 50000,
                    "currency": "INR",
                }
            ),
        ]
    )
    executor = ToolExecutor(
        session,
        org,
        actor_id=actor,
        settings=Settings(_env_file=None, verification_code_pepper="synthetic-only"),
    )
    result = await executor.execute(
        "prepare_booking_offer",
        {
            "phone_e164": "+919999999999",
            "patient_name": "Demo Patient",
            "relationship": "SELF",
            "session_id": str(session_id),
            "payment_method": "UPI",
            "language": "hi-IN",
        },
    )
    assert result["ok"] is True
    offer = cast(dict[str, Any], result["offer"])
    assert offer["payment_method"] == "CASH"
    assert offer["language"] == "hi-IN"
    assert offer_readback(offer) is not None


@pytest.mark.asyncio
async def test_model_failure_after_preparation_still_returns_truthful_readback() -> None:
    class ReadbackFailure(Model):
        async def ainvoke(self, messages: Any) -> AIMessage:
            if not self.replies:
                raise RuntimeError("Synthetic provider timeout")
            return await super().ainvoke(messages)

    graph = build_graph(
        cast(Any, ReadbackFailure([calls("prepare_booking_offer")])),
        fake_tools([]),
        InMemorySaver(),
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Book a session")]},
        {"configurable": {"thread_id": str(uuid4())}},
    )
    assert result["messages"][-1].content == offer_readback(OFFER)
    assert result["offer_presented_turn"] == 1
    assert result["current_confirmation"] is None
