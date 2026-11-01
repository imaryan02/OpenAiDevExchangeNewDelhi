import hashlib
from typing import Any, cast
from uuid import UUID

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from app.agent.graph import _explicit_confirmation, build_graph, build_tools
from app.agent.service import ReceptionAgent
from app.agent.tools import (
    TOOLS,
    ToolExecutor,
    _best_department_match,
    _best_doctor_match,
    _problem_route,
)
from app.core.config import Settings
from app.core.errors import ApiError


@pytest.mark.asyncio
async def test_agent_refuses_to_run_without_backend_configuration() -> None:
    settings = Settings.model_construct(openai_api_key=None, openai_model=None)

    with pytest.raises(ApiError) as error:
        await ReceptionAgent(settings).respond(
            "Is Dr Amit available?",
            object(),  # type: ignore[arg-type]
            UUID("22222222-2222-2222-2222-222222222222"),
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
        )

    assert error.value.code == "AI_NOT_CONFIGURED"


def test_phase_three_tools_keep_private_records_behind_verification() -> None:
    assert [tool["name"] for tool in TOOLS] == [
        "suggest_department",
        "search_availability",
        "lookup_caller_family",
        "start_phone_verification",
        "verify_phone_code",
        "list_upcoming_appointments",
        "prepare_booking_offer",
        "confirm_booking_offer",
        "get_clinic_information",
        "cancel_appointment",
        "reschedule_appointment",
    ]


def test_voice_doctor_name_variants_resolve_to_canonical_assignment() -> None:
    doctors = ["Dr Amit Sharma", "Dr Sweta Gupta"]

    assert _best_doctor_match("doctor Sweta", doctors) == "Dr Sweta Gupta"
    assert _best_doctor_match("Dr Shweta", doctors) == "Dr Sweta Gupta"
    assert _best_doctor_match("Doctor sweater Gupta", doctors) == "Dr Sweta Gupta"
    assert _best_doctor_match("Dr Mehta", doctors) is None


def test_problem_routing_is_limited_and_flags_warning_phrases() -> None:
    departments = ["General Medicine", "Gynae"]

    assert _problem_route("My periods are irregular") == "GYNAE"
    assert _problem_route("I have a headache") == "GENERAL_MEDICINE"
    assert _problem_route("I have chest pain and cannot breathe") == "URGENT"
    assert _best_department_match("gynecology", departments) == "Gynae"
    assert _best_department_match("general physician", departments) == "General Medicine"


@pytest.mark.asyncio
async def test_verification_tool_rejects_invalid_input_before_database_access() -> None:
    settings = Settings.model_construct(verification_code_pepper="test-pepper")
    executor = ToolExecutor(
        cast(Any, None),
        UUID("22222222-2222-2222-2222-222222222222"),
        actor_id=UUID("33333333-3333-3333-3333-333333333333"),
        settings=settings,
        whatsapp=cast(Any, None),
    )

    result = await executor.execute(
        "verify_phone_code",
        {"challenge_id": "not-a-uuid", "code": "123456"},
    )

    assert result == {"ok": False, "error": "A valid verification challenge is required."}


def test_verification_digest_is_stable_and_does_not_store_the_raw_code() -> None:
    settings = Settings.model_construct(verification_code_pepper="test-pepper")
    executor = ToolExecutor(
        cast(Any, None),
        UUID("22222222-2222-2222-2222-222222222222"),
        actor_id=UUID("33333333-3333-3333-3333-333333333333"),
        settings=settings,
    )

    digest = executor._code_digest("123456")

    assert digest == executor._code_digest("123456")
    assert digest != "123456"
    assert len(digest or "") == 64


def test_booking_offer_signature_detects_tampering() -> None:
    settings = Settings.model_construct(verification_code_pepper="test-pepper")
    executor = ToolExecutor(
        cast(Any, None),
        UUID("22222222-2222-2222-2222-222222222222"),
        actor_id=UUID("33333333-3333-3333-3333-333333333333"),
        settings=settings,
    )
    payload: dict[str, object] = {"patient_id": "patient-a", "expires_at": "tomorrow"}

    token = executor._sign_offer(payload)

    assert token is not None
    assert executor._verify_offer(token) == payload
    assert executor._verify_offer(f"{token}changed") is None


def test_confirmed_booking_uses_deterministic_database_result_reply() -> None:
    message = ToolMessage(
        name="confirm_booking_offer",
        tool_call_id="confirmation-1",
        content=(
            '{"ok":true,"status":"CONFIRMED","booking_reference":"GM-TEST123",'
            '"token_number":7,"payment_method":"UPI","patient_profile_created":true}'
        ),
    )

    reply = ReceptionAgent._deterministic_tool_reply([message])

    assert "GM-TEST123" in reply
    assert "token number is 7" in reply
    assert "Payment" not in reply


def test_failed_booking_uses_safe_tool_error_instead_of_empty_reply() -> None:
    message = ToolMessage(
        name="confirm_booking_offer",
        tool_call_id="confirmation-2",
        content='{"ok":false,"error":"The booking offer expired."}',
    )

    reply = ReceptionAgent._deterministic_tool_reply([message])

    assert reply == "I could not confirm that booking. Shall I check availability again?"


DEMO_OFFER = {
    "patient_name": "Synthetic Patient", "doctor_name": "Dr Demo",
    "location_name": "Demo Clinic", "session_date": "15 September 2026",
    "session_time": "5 PM to 7 PM IST", "booking_mode": "SESSION_WINDOW",
}


class _LookupInput(BaseModel):
    phone_e164: str


class _ConfirmOfferInput(BaseModel):
    offer_token: str


class _EmptyInput(BaseModel):
    pass


class _FakeBoundModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self.responses = responses
        self.inputs: list[list[object]] = []

    async def ainvoke(self, messages: list[object]) -> AIMessage:
        self.inputs.append(messages)
        return self.responses.pop(0)


class _FakeModel:
    def __init__(self, responses: list[AIMessage]) -> None:
        self.bound = _FakeBoundModel(responses)

    def bind_tools(self, tools: object, **kwargs: object) -> _FakeBoundModel:
        return self.bound


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["cancel_appointment", "reschedule_appointment"])
@pytest.mark.parametrize("confirmation", ["yes", "No, do not change anything"])
async def test_appointment_changes_preview_then_require_later_approval(
    operation: str, confirmation: str
) -> None:
    observed: list[dict[str, Any]] = []

    class Executor:
        async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, object]:
            observed.append(dict(arguments))
            return {
                "ok": True,
                "status": (
                    "CANCEL_PREVIEW" if name == "cancel_appointment" else "RESCHEDULE_PREVIEW"
                ) if arguments.get("_voice_preview") else (
                    "CANCELLED" if name == "cancel_appointment" else "RESCHEDULED"
                ),
                "booking_reference": "GM-ORIGINAL", "replacement_reference": "GM-REPLACEMENT",
                "patient_name": "Synthetic Patient", "doctor_name": "Dr Demo",
                "starts_at": "2026-10-01T10:00:00+05:30", "location_name": "Demo Clinic",
            }

    original = {"booking_reference": "GM-ORIGINAL"}
    if operation == "reschedule_appointment":
        original["new_session_id"] = "approved-session"

    def call(arguments: dict[str, str], identifier: str) -> AIMessage:
        return AIMessage(content="", tool_calls=[
            {"name": operation, "args": arguments, "id": identifier, "type": "tool_call"}
        ])

    executor = Executor()
    model = _FakeModel([
        # Even an initial "yes" may only prepare a preview.
        call(original, "preview"),
        call({**original, "booking_reference": "GM-MODEL-CHANGED"}, "later"),
    ])
    graph = build_graph(
        cast(Any, model), build_tools(cast(Any, executor)),
        checkpointer=InMemorySaver(), execute_operation=executor.execute,
    )
    config = {"configurable": {"thread_id": f"{operation}:{confirmation}"}}
    first = await graph.ainvoke(
        {"messages": [HumanMessage(content="yes")], "tool_calls": 0}, config=config,
    )
    assert len(observed) == 1 and observed[0]["_voice_preview"] is True
    assert first.get("current_confirmation") is None
    assert "Please confirm:" in first["messages"][-1].content
    assert "GM-ORIGINAL" in first["messages"][-1].content
    if operation == "reschedule_appointment":
        assert "2026-10-01" in first["messages"][-1].content
        assert "Demo Clinic" in first["messages"][-1].content
    second = await graph.ainvoke(
        {"messages": [HumanMessage(content=confirmation)], "tool_calls": 0}, config=config,
    )
    assert len(observed) == 2
    if confirmation == "yes":
        assert observed[1]["booking_reference"] == "GM-ORIGINAL"
        assert "_voice_preview" not in observed[1]
        assert second["current_confirmation"]["ok"] is True
    else:
        assert observed[1]["_voice_preview"] is True
        assert second.get("current_confirmation") is None


@pytest.mark.asyncio
async def test_appointment_changes_fail_closed_without_server_executor() -> None:
    async def mutation(booking_reference: str) -> dict[str, object]:
        pytest.fail("The model-facing wrapper must never execute a mutation directly.")

    tool = StructuredTool.from_function(
        coroutine=mutation, name="cancel_appointment", description="Cancel an appointment."
    )
    model = _FakeModel([
        AIMessage(content="", tool_calls=[{
            "name": "cancel_appointment", "args": {"booking_reference": "GM-TEST"},
            "id": "unsafe", "type": "tool_call",
        }]),
        AIMessage(content="Appointment changes are unavailable."),
    ])
    graph = build_graph(cast(Any, model), [tool], checkpointer=InMemorySaver())
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="yes")], "tool_calls": 0},
        config={"configurable": {"thread_id": "fail-closed"}},
    )
    assert result.get("current_confirmation") is None


@pytest.mark.asyncio
async def test_langgraph_executes_an_allowed_tool_and_returns_a_reply() -> None:
    observed: list[str] = []

    async def lookup(phone_e164: str) -> dict[str, object]:
        observed.append(phone_e164)
        return {"ok": True, "recognized": True, "caller_name": "Aryan"}

    tool = StructuredTool.from_function(
        coroutine=lookup,
        name="lookup_caller_family",
        description="Look up a saved caller.",
        args_schema=_LookupInput,
    )
    model = _FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "lookup_caller_family",
                        "args": {"phone_e164": "+919812345678"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="I found Aryan and the linked family profiles."),
        ]
    )
    graph = build_graph(
        cast(Any, model),
        [tool],
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Who is linked?")], "tool_calls": 0},
        config={"configurable": {"thread_id": "tool-test"}},
    )

    assert observed == ["+919812345678"]
    assert result["tool_calls"] == 1
    assert any(isinstance(message, ToolMessage) for message in result["messages"])
    assert result["messages"][-1].content == "I found Aryan and the linked family profiles."


@pytest.mark.asyncio
async def test_langgraph_blocks_booking_tool_without_explicit_confirmation() -> None:
    observed: list[str] = []

    async def confirm(offer_token: str) -> dict[str, object]:
        observed.append(offer_token)
        return {"ok": True, "status": "CONFIRMED"}

    token = "signed-offer"
    tool = StructuredTool.from_function(
        coroutine=confirm,
        name="confirm_booking_offer",
        description="Confirm an offer.",
        args_schema=_ConfirmOfferInput,
    )
    model = _FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "confirm_booking_offer",
                        "args": {},
                        "id": "call-confirm",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="I still need your explicit confirmation."),
        ]
    )
    graph = build_graph(
        cast(Any, model),
        [tool],
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Let me think about it")],
            "tool_calls": 0,
            "offer_version": hashlib.sha256(token.encode()).hexdigest(),
            "active_offer_token": token,
            "turn_number": 1, "offer_presented_turn": 1,
        },
        config={"configurable": {"thread_id": "consent-test"}},
    )

    assert observed == []
    tool_message = next(
        message for message in result["messages"] if isinstance(message, ToolMessage)
    )
    assert "Explicit confirmation" in str(tool_message.content)


@pytest.mark.asyncio
async def test_langgraph_keeps_signed_offer_out_of_model_messages() -> None:
    token = "private-signed-offer"

    async def prepare() -> dict[str, object]:
        return {"ok": True, "offer_token": token, "offer": {**DEMO_OFFER, "patient_name": "Ajay"}}

    tool = StructuredTool.from_function(
        coroutine=prepare,
        name="prepare_booking_offer",
        description="Prepare an offer.",
        args_schema=_EmptyInput,
    )
    model = _FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "prepare_booking_offer",
                        "args": {},
                        "id": "call-prepare",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Please confirm the offer."),
        ]
    )
    graph = build_graph(
        cast(Any, model),
        [tool],
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Prepare it")], "tool_calls": 0},
        config={"configurable": {"thread_id": "private-offer-test"}},
    )

    tool_message = next(
        message for message in result["messages"] if isinstance(message, ToolMessage)
    )
    assert token not in str(tool_message.content)
    assert result["active_offer_token"] == token
    assert result["offer_version"] == hashlib.sha256(token.encode()).hexdigest()


@pytest.mark.asyncio
async def test_langgraph_allows_matching_offer_after_explicit_confirmation() -> None:
    observed: list[str] = []

    async def confirm(offer_token: str) -> dict[str, object]:
        observed.append(offer_token)
        return {"ok": True, "status": "CONFIRMED"}

    token = "signed-offer"
    tool = StructuredTool.from_function(
        coroutine=confirm,
        name="confirm_booking_offer",
        description="Confirm an offer.",
        args_schema=_ConfirmOfferInput,
    )
    model = _FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "confirm_booking_offer",
                        "args": {},
                        "id": "call-confirm",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Your appointment is confirmed."),
        ]
    )
    graph = build_graph(
        cast(Any, model),
        [tool],
        checkpointer=InMemorySaver(),
    )

    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Yes, book it")],
            "tool_calls": 0,
            "offer_version": hashlib.sha256(token.encode()).hexdigest(),
            "active_offer_token": token,
            "turn_number": 1, "offer_presented_turn": 1,
        },
        config={"configurable": {"thread_id": "confirmed-consent-test"}},
    )

    assert observed == [token]
    assert result["offer_version"] is None
    assert result["active_offer_token"] is None
    assert result["consent_version"] == hashlib.sha256(token.encode()).hexdigest()


@pytest.mark.asyncio
async def test_langgraph_accepts_explicit_confirmation_from_trusted_voice_turn() -> None:
    observed: list[str] = []

    async def confirm(offer_token: str) -> dict[str, object]:
        observed.append(offer_token)
        return {"ok": True, "status": "CONFIRMED"}

    token = "signed-voice-offer"
    tool = StructuredTool.from_function(
        coroutine=confirm,
        name="confirm_booking_offer",
        description="Confirm an offer.",
        args_schema=_ConfirmOfferInput,
    )
    model = _FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "confirm_booking_offer",
                        "args": {},
                        "id": "call-confirm",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Your appointment is confirmed."),
        ]
    )
    graph = build_graph(cast(Any, model), [tool], checkpointer=InMemorySaver())

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "[Trusted voice turn 4. Telephony-verified incoming caller ID: "
                        "+919812345678.]\nCaller said: Haan kar dijiye"
                    )
                )
            ],
            "tool_calls": 0,
            "offer_version": hashlib.sha256(token.encode()).hexdigest(),
            "active_offer_token": token,
            "turn_number": 1, "offer_presented_turn": 1,
        },
        config={"configurable": {"thread_id": "voice-consent-test"}},
    )

    assert observed == [token]
    assert result["active_offer_token"] is None


@pytest.mark.parametrize(
    "utterance",
    [
        "Yes, you can confirm the appointment",
        "Okay please proceed with the booking",
        "Haan ji booking confirm kar dijiye",
        "जी हाँ, बुक कर दीजिए",
        "Theek hai",
        "Haan bilkul",
        "Sahi hai kar do",
        "Theek hai ji, kar dijiye",
        "Haan kar do",
        "Done, please proceed",
        "ठीक है कर दीजिए",
        "बिल्कुल कर दीजिए",
    ],
)
def test_explicit_confirmation_accepts_natural_voice_variants(utterance: str) -> None:
    message = HumanMessage(
        content=(
            "[Trusted voice turn 5. Telephony-verified incoming caller ID: "
            f"+919812345678.]\nCaller said: {utterance}"
        )
    )
    assert _explicit_confirmation([message]) is True


@pytest.mark.parametrize(
    "utterance",
    [
        "No, do not book it",
        "Yes, but change the doctor",
        "Haan ruko",
        "नहीं, कैंसिल कर दीजिए",
    ],
)
def test_explicit_confirmation_rejects_negative_or_changed_requests(utterance: str) -> None:
    message = HumanMessage(content=f"Caller said: {utterance}")
    assert _explicit_confirmation([message]) is False


@pytest.mark.asyncio
async def test_langgraph_keeps_conversation_state_by_server_thread_id() -> None:
    model = _FakeModel(
        [
            AIMessage(content="Which day would you prefer?"),
            AIMessage(content="Dr Amit is available on Monday."),
        ]
    )
    graph = build_graph(
        cast(Any, model),
        [],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "tenant-a:conversation-a"}}

    await graph.ainvoke(
        {"messages": [HumanMessage(content="Show Dr Amit this week.")], "tool_calls": 0},
        config=config,
    )
    await graph.ainvoke(
        {"messages": [HumanMessage(content="What days is he available?")], "tool_calls": 0},
        config=config,
    )

    second_input = model.bound.inputs[1]
    contents = [getattr(message, "content", "") for message in second_input]
    assert "Show Dr Amit this week." in contents
    assert "Which day would you prefer?" in contents
    assert "What days is he available?" in contents


@pytest.mark.asyncio
async def test_langgraph_supports_mid_call_offer_replacement() -> None:
    token_amit = "signed-offer-amit"
    token_sweta = "signed-offer-sweta"
    confirmed_tokens: list[str] = []

    async def prepare() -> dict[str, object]:
        return {"ok": True, "offer_token": token_sweta, "offer": {**DEMO_OFFER, "doctor_name": "Dr Sweta"}}

    async def confirm(offer_token: str) -> dict[str, object]:
        confirmed_tokens.append(offer_token)
        return {"ok": True, "booking_reference": "GM-9999", "status": "CONFIRMED"}

    prepare_tool = StructuredTool.from_function(
        coroutine=prepare,
        name="prepare_booking_offer",
        description="Prepare offer.",
        args_schema=_EmptyInput,
    )
    confirm_tool = StructuredTool.from_function(
        coroutine=confirm,
        name="confirm_booking_offer",
        description="Confirm offer.",
        args_schema=_ConfirmOfferInput,
    )

    model = _FakeModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "prepare_booking_offer",
                        "args": {},
                        "id": "call-sweta-prep",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Dr Sweta's session is prepared. Confirm?"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "confirm_booking_offer",
                        "args": {},
                        "id": "call-sweta-confirm",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Dr Sweta's appointment is confirmed."),
        ]
    )

    graph = build_graph(
        cast(Any, model),
        [prepare_tool, confirm_tool],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "pivot-test"}}

    state = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="Actually change to Dr Sweta")],
            "tool_calls": 0,
            "active_offer_token": token_amit,
            "offer_version": hashlib.sha256(token_amit.encode()).hexdigest(),
        },
        config=config,
    )

    assert state["active_offer_token"] == token_sweta
    assert state["offer_version"] == hashlib.sha256(token_sweta.encode()).hexdigest()

    confirm_state = await graph.ainvoke(
        {"messages": [HumanMessage(content="Haan Dr Sweta ka confirm kar do")], "tool_calls": 0},
        config=config,
    )

    assert confirmed_tokens == [token_sweta]
    assert confirm_state["active_offer_token"] is None
