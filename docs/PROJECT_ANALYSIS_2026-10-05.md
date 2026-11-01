# Project analysis for the enterprise voice-agent guide

Repository review: 5 October 2026. Scope: the current working tree, including the existing local Personal Agent diagnostic changes. This is the research record for the proposed 10–12-page guide, not the final publication.

## Evidence and limits

The scan inventories 91 backend Python modules, 24 frontend TypeScript/TSX source files, 35 backend test files, five frontend test files, 23 SQL migrations, and 17 SQL verification files. The migrations define 39 application tables. Seventy HTTP/WebSocket handlers are declared across the main and alternative backend entry points; this is a declaration count, not a claim that every handler is mounted in production.

The review traced application entry points, staff workflows, authentication, database operations, both clinic voice engines, the Personal Agent runtime, provider adapters, background workers, observability, and deployment configuration. Runtime source takes precedence over historical plans and README claims. The owner supplied a context-only table schema after the initial review: its 39 public table names match the migration inventory, including all six observability tables and all nine personal tables. It does not include stored functions, triggers, indexes, RLS policies, grants or migration history, so those live properties remain unverified. No migrations, seeds, live call probes, message sends, or deployments were performed.

| Verification | Result |
| --- | --- |
| Backend unit/regression suite | 312 passed; 15 database integration tests deliberately skipped; five health tests initially encountered a temporary-directory permission error |
| Separate retry of those five health tests | All five passed using a writable artifact directory |
| Ruff | Passed; reported a local cache access warning |
| Mypy | Passed for all 91 backend source modules |
| Frontend Node tests | 28 passed |
| Frontend production build, including TypeScript compilation | Passed; main JavaScript chunk approximately 506 kB, with Vite size warning |
| Owner-supplied Supabase context schema | 39 table names match the repository inventory; table structure is available for documentation |
| Live RLS, functions, indexes, triggers, grants and migration ledger | Absent from the context export; not verified against a database |
| Current deployed call, callback, and delivery acceptance | Not re-tested in this review |

These checks establish local code/build evidence. They do not establish carrier interoperability, live database correctness, or production readiness.

## 1. Two product domains, shared infrastructure

**Geeta Medicine** is an administrative clinic management system: organization configuration, doctors and departments, schedules, availability, caller and family profiles, appointments, visit queues, and call investigation. The voice receptionist adds a telephone interface to those business operations. It is not a diagnostic or treatment system.

**Friday / Personal Agent** manages one configured owner's tasks, reminders, follow-ups, short-term memory, callbacks, and WhatsApp updates. Its tools and tables are separate from the clinic domain.

The products currently share a repository, FastAPI process, React/Vite build, Supabase database, authentication service, and some telephony/audio utilities. `personal-agent/` contains runbooks and operational scripts; its implementation lives inside the existing backend and frontend build roots. Independence here means separate product logic and owner-scoped data, rather than separate deployable applications or separate databases.

An authenticated VoiceLink stream is routed once at call start. A matching registered owner with Personal AI mode enabled reaches Friday; other inbound callers reach the clinic receptionist. Outbound personal calls require a signed attempt binding. An established personal call is not switched to the receptionist when its runtime fails.

Sources: [main API router](E:/Projects/Ai_receptionist/backend/app/api/router.py), [personal routing](E:/Projects/Ai_receptionist/backend/app/personal_agent/routing.py), [browser entry](E:/Projects/Ai_receptionist/frontend/src/main.tsx).

## 2. Technology and responsibility map

Versions below describe repository declarations/configuration, not vendor recommendations or verified production versions.

| Layer | Repository technology | Responsibility |
| --- | --- | --- |
| Staff and personal interfaces | React 18, TypeScript, Vite 8, Fluent UI 9, custom CSS | Forms, workspace navigation, operational views, call review, personal dashboard |
| API/runtime | Python 3.12 container; FastAPI, Uvicorn, Pydantic settings/models | HTTP, WebSocket and SSE interfaces; validation; authorization; asynchronous orchestration |
| Chained/text orchestration | LangChain Core/OpenAI, LangGraph `StateGraph` | Tool-capable text model, dialogue state and explicit confirmation transitions |
| Realtime speech | OpenAI Realtime over server WebSocket | Streaming speech input/output and proposed function calls |
| Separate speech stages | OpenAI transcription and speech HTTP APIs | Chained STT/TTS; also controlled spoken readbacks in the Realtime flow |
| Carrier integration | VoiceLink; additional Twilio paths | Telephone transport, stream metadata, audio playback and callbacks |
| Notifications | Twilio WhatsApp | Clinic outbox notifications and personal updates/fallbacks |
| Persistence | Supabase PostgreSQL; SQLAlchemy async sessions and asyncpg | Business data, stored functions, durable call state, follow-ups, evidence |
| Authentication | Supabase Auth, browser REST requests, backend HTTP/JWT validation | Staff identity and personal owner identity |
| Observability | structlog, correlation IDs, optional OpenTelemetry OTLP, SQL event history | Operational diagnostics, event correlation and provider-reported usage |
| Hosting/build | Docker, GitHub Actions, Azure Container Apps, Vercel | Backend image/deployment, frontend hosting, quality gates |

`@supabase/supabase-js` is declared as a dependency, but the inspected authentication helper uses Supabase Auth REST endpoints directly. Business data flows through FastAPI and direct PostgreSQL sessions; it is not principally a browser-to-Supabase CRUD application.

Configured defaults include `gpt-4o-mini-transcribe`, `gpt-4o-mini-tts`, and `gpt-realtime-2.1`; the text model is environment-configured. Model/voice identifiers should be explained as replaceable configuration, not guaranteed current availability.

Sources: [backend dependencies](E:/Projects/Ai_receptionist/backend/pyproject.toml), [frontend dependencies](E:/Projects/Ai_receptionist/frontend/package.json), [settings](E:/Projects/Ai_receptionist/backend/app/core/config.py), [authentication helper](E:/Projects/Ai_receptionist/frontend/src/lib/supabaseAuth.ts).

## 3. Frontend and business API

The clinic browser entry opens the staff workspace, or the conference view using `?conference`. The separate `/demo/personal-agent` entry lazily loads Friday's dashboard. Clinic navigation is a small browser-history implementation using query parameters, including deep links to individual calls.

| Interface | Business purpose | Backend boundary |
| --- | --- | --- |
| Overview, calendar, appointments | Availability, booking records, cancellations, rescheduling and queue state | Availability and booking routes |
| Booking form | Caller/patient intake, appointment hold, confirmation and payment-method record | `/v1/booking-intake`, hold and confirm operations |
| Patients | Patient/contact records, relationships, edits and removal workflows | Tenant-authorized patient routes |
| Settings, doctors, departments | Organization, branches, assignments, fees, weekly rules and exceptions | Configuration routes; administration checks for writes |
| AI assistant | Staff text conversation with clinic tools | `/v1/agent/chat` and LangGraph |
| Presentation / Observatory | Rehearsal or observed live voice/tool/database activity | Authenticated presentation SSE |
| Call history/investigation | Conversation evidence, operations, performance, usage and diagnostics | Tenant-authorized voice observability API |
| Friday dashboard | Tasks, pending follow-ups, memory, activity, mode selection and preferences | Owner-authorized `/v1/personal-agent` API |

The clinic shell selects the first active organization membership and refreshes availability and appointments every six seconds and on window focus. Friday polls every two seconds while visible, uses server time for countdown alignment, and rejects responses that became stale across mutations or logout. This is polling plus presentation SSE; it should not be described as Supabase Realtime subscriptions.

The shared authenticated-fetch helper retries an expired request once after a coordinated refresh-token exchange. Some older clinic components still issue direct bearer-authenticated `fetch` requests, so refresh behaviour is not uniformly centralized. Browser access and refresh tokens are stored in localStorage.

The backend permits booking staff roles `ORG_ADMIN` and `RECEPTIONIST`; configuration has separate member/admin gates. A `VIEWER` role exists in the model, but the main shell initially loads endpoints requiring booking staff, so the final guide should not promise a complete viewer experience.

Sources: [clinic shell](E:/Projects/Ai_receptionist/frontend/src/App.tsx), [personal dashboard](E:/Projects/Ai_receptionist/frontend/src/personal-agent/PersonalAgentDemo.tsx), [booking API](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py), [configuration API](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py).

## 4. Clinic voice architectures

### Chained path

VoiceLink streams base64 G.711 A-law audio at 8 kHz. The gateway validates stream start metadata, detects speech and silence, assembles a turn, and sends a WAV representation to transcription. It passes text to `ReceptionAgent`, which uses `ChatOpenAI`, structured tools and a LangGraph state graph. The verified tool result informs the reply; separate TTS generates PCM that is converted back to telephone A-law and paced into carrier frames.

The gateway includes bounded turn queues, stale-turn rejection, duplicate transcript and self-echo suppression, speech interruption, lookup fillers, silence handling, and a call-duration limit. LangGraph uses a process-local `InMemorySaver` keyed by organization, actor and thread; this is different from durable PostgreSQL call-operation state.

**Current limitation:** both the VoiceLink Chained gateway and the legacy Twilio clinic gateway call the agent with `allow_appointment_mutations=False`. The executor rejects confirmation, cancellation and rescheduling in this mode because completed readback is not verifiable there. They can discover information and prepare a booking offer; they cannot complete the consequential operation through this current path. The text assistant has a different confirmation boundary and is not subject to that voice-channel flag.

### Realtime path

The backend opens an OpenAI Realtime session and bridges A-law 8 kHz to PCM16 24 kHz. Realtime supplies speech understanding/generation and function calls without routing every audio turn through LangGraph. Semantic VAD detects turn boundaries, while the server controls response creation and interruption handling.

The exposed tool set contains discovery tools, appointment lookup, booking-offer preparation, and cancellation/reschedule preview tools. It does **not** expose the final booking commit as a model function. The gateway validates/allow-lists function names, binds caller identity from carrier metadata, invokes the shared executor, and returns grounded results.

For consequential operations, the backend temporarily uses separate TTS to play a deterministic readback. This makes the implemented Realtime design a streaming conversational path with a controlled transaction boundary. It is not exclusively speech-to-speech for every utterance.

Normal response playback uses a bounded queue and generation/response identifiers. Caller speech clears queued output, cancels/truncates responses, and invalidates interrupted or corrected proposals. Stale asynchronous results are rejected when a newer caller turn supersedes them.

Engine choice is made once from settings and authenticated caller metadata. With a non-empty canary list, listed callers use Realtime and unlisted callers enter Chained before the Realtime session opens. Startup failure does not imply a seamless mid-call switch to another engine.

Sources: [Chained gateway](E:/Projects/Ai_receptionist/backend/app/voice/voicelink_gateway.py), [Realtime gateway](E:/Projects/Ai_receptionist/backend/app/voice/voicelink_realtime_gateway.py), [graph](E:/Projects/Ai_receptionist/backend/app/agent/graph.py), [audio client](E:/Projects/Ai_receptionist/backend/app/integrations/openai_audio.py), [codec](E:/Projects/Ai_receptionist/backend/app/voice/codec.py).

## 5. Booking transaction and consent design

1. The server derives organization/actor and caller phone from configuration plus authenticated stream metadata. The model cannot choose another tenant or substitute another caller number.
2. Discovery tools retrieve actual doctors, departments, sessions and permitted family profiles. Department suggestion is limited administrative keyword routing; it is not a medical reasoning service. Name matching includes normalized/fuzzy matching and ambiguity handling.
3. `prepare_booking_offer` validates the selected patient/session and constructs a signed, five-minute offer carrying identity, schedule, fee, language and a nonce. It does not reserve capacity or commit an appointment. Realtime keeps its token out of the model conversation.
4. `VoiceCallRuntime` persists a proposal bound to a hash/version of that exact offer or operation arguments. The controlled player emits a carrier mark tied to the readback segment.
5. A matching carrier mark is playback-completion evidence. It is not proof that the person understood the content. A later caller turn must start after that completion, refer to the unchanged proposal, and be classified as explicit approval. The intent classifier returns `CONFIRM`, `CHANGE`, `DECLINE`, or `UNCLEAR`; it cannot execute tools and fails closed.
6. Runtime approval, any needed caller/patient creation, the hold/confirmation functions, and the committed operation result execute in the same transaction. Success is published only after commit. Optimistic state versions, ownership tokens and idempotency keys guard duplicate/stale work.
7. A lost commit response is treated as uncertain. Booking reconciliation reads positive committed-operation evidence from a fresh transaction; absence does not authorize blindly replaying the write.
8. Notifications are separate outbox work. A booked appointment and a delivered message are different outcomes.

The SQL layer locks bookable sessions/slots, enforces capacity and uniqueness, verifies tenant-scoped relationships, and records quote/contact/consent snapshots. Rescheduling creates a replacement appointment linked to the original and preserves history; later triggers strengthen target cutoff, active assignment/location, fee/currency and payment-ledger consistency.

The schema retains exact-time slots and token/session windows, but a later migration restricts newly written weekly rules to `SESSION_TOKEN` while preserving historical rows. The guide must distinguish historical schema capability from the current scheduling policy.

Payments are simulated or recorded as due at clinic. Voice offers force CASH and do not collect real payment. `PAYMENT_PENDING` is a technical hold state, not proof that a payment gateway exists.

Sources: [runtime](E:/Projects/Ai_receptionist/backend/app/voice/call_runtime.py), [call domain state](E:/Projects/Ai_receptionist/backend/app/voice/session.py), [executor](E:/Projects/Ai_receptionist/backend/app/agent/tools.py), [consent-aware hold SQL](E:/Projects/Ai_receptionist/supabase/migrations/20260911001300_phase2_quote_consent_snapshots.sql), [reschedule integrity SQL](E:/Projects/Ai_receptionist/supabase/migrations/20260926000100_rescheduling_integrity.sql).

## 6. Supabase model and access boundaries

This inventory is reconstructed from migrations and its table-name set matches the owner-supplied context schema. The supplied representation splits some composite foreign keys into repeated single-column constraint lines and omits other DDL. It is explicitly non-executable and must not be interpreted as a lossless PostgreSQL schema dump or evidence that the actual composite constraints are broken.

| Group | Tables | Role |
| --- | --- | --- |
| Tenant foundation (7) | organizations, locations, departments, doctors, doctor_assignments, organization_users, audit_events | Organization membership, clinical directory and audit primitives |
| Scheduling (4) | schedule_rules, schedule_exceptions, appointment_sessions, appointment_slots | Weekly rules, dated materialization and historical exact slots |
| Caller/patient identity (4) | contacts, contact_phones, patients, patient_contacts | Separates the phone owner/booker from the person attending |
| Appointment operations (4) | appointments, appointment_contact_permissions, verification_challenges, payment_attempts | Booking lifecycle, permitted contacts, OTP-style verification and payment records |
| Transaction coordination (3) | idempotency_records, outbox_jobs, inbox_events | Duplicate protection and provider/notification work |
| Durable clinic voice state (2) | voice_call_sessions, voice_operation_records | Call identity, fenced state versions and consequential-operation evidence |
| Call observability (6) | voice_observability_calls, voice_observability_events, voice_observability_usage, voice_observability_messages, voice_observability_content_access, voice_observability_attempts | Call review, optional content, access audit and usage units |
| Personal Agent (9) | personal_agent_profiles, personal_agent_tasks, personal_agent_followups, personal_agent_calls, personal_agent_attempts, personal_agent_messages, personal_agent_memory, personal_agent_events, personal_agent_tool_results | Owner-scoped Friday domain |

Supabase Auth validates staff identity. With the common URL/publishable-key configuration, the backend calls `/auth/v1/user`; other configurations use supported JWT/JWKS or legacy-secret validation. API authorization then checks active organization membership and role, or the exact configured personal owner.

RLS and composite tenant/owner foreign keys appear throughout the migrations. The backend connects directly to PostgreSQL, however, so the privileges of `DATABASE_URL` matter: an elevated connection can bypass RLS. Parameterized SQL, explicit organization/owner filters, API authorization, and deliberately set actor claims for stored functions are essential boundaries, not optional duplicates of browser RLS.

Personal tables give authenticated owners SELECT access under `owner_id = auth.uid()` and keep writes server-controlled. The current runtime is one configured demo owner, not a finished multi-owner service. Telephony also uses one configured clinic organization/actor; the presence of tenant-scoped clinic tables does not imply a dynamic DID-to-tenant registry.

Two historical migrations share version `20260911001400`. Their filenames are retained and the repository explicitly requires inspecting the live migration ledger before reconciliation. Automated migration push cannot be assumed safe from a clean checkout.

The provided schema is sufficient to describe table groups and the core relationships. Additional live evidence, if exact deployed safeguards are to be certified, would be indexes/triggers, full current function definitions, RLS policies and grants, `supabase_migrations.schema_migrations` contents, and confirmation of the backend connection role without its password. This does not block drafting the guide with those limits stated. No row data is required.

Sources: [migration convention](E:/Projects/Ai_receptionist/supabase/migrations/README.md), [database sessions](E:/Projects/Ai_receptionist/backend/app/db/session.py), [backend auth](E:/Projects/Ai_receptionist/backend/app/security/auth.py), [personal foundation](E:/Projects/Ai_receptionist/supabase/migrations/20260927000500_personal_agent_foundation.sql).

## 7. Friday: persistent work across interactions

Friday has a separate prompt, typed tools, repository, runtime, voice gateways and worker. It uses Realtime; no separate Personal Agent Chained implementation was found. Its tool contracts cover task retrieval/creation/edit/completion/deletion, pending context, reminder creation/rescheduling/cancellation, update acknowledgement, and optional WhatsApp sending.

The server supplies owner, call, reset generation and request ID. Each tool validates a typed schema, checks the active bound call, and persists an input hash/result for duplicate request protection. Task/follow-up versions reject stale edits. Short transactions complete before success is returned; no SQL transaction is deliberately held open while waiting for ordinary model or audio playback work.

Memory is bounded SQL transcript/event context, not vector retrieval, permanent learning or a knowledge-base RAG system. Defaults retain personal exchanges for seven days. Prompt assembly includes current tasks, unresolved events, a linked callback reason and recent exchanges within explicit item/text budgets. Reset increments a generation to invalidate old sessions and work.

The scheduler leases due follow-ups with `FOR UPDATE SKIP LOCKED`, stages an attempt, commits, then submits it through a configured provider adapter. Provider acceptance does not mean the call was answered. A timeout after submission becomes `unknown`/needs-attention rather than triggering an immediate repeat dial. Unanswered calls may retry within a bounded policy; opted-in WhatsApp fallback is separate work. Answering or ending a call does not itself resolve the follow-up, and acknowledging an update does not complete its associated tasks.

Both VoiceLink and Twilio personal callback paths exist. Configuration defaults and the current deployment workflow select Twilio callbacks, while an older provider-readiness runbook says the owner wanted VoiceLink callbacks and Twilio reserved for WhatsApp. This is a material configuration/documentation conflict to resolve in the final publication.

The latest local VoiceLink diagnostic records a provider `stop` approximately 937 ms after startup despite the backend sending greeting audio. It treats `call_limit: 1` as an unverified possible lead, not an established cause. Friday's readiness response hardcodes `provider_acceptance_verified=False`. The existence of implemented callback and messaging code must not be converted into a claim of current end-to-end live acceptance.

Sources: [personal tools](E:/Projects/Ai_receptionist/backend/app/personal_agent/tools.py), [memory](E:/Projects/Ai_receptionist/backend/app/personal_agent/memory.py), [scheduler](E:/Projects/Ai_receptionist/backend/app/personal_agent/worker.py), [readiness](E:/Projects/Ai_receptionist/backend/app/personal_agent/routes.py), [latest VoiceLink diagnostic](E:/Projects/Ai_receptionist/personal-agent/docs/VOICELINK_FINAL_DIAGNOSTIC_2026-09-30.md).

## 8. Observability, deployment and operational limits

There are three distinct evidence surfaces: opt-in process-local presentation traces; persistent SQL call/event/usage history; and optional OpenTelemetry export. Rehearsal is authored synthetic data. LIVE presentation uses emitted backend events and reconnectable SSE, without hidden model reasoning or synthetic fallback.

The presentation store is bounded to 20 calls, 600 events per call and roughly one hour. It requires the voice path and observer to share a process; the documented demo topology therefore uses one worker/replica. PostgreSQL operation persistence does not make live WebSocket connections, presentation traces or LangGraph checkpoints automatically portable across processes.

Persistent capture has a bounded asynchronous queue and records incomplete collection where evidence is lost. Caller identity, optional transcript content and safe event metadata have separate handling. Transcript retention is configurable and access is audited. No audio recording is implemented. Provider-reported usage is stored as units/tokens/duration; monetary cost is not computed, even though a frontend tab is labelled “Usage & cost”.

The root Dockerfile starts `app.main:app` on port 8002 by default. GitHub Actions runs lint/types/tests/build, pushes a digest-addressed Docker Hub image, deploys to Azure Container Apps, keeps a warm replica and probes readiness. Vercel serves the frontend SPA. Alternative voice-only and Sarvam entry points exist, but the main app does not mount Sarvam routes. Those alternative apps also do not use the main lifespan that starts maintenance, capture and the personal worker.

Liveness establishes process health. Readiness currently executes `select 1` against the database; it does not verify all migrations, model access, carrier marks, callback bindings, or WhatsApp delivery. The current auto-deploy workflow also explicitly enables personal scheduling/outbound flags, so a deployment can change callback behaviour beyond replacing an image.

Clinic notification delivery uses leased outbox jobs and checks messaging consent. It provides durable retryable intent; it does not promise exactly-once external delivery when a send succeeds but the local acknowledgement/commit is lost.

Sources: [presentation store](E:/Projects/Ai_receptionist/backend/app/voice/presentation.py), [capture](E:/Projects/Ai_receptionist/backend/app/observability/capture.py), [telemetry](E:/Projects/Ai_receptionist/backend/app/observability/telemetry.py), [maintenance](E:/Projects/Ai_receptionist/backend/app/services/maintenance.py), [outbox](E:/Projects/Ai_receptionist/backend/app/services/outbox.py), [root Dockerfile](E:/Projects/Ai_receptionist/Dockerfile), [deployment workflow](E:/Projects/Ai_receptionist/.github/workflows/ai-receptionist-backend-AutoDeployTrigger-d2b084f2-4c49-4354-be5c-ae075cc99ad2.yml).

## 9. How this becomes the reusable enterprise guide

The central pattern is a voice interface over controlled business operations: authenticate the channel, establish trusted identity, discover grounded options, prepare a precise proposal, obtain operation-bound consent, execute through the enterprise transaction boundary, and report a committed result. Friday extends that pattern with durable pending work and external delivery state.

For an existing enterprise platform, the guide should explain replacing the clinic-specific executor queries with the platform's supported APIs/services while retaining its authorization and transaction rules. The repository currently implements its own clinic business system using direct SQL; it is not already a packaged connector to arbitrary enterprise software. The reusable pattern is the architecture and contracts.

The final guide should distinguish implemented code, local test evidence, historical operational evidence, live deployment verification, and proposed extensions. It should avoid presenting simulated payments, disabled Chained mutations, bounded memory, optional tracing or configuration presence as stronger capabilities than they are.

The planned page structure is in [DOCUMENT_BLUEPRINT.md](E:/Projects/Ai_receptionist/docs/DOCUMENT_BLUEPRINT.md). Detailed implemented observability coverage is recorded in [OBSERVABILITY_COVERAGE_2026-10-05.md](E:/Projects/Ai_receptionist/docs/OBSERVABILITY_COVERAGE_2026-10-05.md). The supplied table schema enables the database overview; claims about live function/policy/index deployment must remain qualified unless further evidence is provided.
