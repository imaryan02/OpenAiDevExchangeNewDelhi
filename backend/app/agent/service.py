import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.dialogue import confirmation_reply
from app.agent.graph import build_graph, build_tools
from app.agent.tools import ToolExecutor
from app.core.config import Settings
from app.core.errors import ApiError


class ReceptionAgent:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = (
            ChatOpenAI(
                api_key=SecretStr(settings.openai_api_key),
                model=settings.openai_model,
                temperature=0,
                timeout=20,
                max_retries=0,
                max_completion_tokens=180,
                use_responses_api=True,
                store=False,
            )
            if settings.openai_api_key and settings.openai_model
            else None
        )

    async def respond(
        self,
        message: str,
        session: AsyncSession,
        organization_id: UUID,
        actor_id: UUID,
        thread_id: UUID,
        caller_phone: str | None = None,
        on_lookup_start: Callable[[], None] | None = None,
        booking_source: str = "AI_TEXT",
        booking_consent_channel: str = "AI_TEXT",
        allow_appointment_mutations: bool = True,
    ) -> dict[str, object]:
        if self._model is None:
            raise ApiError(
                code="AI_NOT_CONFIGURED",
                message="Add OPENAI_API_KEY and OPENAI_MODEL to backend/.env.",
                status_code=503,
            )

        executor = ToolExecutor(
            session,
            organization_id,
            actor_id=actor_id,
            settings=self._settings,
            caller_phone_e164=caller_phone,
            booking_source=booking_source,
            booking_consent_channel=booking_consent_channel,
            allow_appointment_mutations=allow_appointment_mutations,
        )
        graph = build_graph(
            self._model,
            build_tools(executor),
            on_lookup_start=on_lookup_start,
            execute_operation=executor.execute,
        )
        config: dict[str, Any] = {
            "configurable": {
                "thread_id": f"{organization_id}:{actor_id}:{thread_id}",
            },
            "recursion_limit": 12,
        }
        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=message)], "tool_calls": 0},
                config=config,
            )
        except Exception as error:
            raise ApiError(
                code="AI_PROVIDER_ERROR",
                message="The AI provider could not complete this request.",
                status_code=502,
            ) from error

        messages = result.get("messages", [])
        confirmation = result.get("current_confirmation")
        ai_reply = next(
            (
                self._message_text(item)
                for item in reversed(messages)
                if isinstance(item, AIMessage) and not item.tool_calls
            ),
            "",
        )
        reply = ai_reply or (confirmation_reply(confirmation) if confirmation is not None else "")
        return {
            "reply": reply or "I could not prepare a response. Please try again.",
            "model": self._settings.openai_model,
            "usage_records": self._usage_records(messages),
            "tool_calls": int(result.get("tool_calls", 0)),
            "thread_id": str(thread_id),
            "orchestrator": "langgraph",
            "data_changed": confirmation is not None and confirmation.get("ok") is True,
        }

    def _usage_records(self, messages: list[AnyMessage]) -> list[dict[str, Any]]:
        from app.observability.usage import openai_usage_record

        records = []
        for message in messages:
            if not isinstance(message, AIMessage) or message.usage_metadata is None:
                continue
            response_metadata = message.response_metadata
            request_id = response_metadata.get("id") if isinstance(response_metadata, dict) else None
            provider_id = isinstance(request_id, str) and bool(request_id)
            if not provider_id:
                request_id = str(uuid4())
            model = (
                response_metadata.get("model_name")
                if isinstance(response_metadata, dict) else None
            ) or self._settings.openai_model
            if not isinstance(model, str) or not model:
                continue
            record = openai_usage_record(
                operation="agent_response", model=model, request_id=str(request_id),
                identity_source="provider" if provider_id else "local",
                usage=message.usage_metadata,
            )
            if record:
                records.append(record)
        return records

    @staticmethod
    def _confirmation_payload(messages: list[AnyMessage]) -> dict[str, object] | None:
        # Only the latest caller turn may cause a refresh or confirmation reply.
        last_human = next(
            (i for i in range(len(messages) - 1, -1, -1) if messages[i].type == "human"), -1
        )
        confirmation = next(
            (
                message
                for message in reversed(messages[last_human + 1 :])
                if isinstance(message, ToolMessage) and message.name == "confirm_booking_offer"
            ),
            None,
        )
        if confirmation is None or not isinstance(confirmation.content, str):
            return None
        try:
            payload = json.loads(confirmation.content)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    @staticmethod
    def _deterministic_tool_reply(messages: list[AnyMessage]) -> str:
        payload = ReceptionAgent._confirmation_payload(messages)
        if payload is None:
            return ""
        return confirmation_reply(payload)

    @staticmethod
    def _message_text(message: AIMessage) -> str:
        if isinstance(message.content, str):
            return message.content.strip()
        parts = [
            str(block.get("text", ""))
            for block in message.content
            if isinstance(block, dict) and block.get("type") in {"text", "output_text"}
        ]
        return "\n".join(part for part in parts if part).strip()
