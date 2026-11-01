import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated, Any, Literal, TypedDict
from zoneinfo import ZoneInfo

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from app.agent.dialogue import confirmation_reply, explicit_confirmation, offer_readback
from app.agent.policy import SYSTEM_INSTRUCTIONS
from app.agent.tools import ToolExecutor

MAX_TOOL_CALLS = 4
CHECKPOINTER = InMemorySaver()
logger = structlog.get_logger()


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    tool_calls: int
    preferred_language: str
    provenance: dict[str, str]
    offer_version: str | None
    active_offer_token: str | None
    consent_version: str | None
    turn_number: int
    offer_presented_turn: int | None
    offer_summary: dict[str, Any] | None
    current_confirmation: dict[str, Any] | None
    pending_operation: dict[str, Any] | None
    operation_presented_turn: int | None


class AvailabilityInput(BaseModel):
    from_at: str = Field(description="ISO 8601 datetime with timezone")
    to_at: str = Field(description="ISO 8601 datetime with timezone, after from_at")
    doctor_name: str | None = Field(default=None, description="Optional doctor name")
    department_name: str | None = Field(default=None, description="Optional department name")


class DepartmentSuggestionInput(BaseModel):
    problem_description: str = Field(
        min_length=3,
        max_length=500,
        description="The caller's own brief description of their problem.",
    )


class CallerFamilyInput(BaseModel):
    phone_e164: str = Field(description="Caller mobile number in E.164 format")


class ClinicInformationInput(BaseModel):
    topic: Literal["all", "address", "contact", "timings", "emergency", "payment_policy"] = "all"


class VerifyCodeInput(BaseModel):
    challenge_id: str = Field(description="Verification challenge UUID")
    code: str = Field(description="Six-digit code received by the caller")


class UpcomingAppointmentsInput(BaseModel):
    phone_e164: str = Field(description="Caller mobile number in E.164 format")
    challenge_id: str | None = Field(
        default=None, description="Optional verification challenge UUID"
    )


class PrepareBookingOfferInput(BaseModel):
    phone_e164: str = Field(description="Saved caller mobile number in E.164 format")
    caller_name: str | None = Field(default=None, description="Caller's stated name")
    patient_name: str = Field(description="Saved patient profile name")
    relationship: str = Field(description="SELF, MOTHER, FATHER, SPOUSE, CHILD, or OTHER")
    session_id: str = Field(description="Selected appointment session UUID")
    slot_id: str | None = Field(
        default=None,
        description="Internal reservation_slot_id from availability, when present",
    )
    payment_method: str = Field(
        default="CASH", description="Use CASH: no collection during the demo; due at clinic."
    )
    language: str = Field(description="Consent language: en, hi, en-IN, or hi-IN")
    create_patient_if_missing: bool = Field(
        default=False,
        description="True only when the caller explicitly asked to create this family profile",
    )
    create_caller_if_missing: bool = Field(
        default=False,
        description="True only after an unfamiliar caller has stated their name",
    )


class ConfirmBookingOfferInput(BaseModel):
    offer_token: str | None = Field(
        default=None,
        description="Injected by the server. The assistant should omit this argument.",
    )


class CancelAppointmentInput(BaseModel):
    booking_reference: str = Field(description="The clinic booking reference (e.g. GM-1234567890)")
    reason: str = Field(
        default="Cancelled by caller via telephone",
        description="Reason for cancellation",
    )


class RescheduleAppointmentInput(BaseModel):
    booking_reference: str = Field(description="The existing booking reference to reschedule")
    new_session_id: str = Field(description="The UUID of the new target session from search_availability")
    new_slot_id: str | None = Field(
        default=None,
        description="Optional slot ID if target session is exact-time",
    )


def build_tools(executor: ToolExecutor) -> list[BaseTool]:
    async def get_clinic_information(topic: str = "all") -> dict[str, object]:
        return await executor.execute("get_clinic_information", {"topic": topic})

    async def suggest_department(problem_description: str) -> dict[str, object]:
        return await executor.execute(
            "suggest_department", {"problem_description": problem_description}
        )

    async def search_availability(
        from_at: str,
        to_at: str,
        doctor_name: str | None = None,
        department_name: str | None = None,
    ) -> dict[str, object]:
        return await executor.execute(
            "search_availability",
            {
                "from_at": from_at,
                "to_at": to_at,
                "doctor_name": doctor_name,
                "department_name": department_name,
            },
        )

    async def lookup_caller_family(phone_e164: str) -> dict[str, object]:
        return await executor.execute("lookup_caller_family", {"phone_e164": phone_e164})

    async def start_phone_verification(phone_e164: str) -> dict[str, object]:
        return await executor.execute("start_phone_verification", {"phone_e164": phone_e164})

    async def verify_phone_code(challenge_id: str, code: str) -> dict[str, object]:
        return await executor.execute(
            "verify_phone_code",
            {"challenge_id": challenge_id, "code": code},
        )

    async def list_upcoming_appointments(
        phone_e164: str, challenge_id: str | None = None
    ) -> dict[str, object]:
        return await executor.execute(
            "list_upcoming_appointments",
            {"phone_e164": phone_e164, "challenge_id": challenge_id},
        )

    async def prepare_booking_offer(
        phone_e164: str,
        patient_name: str,
        relationship: str,
        session_id: str,
        payment_method: str = "CASH",
        language: str = "en",
        caller_name: str | None = None,
        slot_id: str | None = None,
        create_patient_if_missing: bool = False,
        create_caller_if_missing: bool = False,
    ) -> dict[str, object]:
        return await executor.execute(
            "prepare_booking_offer",
            {
                "phone_e164": phone_e164,
                "caller_name": caller_name,
                "patient_name": patient_name,
                "relationship": relationship,
                "session_id": session_id,
                "slot_id": slot_id,
                "payment_method": payment_method,
                "language": language,
                "create_patient_if_missing": create_patient_if_missing,
                "create_caller_if_missing": create_caller_if_missing,
            },
        )

    async def confirm_booking_offer(offer_token: str | None = None) -> dict[str, object]:
        return await executor.execute(
            "confirm_booking_offer",
            {"offer_token": offer_token or ""},
        )

    async def cancel_appointment(
        booking_reference: str, reason: str = "Cancelled by caller via telephone"
    ) -> dict[str, object]:
        return await executor.execute(
            "cancel_appointment",
            {"booking_reference": booking_reference, "reason": reason},
        )

    async def reschedule_appointment(
        booking_reference: str, new_session_id: str, new_slot_id: str | None = None
    ) -> dict[str, object]:
        return await executor.execute(
            "reschedule_appointment",
            {
                "booking_reference": booking_reference,
                "new_session_id": new_session_id,
                "new_slot_id": new_slot_id,
            },
        )

    return [
        StructuredTool.from_function(
            coroutine=get_clinic_information,
            name="get_clinic_information",
            description="Retrieve verified clinic addresses, departments, timing notes and payment policy.",
            args_schema=ClinicInformationInput,
        ),
        StructuredTool.from_function(
            coroutine=suggest_department,
            name="suggest_department",
            description=(
                "Suggest an active clinic department and list its doctors from a caller's "
                "problem description. This is administrative routing, not diagnosis."
            ),
            args_schema=DepartmentSuggestionInput,
        ),
        StructuredTool.from_function(
            coroutine=search_availability,
            name="search_availability",
            description=(
                "Find current bookable sessions in a date range. Doctor and department are "
                "optional; omit both to discover all available options."
            ),
            args_schema=AvailabilityInput,
        ),
        StructuredTool.from_function(
            coroutine=lookup_caller_family,
            name="lookup_caller_family",
            description=(
                "Recognize a caller mobile and list linked family profiles. "
                "This never returns appointments."
            ),
            args_schema=CallerFamilyInput,
        ),
        StructuredTool.from_function(
            coroutine=start_phone_verification,
            name="start_phone_verification",
            description=(
                "Send a verification code when the channel requires a phone challenge. "
                "Do not use for an incoming telephone call with server-bound caller identity."
            ),
            args_schema=CallerFamilyInput,
        ),
        StructuredTool.from_function(
            coroutine=verify_phone_code,
            name="verify_phone_code",
            description="Verify the six-digit code supplied by the caller.",
            args_schema=VerifyCodeInput,
        ),
        StructuredTool.from_function(
            coroutine=list_upcoming_appointments,
            name="list_upcoming_appointments",
            description=(
                "List upcoming appointments permitted for the caller. On an incoming telephone "
                "call, use the server-bound caller number and omit challenge_id; no OTP step. "
                "For a challenge-based flow, supply the verified challenge_id."
            ),
            args_schema=UpcomingAppointmentsInput,
        ),
        StructuredTool.from_function(
            coroutine=prepare_booking_offer,
            name="prepare_booking_offer",
            description=(
                "Prepare a short-lived booking offer for a saved caller and patient. "
                "Read the complete returned summary and ask for explicit confirmation."
            ),
            args_schema=PrepareBookingOfferInput,
        ),
        StructuredTool.from_function(
            coroutine=confirm_booking_offer,
            name="confirm_booking_offer",
            description=(
                "Confirm the active offer only after the caller explicitly accepts the "
                "complete read-back. Call with no arguments; the server injects the offer."
            ),
            args_schema=ConfirmBookingOfferInput,
        ),
        StructuredTool.from_function(
            coroutine=cancel_appointment,
            name="cancel_appointment",
            description=(
                "Cancel an existing upcoming appointment for the caller after explicit confirmation."
            ),
            args_schema=CancelAppointmentInput,
        ),
        StructuredTool.from_function(
            coroutine=reschedule_appointment,
            name="reschedule_appointment",
            description=(
                "Move an existing confirmed appointment to a new available session date/time."
            ),
            args_schema=RescheduleAppointmentInput,
        ),
    ]


def _explicit_confirmation(
    messages: list[AnyMessage],
    offer: dict[str, Any] | None = None,
) -> bool:
    return explicit_confirmation(messages, offer)


def build_graph(
    model: BaseChatModel,
    tools: list[BaseTool],
    checkpointer: Any = CHECKPOINTER,
    on_lookup_start: Callable[[], None] | None = None,
    execute_operation: Callable[[str, dict[str, Any]], Awaitable[dict[str, object]]] | None = None,
) -> Any:
    from app.voice import presentation

    tool_by_name = {tool.name: tool for tool in tools}
    presentation.available_tools(list(tool_by_name))
    model_with_tools = model.bind_tools(tools, parallel_tool_calls=False)

    async def call_model(state: AgentState) -> dict[str, object]:
        outcome = state.get("current_confirmation")
        if outcome and outcome.get("ok") is True:
            return {"messages": [AIMessage(content=confirmation_reply(outcome))]}
        today = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(timespec="minutes")
        active_offer = state.get("active_offer_token")
        pending_operation = state.get("pending_operation")
        if pending_operation and state.get("operation_presented_turn") == state.get("turn_number", 0):
            summary = pending_operation["summary"]
            details = (
                f"appointment {summary['booking_reference']} for {summary['patient_name']} "
                f"with {summary['doctor_name']}"
            )
            if pending_operation["tool_name"] == "reschedule_appointment":
                details += f" to {summary['starts_at']}"
                if summary.get("location_name"):
                    details += f" at {summary['location_name']}"
            action = "cancel" if pending_operation["tool_name"] == "cancel_appointment" else "reschedule"
            return {"messages": [AIMessage(content=f"Please confirm: {action} {details}.")]}
        consent_ver = state.get("consent_version")
        if active_offer:
            status_note = (
                "\n\n[SYSTEM STATE NOTE: A booking offer has been prepared but is NOT YET CONFIRMED in the database. "
                "The appointment does NOT exist until you call confirm_booking_offer. "
                "DO NOT claim or tell the caller their appointment is booked/confirmed. "
                "Only explicit acceptance in a later caller turn permits confirmation. A status question is not acceptance.]"
            )
        elif consent_ver:
            status_note = (
                "\n\n[SYSTEM STATE NOTE: The booking was successfully confirmed in the database. "
                "You may conclude the conversation warmly with the confirmed reference.]"
            )
        else:
            status_note = ""
        if pending_operation:
            status_note += (
                "\n\n[SYSTEM STATE NOTE: A cancellation or reschedule preview has been prepared but has NOT "
                "been applied. Read back its returned appointment details and wait for explicit approval in a "
                "later caller turn. Never execute a different operation or altered arguments.]"
            )

        system = SystemMessage(
            content=f"{SYSTEM_INSTRUCTIONS}\nCurrent clinic date and time: {today}.{status_note}"
        )
        try:
            response = await model_with_tools.ainvoke([system, *state.get("messages", [])])
        except Exception:
            # A completed offer can still be read truthfully when the model's
            # final wording request fails. Never lose an actionable tool result.
            readback = offer_readback(state.get("offer_summary") or {}) if active_offer else None
            if readback:
                return {
                    "messages": [AIMessage(content=readback)],
                    "offer_presented_turn": state.get("turn_number", 0),
                }
            if outcome is not None:
                return {"messages": [AIMessage(content=confirmation_reply(outcome))]}
            raise
        update: dict[str, object] = {"messages": [response]}
        if not response.tool_calls and active_offer and state.get("offer_summary"):
            readback = offer_readback(state["offer_summary"] or {})
            if readback:
                update["messages"] = [AIMessage(content=readback)]
                update["offer_presented_turn"] = state.get("turn_number", 0)
        elif not response.tool_calls and outcome is not None:
            update["messages"] = [AIMessage(content=confirmation_reply(outcome))]
        return update

    async def call_tools(state: AgentState) -> dict[str, object]:
        last_message = state.get("messages", [])[-1]
        calls = last_message.tool_calls if isinstance(last_message, AIMessage) else []
        used = state.get("tool_calls", 0)
        outputs: list[ToolMessage] = []
        offer_version = state.get("offer_version")
        active_offer_token = state.get("active_offer_token")
        consent_version = state.get("consent_version")
        presented_turn = state.get("offer_presented_turn")
        offer_summary = state.get("offer_summary")
        current_confirmation = state.get("current_confirmation")
        pending_operation = state.get("pending_operation")
        operation_presented_turn = state.get("operation_presented_turn")
        for call in calls:
            presentation.selected_tool(call["name"])
            if used >= MAX_TOOL_CALLS:
                result: object = {
                    "ok": False,
                    "error": "Safe lookup limit reached. Ask one focused clarification.",
                }
            else:
                used += 1
                tool_name = call["name"]
                tool = tool_by_name.get(tool_name)
                tool_arguments = dict(call.get("args", {}))
                operation = pending_operation or {}
                if tool_name == "confirm_booking_offer":
                    tool_arguments["offer_token"] = active_offer_token or ""
                if tool_name in {"cancel_appointment", "reschedule_appointment"} and pending_operation is None:
                    # A model call is never sufficient authority to change an appointment. First obtain
                    # server-verified details, then bind a later caller confirmation to these exact arguments.
                    tool_arguments["_voice_preview"] = True
                    result = None
                elif tool_name in {"cancel_appointment", "reschedule_appointment"} and (
                    operation.get("tool_name") != tool_name
                ):
                    result = {"ok": False, "error": "A different appointment change is awaiting confirmation."}
                elif tool_name in {"cancel_appointment", "reschedule_appointment"} and not _explicit_confirmation(
                    state.get("messages", []), operation.get("summary")
                ):
                    result = {"ok": False, "error": "Explicit confirmation of the appointment change is required."}
                elif tool_name in {"cancel_appointment", "reschedule_appointment"} and (
                    operation_presented_turn is None or operation_presented_turn >= state.get("turn_number", 0)
                ):
                    result = {"ok": False, "error": "Read back the appointment change and wait for a later caller turn."}
                elif tool_name in {"cancel_appointment", "reschedule_appointment"}:
                    tool_arguments = dict(operation["arguments"])
                    result = None
                else:
                    result = None
                if result is None and tool_name == "confirm_booking_offer" and not _explicit_confirmation(
                    state.get("messages", []), offer_summary
                ):
                    result = {
                        "ok": False,
                        "error": "Explicit confirmation of the active offer is required.",
                    }
                elif result is None and tool_name == "confirm_booking_offer" and not active_offer_token:
                    result = {
                        "ok": False,
                        "error": (
                            "No active booking offer found. Please call prepare_booking_offer "
                            "first before confirming."
                        ),
                    }
                elif result is None and tool_name == "confirm_booking_offer" and (
                    active_offer_token is None
                    or hashlib.sha256(active_offer_token.encode()).hexdigest() != offer_version
                ):
                    result = {
                        "ok": False,
                        "error": (
                            "The active booking offer has changed. Please call prepare_booking_offer "
                            "to prepare a fresh offer."
                        ),
                    }
                elif result is None and tool_name == "confirm_booking_offer" and (
                    presented_turn is None or presented_turn >= state.get("turn_number", 0)
                ):
                    result = {
                        "ok": False,
                        "error": "Read the offer and wait for a later caller turn before confirmation.",
                    }
                elif result is None and current_confirmation and current_confirmation.get("ok") is True:
                    result = {
                        "ok": False,
                        "error": "Booking already confirmed this turn. Report its result.",
                    }
                elif result is None and tool is None:
                    result = {"ok": False, "error": "Tool is not allowed."}
                elif result is None:
                    assert tool is not None
                    tool_started_at = time.perf_counter()
                    try:
                        if on_lookup_start is not None and tool_name in {
                            "search_availability", "suggest_department", "get_clinic_information",
                            "lookup_caller_family", "list_upcoming_appointments",
                        }:
                            on_lookup_start()
                        if tool_name in {"cancel_appointment", "reschedule_appointment"}:
                            # StructuredTool validates model arguments and drops private flags.
                            # Keep preview/approved dispatch on the server-owned executor path.
                            result = (
                                await execute_operation(tool_name, tool_arguments)
                                if execute_operation is not None
                                else {"ok": False, "error": "Appointment changes are unavailable."}
                            )
                        else:
                            result = await tool.ainvoke(tool_arguments)
                    except Exception:
                        result = {"ok": False, "error": "Verified lookup failed."}
                    logger.info(
                        "agent_tool_call",
                        tool_name=tool_name,
                        ok=result.get("ok") if isinstance(result, dict) else None,
                        result_count=(
                            len(result.get("sessions", []))
                            if isinstance(result, dict) and isinstance(result.get("sessions"), list)
                            else None
                        ),
                        elapsed_ms=round((time.perf_counter() - tool_started_at) * 1000),
                    )
                if call["name"] == "prepare_booking_offer" and isinstance(result, dict):
                    token = result.get("offer_token")
                    offer_version = (
                        hashlib.sha256(str(token).encode()).hexdigest() if token else None
                    )
                    active_offer_token = str(token) if token else None
                    result = dict(result)
                    result.pop("offer_token", None)
                    consent_version = None
                    presented_turn = None
                    offer_summary = (
                        result.get("offer") if isinstance(result.get("offer"), dict) else None
                    )
                elif call["name"] in ("cancel_appointment", "reschedule_appointment") and isinstance(result, dict) and result.get("ok") is True and result.get("status") in {"CANCEL_PREVIEW", "RESCHEDULE_PREVIEW"} and tool_arguments.get("_voice_preview") is True:
                    pending_operation = {
                        "tool_name": call["name"],
                        "arguments": {key: value for key, value in tool_arguments.items() if key != "_voice_preview"},
                        "summary": dict(result),
                    }
                    operation_presented_turn = state.get("turn_number", 0)
                elif (
                    call["name"] in ("confirm_booking_offer", "cancel_appointment", "reschedule_appointment")
                    and isinstance(result, dict)
                    and result.get("ok") is True
                ):
                    consent_version = offer_version
                    offer_version = None
                    active_offer_token = None
                    presented_turn = None
                    offer_summary = None
                    pending_operation = None
                    operation_presented_turn = None
                elif call["name"] == "search_availability":
                    offer_version = None
                    active_offer_token = None
                    consent_version = None
                    presented_turn = None
                    offer_summary = None
                if (
                    call["name"] in ("confirm_booking_offer", "cancel_appointment", "reschedule_appointment")
                    and isinstance(result, dict)
                    and not tool_arguments.get("_voice_preview")
                ):
                    result.setdefault(
                        "language", (state.get("offer_summary") or {}).get("language", "en")
                    )
                    if not current_confirmation or current_confirmation.get("ok") is not True:
                        current_confirmation = result
            presentation.emit("result_transmitted", "voice", "Tool result added to agent context",
                              tool=call["name"])
            outputs.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=call["id"],
                    name=call["name"],
                )
            )
        return {
            "messages": outputs,
            "tool_calls": used,
            "offer_version": offer_version,
            "active_offer_token": active_offer_token,
            "consent_version": consent_version,
            "offer_presented_turn": presented_turn,
            "offer_summary": offer_summary,
            "current_confirmation": current_confirmation,
            "pending_operation": pending_operation,
            "operation_presented_turn": operation_presented_turn,
        }

    def route_after_model(state: AgentState) -> str:
        messages = state.get("messages", [])
        if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
            return "tools"
        return END

    def begin_turn(state: AgentState) -> dict[str, object]:
        update: dict[str, object] = {
            "turn_number": state.get("turn_number", 0) + 1,
            "tool_calls": 0,
            "current_confirmation": None,
        }
        # A non-acceptance may contain a correction. Retain conversation details,
        # but require a fresh offer/readback before a later yes can mutate records.
        if state.get("active_offer_token") and not _explicit_confirmation(
            state.get("messages", []), state.get("offer_summary")
        ):
            update.update(
                active_offer_token=None,
                offer_version=None,
                offer_presented_turn=None,
                offer_summary=None,
                consent_version=None,
            )
        pending_operation = state.get("pending_operation")
        if pending_operation and not _explicit_confirmation(
            state.get("messages", []), pending_operation.get("summary")
        ):
            update.update(pending_operation=None, operation_presented_turn=None)
        return update

    builder = StateGraph(AgentState)
    builder.add_node("begin_turn", begin_turn)
    builder.add_node("assistant", call_model)
    builder.add_node("tools", call_tools)
    builder.add_edge(START, "begin_turn")
    builder.add_edge("begin_turn", "assistant")
    builder.add_conditional_edges("assistant", route_after_model, {"tools": "tools", END: END})
    builder.add_edge("tools", "assistant")
    return builder.compile(checkpointer=checkpointer)
