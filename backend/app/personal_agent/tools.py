"""Transport-independent personal tools. One transaction per call-bound invocation.

The voice gateway will supply call/owner/generation/request IDs. Callers MUST
commit before publishing results and roll back unexpected exceptions. No network
side effects occur here. Profile locking serializes duplicate requests and reset.
"""

import hashlib
import json
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from pydantic import Field, ValidationError
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import ApiError
from app.personal_agent.config import PersonalSettings
from app.personal_agent.memory import assemble_context, bound_call
from app.personal_agent.repository import PersonalRepository
from app.personal_agent.schemas import Input, ReminderInput, TaskInput, TaskUpdate


class GetTasks(Input):
    today_only: bool = True


class NoArguments(Input):
    pass


class EditTask(Input):
    task_id: UUID
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    due_at: str | None = None


class TaskRef(Input):
    task_id: UUID
    version: int = Field(ge=1)


class EventRef(Input):
    event_id: UUID
    version: int = Field(ge=1)


class Reschedule(EventRef):
    delay_seconds: int = Field(ge=10, le=86400)


class SendWhatsApp(Input):
    event_id: UUID | None = None


CONTRACTS: dict[str, tuple[type[Input], str]] = {
    "get_tasks": (
        GetTasks,
        "Retrieve Aryan's personal tasks when he asks for his schedule, to-do list "
        "or tasks. Today includes overdue and undated pending tasks; also returns "
        "task IDs/versions for edits.",
    ),
    "get_pending_context": (
        NoArguments,
        "Retrieve pending updates, current tasks and bounded recent exchanges.",
    ),
    "create_task": (
        TaskInput,
        "Create the task requested by the owner; dates require an explicit timezone.",
    ),
    "update_task": (
        EditTask,
        "Edit one identified task using its current ID/version. Omitted fields are preserved.",
    ),
    "complete_task": (
        TaskRef,
        "Complete one identified task. Acknowledging a reminder does not complete tasks.",
    ),
    "delete_task": (
        TaskRef,
        "Remove one task explicitly requested by the owner using its current ID/version.",
    ),
    "create_reminder": (
        ReminderInput,
        "Save a callback request with a definite delay and subject. "
        "Execution follows backend capabilities.",
    ),
    "reschedule_reminder": (
        Reschedule,
        "Move an existing update to an explicitly requested delay; avoid duplicate reminders.",
    ),
    "cancel_reminder": (EventRef, "Cancel the owner's explicitly identified pending update."),
    "acknowledge_update": (
        EventRef,
        "Resolve a clear acknowledgment; never on answer, silence, hangup or ambiguous okay.",
    ),
    "send_whatsapp_update": (
        SendWhatsApp,
        "Send the pending update or today's tasks to the registered owner "
        "after an explicit request. Submission is not proof of delivery.",
    ),
}


def tool_definitions(*, whatsapp_available: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": model.model_json_schema(),
        }
        for name, (model, description) in CONTRACTS.items()
        if name != "send_whatsapp_update" or whatsapp_available
    ]


class PersonalTools:
    def __init__(
        self, repo: PersonalRepository, *, call_id: UUID, generation: int, config: PersonalSettings
    ) -> None:
        self.repo = repo
        self.call_id = call_id
        self.generation = generation
        self.config = config

    async def execute(
        self, request_id: str, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if not request_id or len(request_id) > 200:
            raise ApiError("TOOL_REQUEST_INVALID", "Invalid tool request identifier.", 422)
        encoded = json.dumps(
            {"name": name, "arguments": arguments},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        if len(encoded) > 12000:
            raise ApiError("TOOL_INPUT_TOO_LARGE", "Personal tool input is too large.", 422)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        call = await bound_call(self.repo, self.call_id, self.generation)
        stored = await self.repo.session.execute(
            text("""select input_hash,result from public.personal_agent_tool_results
                    where owner_id=:owner and call_id=:call and request_id=:request"""),
            {"owner": self.repo.owner_id, "call": self.call_id, "request": request_id},
        )
        previous = stored.mappings().one_or_none()
        if previous is not None:
            if previous["input_hash"] != digest:
                raise ApiError(
                    "TOOL_REQUEST_REUSED", "Tool request ID was reused with changed input.", 409
                )
            return dict(previous["result"])
        try:
            contract = CONTRACTS.get(name)
            if contract is None:
                raise ApiError("TOOL_UNAVAILABLE", "That personal tool is unavailable.", 422)
            data = contract[0].model_validate(arguments)
            if name == "send_whatsapp_update":
                raise ApiError(
                    "WHATSAPP_RUNTIME_REQUIRED", "WhatsApp sending needs the message runtime.", 503
                )
            # A savepoint prevents a future handler's partial writes surviving a handled error.
            async with self.repo.session.begin_nested():
                result = await self._dispatch(name, data, call)
            response = {"ok": True, "data": jsonable_encoder(result)}
        except ValidationError:
            response = {
                "ok": False,
                "code": "TOOL_ARGUMENT_INVALID",
                "message": "Use valid tool arguments; clarify missing or ambiguous information.",
            }
        except ApiError as error:
            response = {"ok": False, "code": error.code, "message": error.message}
        await self.repo.session.execute(
            text("""insert into public.personal_agent_tool_results
                    (call_id,owner_id,request_id,input_hash,result)
                    values (:call,:owner,:request,:hash,cast(:result as jsonb))"""),
            {
                "call": self.call_id,
                "owner": self.repo.owner_id,
                "request": request_id,
                "hash": digest,
                "result": json.dumps(response),
            },
        )
        await self.repo.activity(
            "tool_completed" if response["ok"] else "tool_error",
            f"Personal tool: {name[:80]}",
            call_id=self.call_id,
            followup_id=call["followup_id"],
            metadata={
                "tool": name[:80],
                "request_id": request_id,
                "call_id": str(self.call_id),
                "ok": response["ok"],
            },
        )
        return response

    async def _task(self, task_id: UUID, version: int) -> dict[str, Any]:
        result = await self.repo.session.execute(
            text("""select * from public.personal_agent_tasks where owner_id=:owner
                    and id=:id and version=:version and deleted_at is null"""),
            {"owner": self.repo.owner_id, "id": task_id, "version": version},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(
                "TASK_CHANGED", "Task is unavailable or changed; retrieve fresh tasks.", 409
            )
        return dict(row)

    async def _dispatch(self, name: str, data: Input, call: dict[str, Any]) -> Any:
        args = data.model_dump()
        if name == "get_tasks":
            tasks = await self.repo.tasks(today_only=args["today_only"])
            await self.repo.activity("tasks_retrieved", "Friday retrieved personal tasks")
            return {
                "tasks": [
                    {
                        key: row[key]
                        for key in ("id", "title", "description", "status", "due_at", "version")
                    }
                    for row in tasks[:50]
                ],
                "truncated": len(tasks) > 50,
            }
        if name == "get_pending_context":
            context = await assemble_context(
                self.repo,
                linked_event_id=call["followup_id"],
                callback_enabled=self.config.scheduler_enabled and self.config.outbound_enabled,
            )
            settings = get_settings()
            context["capabilities"]["whatsapp_send"] = bool(
                self.config.whatsapp_enabled
                and settings.twilio_whatsapp_configured
                and settings.public_backend_url
            )
            return context
        if name == "create_task":
            return await self.repo.create_task(TaskInput.model_validate(args))
        if name in {"update_task", "complete_task", "delete_task"}:
            task_id, version = args.pop("task_id"), args.pop("version")
            task = await self._task(task_id, version)
            if name == "delete_task":
                await self.repo.delete_task(task_id, version)
                return {"deleted": True, "task_id": task_id}
            updates = {key: task[key] for key in ("title", "description", "due_at", "status")}
            if name == "complete_task":
                updates["status"] = "completed"
            else:
                for key in data.model_fields_set - {"task_id", "version"}:
                    updates[key] = args[key]
            return await self.repo.update_task(
                task_id, TaskUpdate.model_validate({**updates, "version": version})
            )
        if name == "create_reminder":
            event = await self.repo.create_followup(
                ReminderInput.model_validate(args), snapshot_today=False
            )
            await self.repo.session.execute(
                text("""update public.personal_agent_followups set source_call_id=:call
                        where owner_id=:owner and id=:id and generation=:generation"""),
                {
                    "call": self.call_id,
                    "owner": self.repo.owner_id,
                    "id": event["id"],
                    "generation": self.generation,
                },
            )
            return {
                **event,
                "source_call_id": self.call_id,
                "execution_enabled": self.config.scheduler_enabled and self.config.outbound_enabled,
                "execution_note": "Saved; callback follows backend settings.",
            }
        action = {
            "reschedule_reminder": "reschedule",
            "cancel_reminder": "cancel",
            "acknowledge_update": "acknowledge",
        }[name]  # Only allowlisted contracts reach dispatch.
        return await self.repo.followup_action(
            args["event_id"], args["version"], action, args.get("delay_seconds")
        )
