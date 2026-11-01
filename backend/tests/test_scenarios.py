import hashlib
from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

from app.agent.graph import build_graph
from app.agent.policy import SYSTEM_INSTRUCTIONS
from app.agent.tools import (
    _best_department_match,
    _best_doctor_match,
    _problem_route,
)

DEMO_OFFER = {
    "patient_name": "Synthetic Patient", "doctor_name": "Dr Demo",
    "location_name": "Demo Clinic", "session_date": "15 September 2026",
    "session_time": "5 PM to 7 PM IST", "booking_mode": "SESSION_WINDOW",
}


class _EmptyInput(BaseModel):
    pass


class _LookupInput(BaseModel):
    phone_e164: str


class _ConfirmOfferInput(BaseModel):
    offer_token: str = ''


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
async def test_scenario_1_registered_caller_booking_for_registered_mother() -> None:
    token = 'offer-token-sunita-sweta'
    confirmed_tokens: list[str] = []

    async def lookup(phone_e164: str) -> dict[str, object]:
        return {
            'ok': True,
            'recognized': True,
            'caller_name': 'Aryan Gupta',
            'patients': [{'patient_name': 'Sunita Gupta', 'relationship': 'MOTHER'}],
        }

    async def prepare() -> dict[str, object]:
        return {
            'ok': True,
            'offer_token': token,
            'offer': {**DEMO_OFFER,
                'doctor_name': 'Dr Sweta Gupta',
                'patient_name': 'Sunita Gupta',
                'slot_start': '2026-09-15T10:00:00+05:30',
            },
        }

    async def confirm(offer_token: str) -> dict[str, object]:
        confirmed_tokens.append(offer_token)
        return {
            'ok': True,
            'booking_reference': 'GM-SUNITA-101',
            'status': 'CONFIRMED',
            'token_number': 5,
        }

    tools = [
        StructuredTool.from_function(
            coroutine=lookup,
            name='lookup_caller_family',
            description='Lookup caller family.',
            args_schema=_LookupInput,
        ),
        StructuredTool.from_function(
            coroutine=prepare,
            name='prepare_booking_offer',
            description='Prepare offer.',
            args_schema=_EmptyInput,
        ),
        StructuredTool.from_function(
            coroutine=confirm,
            name='confirm_booking_offer',
            description='Confirm offer.',
            args_schema=_ConfirmOfferInput,
        ),
    ]

    model = _FakeModel(
        [
            AIMessage(
                content='',
                tool_calls=[
                    {'name': 'lookup_caller_family', 'args': {'phone_e164': '+918529586946'}, 'id': 't1', 'type': 'tool_call'}
                ],
            ),
            AIMessage(content='Haan Aryan ji bilkul! Sunita ji ke liye book karein? Kis doctor se milna hai?'),
            AIMessage(
                content='',
                tool_calls=[
                    {'name': 'prepare_booking_offer', 'args': {}, 'id': 't2', 'type': 'tool_call'}
                ],
            ),
            AIMessage(content='Dr. Sweta ke saath Sunita ji ka slot 15 September 10 baje prepare ho gaya hai. Kya confirm kar doon?'),
            AIMessage(
                content='',
                tool_calls=[
                    {'name': 'confirm_booking_offer', 'args': {}, 'id': 't3', 'type': 'tool_call'}
                ],
            ),
            AIMessage(content='Sunita ji ka appointment confirm ho gaya hai! Reference: GM-SUNITA-101, Token: 5.'),
        ]
    )

    graph = build_graph(cast(Any, model), tools, checkpointer=InMemorySaver())
    config = {'configurable': {'thread_id': 'scenario-1-thread'}}

    t1 = await graph.ainvoke(
        {'messages': [HumanMessage(content='Mummy ke liye appointment book karana hai')], 'tool_calls': 0},
        config=config,
    )
    assert 'Sunita ji' in t1['messages'][-1].content

    t2 = await graph.ainvoke(
        {'messages': [HumanMessage(content='Dr Sweta ke paas kara do')], 'tool_calls': 0},
        config=config,
    )
    assert t2['active_offer_token'] == token

    t3 = await graph.ainvoke(
        {'messages': [HumanMessage(content='Haanji bilkul, confirm kar dijiye')], 'tool_calls': 0},
        config=config,
    )
    assert confirmed_tokens == [token]
    assert t3['active_offer_token'] is None
    assert 'GM-SUNITA-101' in t3['messages'][-1].content


@pytest.mark.asyncio
async def test_scenario_2_registered_caller_booking_for_unregistered_family_member() -> None:
    token = 'offer-token-ramesh-amit'
    confirmed_tokens: list[str] = []

    async def prepare() -> dict[str, object]:
        return {
            'ok': True,
            'offer_token': token,
            'offer': {**DEMO_OFFER,
                'doctor_name': 'Dr Amit Kumar',
                'patient_name': 'Ramesh Gupta',
                'relationship': 'FATHER',
            },
        }

    async def confirm(offer_token: str) -> dict[str, object]:
        confirmed_tokens.append(offer_token)
        return {
            'ok': True,
            'booking_reference': 'GM-RAMESH-202',
            'status': 'CONFIRMED',
            'patient_profile_created': True,
        }

    tools = [
        StructuredTool.from_function(
            coroutine=prepare,
            name='prepare_booking_offer',
            description='Prepare offer.',
            args_schema=_EmptyInput,
        ),
        StructuredTool.from_function(
            coroutine=confirm,
            name='confirm_booking_offer',
            description='Confirm offer.',
            args_schema=_ConfirmOfferInput,
        ),
    ]

    model = _FakeModel(
        [
            AIMessage(
                content='',
                tool_calls=[
                    {'name': 'prepare_booking_offer', 'args': {}, 'id': 't1', 'type': 'tool_call'}
                ],
            ),
            AIMessage(content='Maine Ramesh Gupta ji ke liye Dr. Amit ke paas slot hold kar diya hai. Kya confirm kar doon?'),
            AIMessage(
                content='',
                tool_calls=[
                    {'name': 'confirm_booking_offer', 'args': {}, 'id': 't2', 'type': 'tool_call'}
                ],
            ),
            AIMessage(content='Ramesh ji ka appointment confirm ho gaya hai. Family profile create kar diya gaya hai.'),
        ]
    )

    graph = build_graph(cast(Any, model), tools, checkpointer=InMemorySaver())
    config = {'configurable': {'thread_id': 'scenario-2-thread'}}

    t1 = await graph.ainvoke(
        {'messages': [HumanMessage(content='Father ke liye book karna hai, Ramesh Gupta, Dr Amit ke paas')], 'tool_calls': 0},
        config=config,
    )
    assert t1['active_offer_token'] == token

    t2 = await graph.ainvoke(
        {'messages': [HumanMessage(content='Theek hai kar do')], 'tool_calls': 0},
        config=config,
    )
    assert confirmed_tokens == [token]
    assert t2['active_offer_token'] is None


def test_scenario_3_symptom_routing_to_general_medicine() -> None:
    departments = ['General Medicine', 'Gynaecology']

    route = _problem_route('Mujhe do din se bukhar aur sar dard hai')
    assert route == 'GENERAL_MEDICINE'

    route_en = _problem_route('I have high fever and shivering')
    assert route_en == 'GENERAL_MEDICINE'

    assert _best_department_match('general physician', departments) == 'General Medicine'
    assert _best_department_match('fever doctor', departments) == 'General Medicine'

    doctors = ['Dr Amit Kumar', 'Dr Sweta Sharma']
    assert _best_doctor_match('Amit ji', doctors) == 'Dr Amit Kumar'
    assert _best_doctor_match('Doctor Amit', doctors) == 'Dr Amit Kumar'


@pytest.mark.asyncio
async def test_scenario_4_mid_call_change_of_doctor_and_date() -> None:
    token_amit = 'signed-offer-amit-mon'
    token_sweta = 'signed-offer-sweta-wed'
    confirmed_tokens: list[str] = []

    async def prepare() -> dict[str, object]:
        return {
            'ok': True,
            'offer_token': token_sweta,
            'offer': {**DEMO_OFFER, 'doctor_name': 'Dr Sweta', 'day': 'Wednesday'},
        }

    async def confirm(offer_token: str) -> dict[str, object]:
        confirmed_tokens.append(offer_token)
        return {'ok': True, 'booking_reference': 'GM-SWETA-404', 'status': 'CONFIRMED'}

    tools = [
        StructuredTool.from_function(
            coroutine=prepare,
            name='prepare_booking_offer',
            description='Prepare offer.',
            args_schema=_EmptyInput,
        ),
        StructuredTool.from_function(
            coroutine=confirm,
            name='confirm_booking_offer',
            description='Confirm offer.',
            args_schema=_ConfirmOfferInput,
        ),
    ]

    model = _FakeModel(
        [
            AIMessage(
                content='',
                tool_calls=[
                    {'name': 'prepare_booking_offer', 'args': {}, 'id': 't1', 'type': 'tool_call'}
                ],
            ),
            AIMessage(content='Theek hai, Dr. Sweta ka Wednesday subah 11 baje ka slot hold kar diya hai. Confirm karoon?'),
            AIMessage(
                content='',
                tool_calls=[
                    {'name': 'confirm_booking_offer', 'args': {}, 'id': 't2', 'type': 'tool_call'}
                ],
            ),
            AIMessage(content='Dr. Sweta ka appointment confirm ho gaya hai.'),
        ]
    )

    graph = build_graph(cast(Any, model), tools, checkpointer=InMemorySaver())
    config = {'configurable': {'thread_id': 'scenario-4-thread'}}

    state = await graph.ainvoke(
        {
            'messages': [HumanMessage(content='Nahi, Dr Amit nahi, Dr Sweta ka kar do Wednesday ko')],
            'tool_calls': 0,
            'active_offer_token': token_amit,
            'offer_version': hashlib.sha256(token_amit.encode()).hexdigest(),
        },
        config=config,
    )

    assert state['active_offer_token'] == token_sweta
    assert state['offer_version'] == hashlib.sha256(token_sweta.encode()).hexdigest()

    confirm_state = await graph.ainvoke(
        {'messages': [HumanMessage(content='Haan Dr Sweta ka confirm kar do')], 'tool_calls': 0},
        config=config,
    )

    assert confirmed_tokens == [token_sweta]
    assert confirm_state['active_offer_token'] is None


def test_scenario_5_emergency_symptom_trigger_stops_booking() -> None:
    urgent_prompts = [
        'Mere seene mein tez dard ho raha hai',
        'Patient is unconscious and not waking up',
        'Bahut zyada khoon beh raha hai',
        'Severe chest pain and difficulty breathing',
        'Saans nahi aa rahi hai',
    ]

    for prompt in urgent_prompts:
        assert _problem_route(prompt) == 'URGENT', f'Failed for prompt: {prompt}'

    assert 'Urgent safety' in SYSTEM_INSTRUCTIONS
    assert 'emergency' in SYSTEM_INSTRUCTIONS
    assert 'ambulance' in SYSTEM_INSTRUCTIONS


@pytest.mark.asyncio
async def test_scenario_6_telephony_retry_and_disconnection_idempotency() -> None:
    token = 'offer-token-idempotent'
    confirmed_calls = 0

    async def confirm(offer_token: str) -> dict[str, object]:
        nonlocal confirmed_calls
        confirmed_calls += 1
        return {'ok': True, 'booking_reference': 'GM-REPEAT-606', 'status': 'CONFIRMED'}

    tool = StructuredTool.from_function(
        coroutine=confirm,
        name='confirm_booking_offer',
        description='Confirm offer.',
        args_schema=_ConfirmOfferInput,
    )

    model = _FakeModel(
        [
            AIMessage(
                content='',
                tool_calls=[{'name': 'confirm_booking_offer', 'args': {}, 'id': 't1', 'type': 'tool_call'}],
            ),
            AIMessage(
                content='',
                tool_calls=[{'name': 'confirm_booking_offer', 'args': {}, 'id': 't2', 'type': 'tool_call'}],
            ),
            AIMessage(content='Appointment pehle hi verify aur confirm hai.'),
        ]
    )

    graph = build_graph(cast(Any, model), [tool], checkpointer=InMemorySaver())
    config = {'configurable': {'thread_id': 'scenario-6-thread'}}

    s1 = await graph.ainvoke(
        {
            'messages': [HumanMessage(content='Haan confirm kar do')],
            'tool_calls': 0,
            'active_offer_token': token,
            'turn_number': 1, 'offer_presented_turn': 1,
            'offer_version': hashlib.sha256(token.encode()).hexdigest(),
        },
        config=config,
    )
    assert confirmed_calls == 1
    assert s1['active_offer_token'] is None
    assert s1['consent_version'] == hashlib.sha256(token.encode()).hexdigest()

    s2 = await graph.ainvoke(
        {'messages': [HumanMessage(content='Haan kar do')], 'tool_calls': 0},
        config=config,
    )
    assert confirmed_calls == 1
    tool_msgs = [m for m in s2['messages'] if isinstance(m, ToolMessage)]
    assert any('No active booking offer found' in str(m.content) for m in tool_msgs)
