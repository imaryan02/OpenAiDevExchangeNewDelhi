# Personal AI / Friday demo module

Status: isolated data/API foundation, dashboard and personal prompt/tools/memory
runtime plus VoiceLink inbound and outbound wiring implemented locally. Live call
acceptance, scheduler execution and WhatsApp delivery remain pending.

This folder contains the agreed product direction and delivery plan for a separate
Personal AI demo inside the existing AI Receptionist repository.

Friday is a natural voice assistant with tasks, recent interaction memory and
persistent follow-up events. An event can continue across incoming calls, scheduled
callbacks, unanswered attempts and WhatsApp messages. Conversation examples are
illustrations, not fixed scripts or mandatory dialogue sequences.

The existing inbound number is retained. With Personal AI mode enabled, only the
registered demo caller reaches Friday. Other callers reach the receptionist.
Mode is selected once per call. Personal AI data is separate from clinic data.

## Planning documents

- [Phase plan and progress checklist](docs/IMPLEMENTATION_PLAN.md)
- [Database isolation and separate tables](docs/SCHEMA_ISOLATION.md)
- [Foundation setup and current limitations](docs/SETUP.md)

## Planned implementation boundaries

- Backend: `backend/app/personal_agent/`, including its own API routes, prompt,
  tools, domain services, persistence, voice session and worker.
- Frontend: `frontend/src/personal-agent/`, including its dashboard, API client,
  types and scoped styles.
- Tests: `backend/tests/personal_agent/` and
  `frontend/tests/personal-agent.test.mjs`.
- SQL: uniquely versioned `personal_agent_*` migrations and verification files
  in the existing `supabase/migrations/` and `supabase/verification/` directories.
- Documentation and eventual demo utilities: this `personal-agent/` folder.

Implementation code stays in the existing build roots so the current Docker,
Python packaging and Vite deployment can include it. This planning folder is not
a second application or deployment.

Shared changes should be limited to route registration, call dispatch, additive
settings, worker startup/shutdown and the frontend demo entry. No receptionist
prompt, tools or appointment state should be repurposed for Friday.
