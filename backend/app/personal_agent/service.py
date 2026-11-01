"""Transaction boundary for the future voice transport; no browser-selected owner."""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.errors import ApiError
from app.personal_agent.config import PersonalSettings
from app.personal_agent.memory import assemble_context, bound_call, instructions, save_exchange
from app.personal_agent.messaging import PersonalMessenger
from app.personal_agent.repository import PersonalRepository
from app.personal_agent.tools import PersonalTools, tool_definitions


class PersonalRuntime:
    """Construct only after the gateway authenticates and persists the personal call.

    Each operation owns a fresh short transaction. Returned tool success has
    committed already; SQL/network errors propagate and must never be spoken as success.
    No SQL transaction stays open during voice playback or external model calls.
    """

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        config: PersonalSettings,
        *,
        call_id: UUID,
        generation: int,
    ) -> None:
        if not config.enabled or config.owner_id is None:
            raise ApiError("PERSONAL_DISABLED", "Personal owner/runtime is not configured.", 503)
        self.sessions = sessions
        self.config = config
        self.owner_id = config.owner_id
        self.call_id = call_id
        self.generation = generation

    async def prepare(self) -> dict[str, Any]:
        async with self.sessions.begin() as session:
            repo = PersonalRepository(session, self.owner_id)
            call = await bound_call(repo, self.call_id, self.generation)
            context = await assemble_context(
                repo,
                linked_event_id=call["followup_id"],
                callback_enabled=self.config.scheduler_enabled and self.config.outbound_enabled,
            )
            context["call_direction"] = call["direction"]
            whatsapp_available = (
                self.config.whatsapp_enabled and get_settings().twilio_whatsapp_configured
                and bool(get_settings().public_backend_url)
            )
            context["capabilities"]["whatsapp_send"] = whatsapp_available
            return {"instructions": instructions(context),
                    "tools": tool_definitions(whatsapp_available=whatsapp_available)}

    async def execute(
        self, request_id: str, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if name == "send_whatsapp_update":
            messenger = PersonalMessenger(
                self.sessions, get_settings(), self.config,
                owner_id=self.owner_id, call_id=self.call_id,
                generation=self.generation,
            )
            return await messenger.send(request_id, arguments)
        async with self.sessions.begin() as session:
            executor = PersonalTools(
                PersonalRepository(session, self.owner_id),
                call_id=self.call_id,
                generation=self.generation,
                config=self.config,
            )
            result = await executor.execute(request_id, name, arguments)
        return result

    async def remember(
        self, *, source_id: str, speaker: Literal["caller", "assistant"], content: str
    ) -> None:
        async with self.sessions.begin() as session:
            await save_exchange(
                PersonalRepository(session, self.owner_id),
                self.config,
                call_id=self.call_id,
                generation=self.generation,
                source_id=source_id,
                speaker=speaker,
                content=content,
            )
