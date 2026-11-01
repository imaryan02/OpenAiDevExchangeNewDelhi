"""Optional AI supervisor selects only a bounded operational check."""

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from app.core.config import Settings
from app.core.errors import ApiError

TaskKind = Literal[
    "RESOURCE_RECHECK", "MATCHING_REVIEW", "COORDINATION_FOLLOWUP", "HUMAN_REVIEW"
]


class SupervisorChoice(BaseModel):
    kind: TaskKind


async def choose_task(
    settings: Settings, *, status: str, requirement: str,
    recent_events: list[str],
) -> SupervisorChoice:
    if not settings.openai_api_key or not settings.openai_model:
        raise ApiError("SUPERVISOR_NOT_CONFIGURED", "AI supervisor is not configured.", 503)
    model = ChatOpenAI(
        api_key=SecretStr(settings.openai_api_key), model=settings.openai_model,
        temperature=0, timeout=15, max_retries=0, max_completion_tokens=90,
        use_responses_api=True, store=False,
    )
    prompt = [
        SystemMessage(content=(
            "You are the HospitalOS synthetic-demo operations supervisor. Select exactly one "
            "bounded task kind for staff to review. Resource recheck checks Geeta readiness; "
            "matching review compares synthetic candidates; coordination follow-up checks "
            "request state; human review flags an exception. Never diagnose, triage, accept, "
            "decline, direct transport, or claim admission. No patient identity is provided."
        )),
        HumanMessage(content=(
            f"Request status: {status}; known resource requirement: {requirement}; "
            f"recent event types: {', '.join(recent_events[-8:]) or 'none'}."
        )),
    ]
    try:
        result = await model.with_structured_output(SupervisorChoice).ainvoke(prompt)
        return SupervisorChoice.model_validate(result)
    except Exception as exc:
        raise ApiError(
            "SUPERVISOR_UNAVAILABLE", "AI supervisor could not choose a task.", 503
        ) from exc
