"""Personal persistence. Every query is bound to an owner; no clinic SQL lives here."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.personal_agent.schemas import ProfileInput, ReminderInput, TaskInput, TaskUpdate

Collection = Literal["followups", "calls", "attempts", "messages", "events", "memory"]


class PersonalRepository:
    def __init__(self, session: AsyncSession, owner_id: UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    async def profile(self, *, lock: bool = False) -> dict[str, Any]:
        suffix = " for update" if lock else ""
        result = await self.session.execute(
            text("select * from public.personal_agent_profiles where owner_id=:owner" + suffix),
            {"owner": self.owner_id},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError("PERSONAL_PROFILE_REQUIRED", "Register your personal phone first.", 409)
        return dict(row)

    async def activity(
        self,
        kind: str,
        description: str,
        *,
        followup_id: UUID | None = None,
        call_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self.session.execute(
            text(
                """insert into public.personal_agent_events
               (owner_id,generation,event_type,description,metadata,followup_id,call_id)
               select owner_id,generation,:kind,:description,
                      cast(:metadata as jsonb),:followup,:call
               from public.personal_agent_profiles where owner_id=:owner"""
            ),
            {
                "owner": self.owner_id,
                "kind": kind,
                "description": description,
                "metadata": json.dumps(metadata or {}),
                "followup": followup_id,
                "call": call_id,
            },
        )

    async def save_profile(self, data: ProfileInput) -> dict[str, Any]:
        existing = await self.session.execute(
            text("select * from public.personal_agent_profiles where owner_id=:owner for update"),
            {"owner": self.owner_id},
        )
        previous = existing.mappings().one_or_none()
        if previous is not None and previous["phone_e164"] != data.phone_e164:
            # A pending callback must not silently move to a newly entered destination.
            pending = await self.session.execute(
                text(
                    """select exists(select 1 from public.personal_agent_followups
                   where owner_id=:owner and status not in ('resolved','cancelled'))
                   or exists(select 1 from public.personal_agent_calls
                   where owner_id=:owner and status='active')"""
                ),
                {"owner": self.owner_id},
            )
            if pending.scalar_one():
                raise ApiError(
                    "PERSONAL_PHONE_IN_USE",
                    "Finish or cancel pending work before changing phone.",
                    409,
                )
        params = {"owner": self.owner_id, **data.model_dump()}
        await self.session.execute(
            text(
                """insert into public.personal_agent_profiles
               (owner_id,phone_e164,timezone,language,whatsapp_fallback)
               values (:owner,:phone_e164,:timezone,:language,:whatsapp_fallback)
               on conflict (owner_id) do update set phone_e164=excluded.phone_e164,
               timezone=excluded.timezone,language=excluded.language,
               whatsapp_fallback=excluded.whatsapp_fallback,updated_at=now(),
               mode=case when personal_agent_profiles.phone_e164=excluded.phone_e164
                         then personal_agent_profiles.mode else 'receptionist' end"""
            ),
            params,
        )
        await self.activity("profile_updated", "Personal profile saved")
        return await self.profile()

    async def set_mode(self, mode: str) -> dict[str, Any]:
        await self.profile(lock=True)
        await self.session.execute(
            text(
                """update public.personal_agent_profiles set mode=:mode,updated_at=now()
               where owner_id=:owner"""
            ),
            {"owner": self.owner_id, "mode": mode},
        )
        await self.activity("mode_updated", f"New-call mode set to {mode}")
        return await self.profile()

    async def tasks(self, *, today_only: bool = False) -> list[dict[str, Any]]:
        profile = await self.profile()
        end_of_day = (
            datetime.now(ZoneInfo(profile["timezone"])).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            + timedelta(days=1)
        ).astimezone(UTC)
        result = await self.session.execute(
            text(
                """select * from public.personal_agent_tasks where owner_id=:owner
               and deleted_at is null
               and (not :today_only or (status='pending' and (due_at is null or due_at<:until)))
               order by status desc,due_at nulls last,created_at,id limit 200"""
            ),
            {"owner": self.owner_id, "today_only": today_only, "until": end_of_day},
        )
        return [dict(row) for row in result.mappings()]

    async def create_task(self, data: TaskInput) -> dict[str, Any]:
        await self.profile(lock=True)
        result = await self.session.execute(
            text(
                """insert into public.personal_agent_tasks (owner_id,title,description,due_at)
               values (:owner,:title,:description,:due_at) returning *"""
            ),
            {"owner": self.owner_id, **data.model_dump()},
        )
        task = dict(result.mappings().one())
        await self.activity("task_created", f"Task added: {task['title']}")
        return task

    async def update_task(self, task_id: UUID, data: TaskUpdate) -> dict[str, Any]:
        await self.profile(lock=True)
        result = await self.session.execute(
            text(
                """update public.personal_agent_tasks set title=:title,description=:description,
               due_at=:due_at,status=:status,
               completed_at=case when :status='completed' then coalesce(completed_at,now())
                                 else null end,version=version+1,updated_at=now()
               where owner_id=:owner and id=:id and version=:version and deleted_at is null
               returning *"""
            ),
            {"owner": self.owner_id, "id": task_id, **data.model_dump()},
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(
                "TASK_CHANGED", "Task is unavailable or changed. Refresh and retry.", 409
            )
        task = dict(row)
        await self.activity("task_updated", f"Task {task['status']}: {task['title']}")
        return task

    async def delete_task(self, task_id: UUID, version: int) -> None:
        await self.profile(lock=True)
        result = await self.session.execute(
            text(
                """update public.personal_agent_tasks set deleted_at=now(),updated_at=now(),
               version=version+1 where owner_id=:owner and id=:id and version=:version
               and deleted_at is null returning title"""
            ),
            {"owner": self.owner_id, "id": task_id, "version": version},
        )
        title = result.scalar_one_or_none()
        if title is None:
            raise ApiError(
                "TASK_CHANGED", "Task is unavailable or changed. Refresh and retry.", 409
            )
        await self.activity("task_deleted", f"Task removed: {title}")

    async def collections(
        self,
        collection: Collection,
        *,
        before: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        # Collection comes from module code, never arbitrary client SQL identifiers.
        allowed = {"followups", "calls", "attempts", "messages", "events", "memory"}
        if collection not in allowed:
            raise ValueError("Unknown personal collection")
        profile = await self.profile()
        extra = ""
        if collection == "memory":
            extra = " and expires_at>now()"
        if collection == "events" and before is not None:
            extra += " and id<:before"
        order = (
            "id"
            if collection in {"events", "memory"}
            else ("started_at" if collection == "calls" else "created_at")
        )
        result = await self.session.execute(
            text(
                f"select * from public.personal_agent_{collection} where owner_id=:owner "
                f"and generation=:generation{extra} order by {order} desc limit :limit"
            ),
            {
                "owner": self.owner_id,
                "generation": profile["generation"],
                "before": before,
                "limit": limit,
            },
        )
        return [dict(row) for row in result.mappings()]

    async def create_followup(
        self, data: ReminderInput, *, snapshot_today: bool = True
    ) -> dict[str, Any]:
        profile = await self.profile(lock=True)
        tasks = await self.tasks(today_only=True) if snapshot_today else []
        if data.task_ids:
            all_tasks = await self.tasks()
            chosen = {task["id"]: task for task in all_tasks if task["id"] in data.task_ids}
            if set(chosen) != set(data.task_ids):
                raise ApiError("TASK_NOT_FOUND", "A selected task is unavailable.", 404)
            tasks = list(chosen.values())
        snapshot = [
            {"id": str(task["id"]), "title": task["title"], "status": task["status"]}
            for task in tasks[:20]
        ]
        result = await self.session.execute(
            text(
                """insert into public.personal_agent_followups
               (owner_id,generation,title,context,task_snapshot,next_action,next_action_at)
               values (:owner,:generation,:title,:context,cast(:snapshot as jsonb),'call',
                       now()+make_interval(secs=>:delay)) returning *"""
            ),
            {
                "owner": self.owner_id,
                "generation": profile["generation"],
                "title": data.title,
                "context": data.context,
                "snapshot": json.dumps(snapshot),
                "delay": data.delay_seconds,
            },
        )
        followup = dict(result.mappings().one())
        await self.activity(
            "reminder_created", f"Reminder saved: {data.title}", followup_id=followup["id"]
        )
        return followup

    async def followup_action(
        self,
        event_id: UUID,
        version: int,
        action: str,
        delay: int | None,
    ) -> dict[str, Any]:
        profile = await self.profile(lock=True)
        if action == "reschedule" and delay is None:
            raise ApiError("CALLBACK_TIME_REQUIRED", "Choose when Friday should call.", 422)
        status = {"cancel": "cancelled", "acknowledge": "resolved", "reschedule": "scheduled"}[
            action
        ]
        result = await self.session.execute(
            text(
                """update public.personal_agent_followups set status=:status,
               next_action=case when :status='scheduled' then 'call' else null end,
               next_action_at=case when :status='scheduled'
                    then now()+make_interval(secs=>:delay) else null end,
               resolution=:resolution,version=version+1,lease_token=null,lease_until=null,
               call_attempts=case when :status='scheduled' then 0 else call_attempts end,
               updated_at=now() where owner_id=:owner and id=:id and generation=:generation
               and version=:version and status not in ('resolved','cancelled') returning *"""
            ),
            {
                "owner": self.owner_id,
                "generation": profile["generation"],
                "id": event_id,
                "version": version,
                "status": status,
                "delay": delay or 0,
                "resolution": None if status == "scheduled" else f"user_{action}",
            },
        )
        row = result.mappings().one_or_none()
        if row is None:
            raise ApiError("FOLLOWUP_CHANGED", "Follow-up is unavailable or changed.", 409)
        event = dict(row)
        await self.activity(
            f"followup_{action}", f"Follow-up {status}: {event['title']}", followup_id=event_id
        )
        return event

    async def seed(self) -> int:
        await self.profile(lock=True)
        existing = {task["title"] for task in await self.tasks()}
        count = 0
        for title in (
            "Complete AI presentation",
            "Review demo flow",
            "Send project report",
            "Prepare meeting notes",
        ):
            if title not in existing:
                await self.create_task(TaskInput(title=title))
                count += 1
        await self.activity("demo_seeded", f"Added {count} rehearsal tasks")
        return count

    async def reset(self) -> None:
        await self.profile(lock=True)
        active = await self.session.execute(
            text(
                """select exists(select 1 from public.personal_agent_calls where owner_id=:owner
               and status='active' and heartbeat_at>now()-interval '60 seconds')
               or exists(select 1 from public.personal_agent_attempts where owner_id=:owner
               and status in ('submitting','accepted','ringing','in-progress','unknown'))
               or exists(select 1 from public.personal_agent_messages where owner_id=:owner
               and status in ('submitting','accepted','sending','sent','unknown'))"""
            ),
            {"owner": self.owner_id},
        )
        if active.scalar_one():
            raise ApiError(
                "DEMO_ACTION_ACTIVE", "Finish active calls or deliveries before reset.", 409
            )
        # Retain provider history; hide prior generations and invalidate queued tools/work.
        await self.session.execute(
            text(
                """update public.personal_agent_followups set status='cancelled',next_action=null,
               next_action_at=null,lease_token=null,lease_until=null,version=version+1,
               resolution='demo_reset',updated_at=now()
               where owner_id=:owner and status not in ('resolved','cancelled')"""
            ),
            {"owner": self.owner_id},
        )
        await self.session.execute(
            text(
                """update public.personal_agent_tasks set deleted_at=now(),version=version+1
               where owner_id=:owner and deleted_at is null"""
            ),
            {"owner": self.owner_id},
        )
        await self.session.execute(
            text("delete from public.personal_agent_memory where owner_id=:owner"),
            {"owner": self.owner_id},
        )
        await self.session.execute(
            text(
                """update public.personal_agent_profiles set generation=generation+1,
               mode='receptionist',updated_at=now() where owner_id=:owner"""
            ),
            {"owner": self.owner_id},
        )
        await self.activity("demo_reset", "Demo reset; incoming calls use Receptionist")
