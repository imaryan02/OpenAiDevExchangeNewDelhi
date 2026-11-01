"""Bounded recent context and exact-session memory; no external model calls."""

import json
from pathlib import Path
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.errors import ApiError
from app.personal_agent.config import PersonalSettings
from app.personal_agent.domain import FINAL_EVENTS, utcnow
from app.personal_agent.repository import PersonalRepository


async def bound_call(repo: PersonalRepository, call_id: UUID, generation: int) -> dict[str, Any]:
    """Caller is server-bound; reject old sessions after a reset before reading state."""
    profile = await repo.profile(lock=True)
    if profile["generation"] != generation:
        raise ApiError("PERSONAL_SESSION_STALE", "Personal demo was reset; end this session.", 409)
    result = await repo.session.execute(
        text("""select * from public.personal_agent_calls
                where owner_id=:owner and id=:call and generation=:generation
                and status='active' for update"""),
        {"owner": repo.owner_id, "call": call_id, "generation": generation},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise ApiError("PERSONAL_CALL_UNAVAILABLE", "This personal call is not active.", 409)
    return dict(row)


async def save_exchange(
    repo: PersonalRepository,
    config: PersonalSettings,
    *,
    call_id: UUID,
    generation: int,
    source_id: str,
    speaker: Literal["caller", "assistant"],
    content: str,
) -> None:
    """Store final transcript items only, before ending the call; duplicate items are ignored.

    The transport supplies the call/source/speaker, never the language model.
    The caller commits the transaction. Do not store partial audio transcriptions.
    """
    if speaker not in {"caller", "assistant"} or not source_id or len(source_id) > 200:
        raise ValueError("Invalid transcript source")
    content = content.strip()
    if not content:
        return
    await bound_call(repo, call_id, generation)
    await repo.session.execute(
        text("""insert into public.personal_agent_memory
                (owner_id,call_id,generation,source_id,speaker,content,expires_at)
                values (:owner,:call,:generation,:source,:speaker,:content,
                        now()+make_interval(days=>:days))
                on conflict (call_id,source_id,speaker) do nothing"""),
        {
            "owner": repo.owner_id,
            "call": call_id,
            "generation": generation,
            "source": source_id,
            "speaker": speaker,
            "content": content[:2000],
            "days": config.memory_days,
        },
    )


async def prune_expired(repo: PersonalRepository) -> None:
    """Owner-scoped cleanup for the future worker; unresolved events are never removed."""
    await repo.session.execute(
        text(
            "delete from public.personal_agent_memory where owner_id=:owner and expires_at<=now()"
        ),
        {"owner": repo.owner_id},
    )


async def assemble_context(
    repo: PersonalRepository,
    *,
    linked_event_id: UUID | None = None,
    callback_enabled: bool = False,
) -> dict[str, Any]:
    profile = await repo.profile()
    tasks = await repo.tasks(today_only=True)
    result = await repo.session.execute(
        text("""select * from public.personal_agent_followups where owner_id=:owner
                and generation=:generation and status not in ('resolved','cancelled')
                order by (id=:linked) desc nulls last,next_action_at nulls last,created_at,id
                limit 11"""),
        {"owner": repo.owner_id, "generation": profile["generation"], "linked": linked_event_id},
    )
    events = [dict(row) for row in result.mappings()]
    linked_event = None
    if linked_event_id:
        linked = await repo.session.execute(
            text("""select id,title,context,task_snapshot,status,version,created_at
                    from public.personal_agent_followups where owner_id=:owner
                    and generation=:generation and id=:id"""),
            {"owner": repo.owner_id, "generation": profile["generation"], "id": linked_event_id},
        )
        row = linked.mappings().one_or_none()
        if row is None:
            raise ApiError("FOLLOWUP_UNAVAILABLE", "The linked update is unavailable.", 409)
        linked_event = dict(row)
        linked_event["context"] = linked_event["context"][:600]
        linked_event["task_snapshot"] = linked_event["task_snapshot"][:20]
    memories = await repo.collections("memory", limit=13)
    now = utcnow()
    context: dict[str, Any] = {
        "time": now.isoformat(),
        "local_date": now.astimezone(ZoneInfo(profile["timezone"])).date().isoformat(),
        "timezone": profile["timezone"],
        "language": profile["language"],
        "linked_event_id": str(linked_event_id) if linked_event_id else None,
        "linked_event": linked_event,
        "capabilities": {"automatic_callback": callback_enabled, "whatsapp_send": False},
        "tasks": [
            {key: row[key] for key in ("id", "title", "status", "version", "due_at")}
            for row in tasks[:20]
        ],
        "pending_events": [
            {
                key: row[key]
                for key in ("id", "title", "context", "status", "version", "next_action_at")
            }
            for row in events[:10]
            if row["status"] not in FINAL_EVENTS
        ],
        "recent_exchanges": [
            {key: row[key] for key in ("call_id", "speaker", "content", "created_at")}
            for row in reversed(memories[:12])
        ],
        "truncated": len(tasks) > 20 or len(events) > 10 or len(memories) > 12,
    }
    # Text fields and total serialized context both have explicit budgets.
    for row in context["pending_events"]:
        row["context"] = row["context"][:600]
    for row in context["recent_exchanges"]:
        row["content"] = row["content"][:600]
    while len(json.dumps(context, default=str, ensure_ascii=False)) > 16000:
        context["truncated"] = True
        for key in ("recent_exchanges", "tasks", "pending_events"):
            if context[key]:
                context[key].pop(0 if key == "recent_exchanges" else -1)
                break
        else:
            break
    return context


def instructions(context: dict[str, Any]) -> str:
    # UTF-8 resource is shipped with the Python package (see package-data).
    prompt = Path(__file__).with_name("prompt.txt").read_text(encoding="utf-8")
    return (
        prompt + "\nPERSONAL_CONTEXT_JSON:\n" + json.dumps(context, default=str, ensure_ascii=False)
    )
