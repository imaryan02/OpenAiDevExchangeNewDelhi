# Personal AI / Friday V1 implementation plan

Created: 27 September 2026.
Status: local data/API foundation and initial dashboard implemented; owner supplied
nine-table grant/RLS evidence and zero unexpected foreign-key targets. Natural
Prompt/tools/memory runtime and VoiceLink inbound/outbound routing implemented locally;
provider acceptance and full database/runtime acceptance remain pending.
Priority: reliable end-to-end behavior, followed by clean separation, then extras.

## Current review — 27 September 2026

Reviewed against the actual personal backend/frontend files and owner-supplied
database verification. A completed code item is not a claim of deployed acceptance.

| Phase | Current status | Remaining acceptance |
| --- | --- | --- |
| 0: Analysis | Repository analysis and requirements recorded | Callback provider/caller ID and owner setup |
| 1: Providers | Twilio Sandbox joined and one free-form message reached `read`; VoiceLink outbound documentation recorded | Real callback audio and Friday-to-WhatsApp delivery |
| 2: Foundation | Separate tables and owner APIs implemented; grant/RLS/FK checkpoint passed | Live owner isolation, transactions, restart persistence and tool idempotency |
| 3: Tools/memory | Personal prompt, tool executor, exact-session memory capture and bounded context assembly implemented | Transport wiring, live transactions and varied conversation acceptance |
| 4: Voice routing | Registered-caller dispatch and isolated Friday gateway implemented | Owner setup, deployment and real call acceptance |
| 5: Scheduler | Worker claims/recovery and lifespan wiring implemented; execution gated | Live restart/concurrency/race acceptance |
| 6: Callbacks | VoiceLink lead adapter, signed stream/status correlation and retry policy coded; execution gated | Azure token configuration and live call acceptance |
| 7: WhatsApp | Explicit sending, signed delivery callbacks and opted-in missed-call fallback coded; gated | Deployed Friday handoff, signed callback and repeat rehearsal window |
| 8: Dashboard | Separate local dashboard, polling, countdowns and rehearsal controls implemented | Deployed workflows, linked provider evidence and full visual/accessibility review |
| 9: Acceptance | Foundation build/checks and receptionist regressions passed | Real end-to-end acceptance, deployment and rehearsal |

### Next work in order

1. Configure the existing Auth user as the owner and verify the foundation against
   the applied database; register the owner's phone through the personal profile.
2. Verify the implemented prompt/tools/memory and same-number registered-caller
   routing through deployed natural conversations. Check active-call mode stability
   and receptionist fallback with the designated phone.
3. Finalize the outbound callback transport and visible number; record real audio
   and WhatsApp recipient eligibility before enabling outbound execution.
4. Connect the durable worker and chosen callback transport, then retry and
   WhatsApp handoff/fallback. Verify actual provider behavior before enabling it.
5. Deploy and rehearse varied natural conversations and failure paths.

Owner UUID has now been supplied and configured locally, and the personal profile
was saved/verified in the database. The owner requires callbacks from the existing
VoiceLink number. Twilio is for WhatsApp only. VoiceLink outbound documentation
and credentials are needed before completing the callback transport.

## 1. What we are building

A separate Personal AI module in the existing repository and deployments. Friday
understands natural requests, operates a small task system, remembers recent
interactions and pending events, schedules callbacks and continues updates through
WhatsApp. The existing AI Receptionist remains the default inbound experience.

The primary demonstration is a real conversation using real tools and persisted
state. It is not a scripted sequence. Phrases such as "anything for me?", "yes,
tell me", "I'm in a meeting", "WhatsApp me" and "call me in sixty seconds" must
be interpreted using the current conversation and pending-event context.

An answered or ended call is not proof of event completion. Likewise, delivering
a task summary does not complete the underlying tasks.

## 2. Confirmed requirements

- Keep the existing inbound phone number.
- Toggle new inbound calls between receptionist and Personal AI.
- Route only the registered demo caller to Personal AI when enabled; other callers
  remain on the receptionist flow.
- Resolve and persist agent mode once at authenticated call start.
- Use separate personal prompt, tools, conversations and database records.
- Support task listing, creation, editing, completion and deletion.
- Support persistent reminders, natural rescheduling and cancellation.
- Maintain recent interaction memory and unresolved event context across calls.
- Initiate contextual callbacks through a backend scheduler.
- Track individual call attempts and the event they are trying to resolve.
- Keep unanswered and unresolved interactions pending.
- Support a bounded retry after five minutes and WhatsApp fallback.
- Send WhatsApp updates when explicitly requested during a conversation.
- Show tasks, timers, follow-up state, call/message attempts and recent activity.
- Provide personal-demo-only seeding and reset.
- Reuse existing Twilio configuration where suitable.

## 3. Repository analysis and reuse decisions

| Existing component | Observed behavior | Planned use |
| --- | --- | --- |
| `backend/app/api/routes/voice.py` | Authenticates carrier streams; selects receptionist engine | Small dispatch hook after valid call-start metadata |
| `voice/voicelink_realtime_gateway.py` | Clinic prompt, tools, greeting and appointment runtime are embedded | Preserve receptionist behavior; avoid making its booking state serve Friday |
| `integrations/openai_realtime.py` | Receives instructions and tool schemas; no appointment logic | Reuse protocol client for Friday |
| `integrations/openai_audio.py`, `voice/codec.py` | Speech adapters and audio conversion | Reuse where formats and interfaces match |
| `voice/security.py` | Twilio signatures and signed stream binding | Reuse signature validation; separate personal callback binding |
| `backend/scripts/start_test_voice_call.py` | Demonstrates Twilio outbound call creation | Reference for a proper personal callback adapter, not a scheduler |
| `integrations/twilio.py` | WhatsApp send returns provider message ID and acceptance status | Reuse sender with personal message tracking and delivery callbacks |
| `services/outbox.py` | Appointment-specific recipient lookup and job delivery | Reuse durable leasing ideas, not appointment jobs/tables |
| `services/maintenance.py` | Runs a maintenance cycle every 60 seconds | Keep personal reminder worker separate with shorter polling |
| `db/session.py`, `security/auth.py` | Async SQL sessions and Supabase principal resolution | Reuse database and authentication infrastructure |
| `frontend/src/lib/supabaseAuth.ts` | Login, refresh and authenticated requests | Reuse for the separate demo entry |
| `frontend/src/lib/workspaceNavigation.ts` | Clinic query-param navigation | Keep clinic routing; separate pathname entry for the demo |
| `frontend/vercel.json` | SPA rewrite already supports deep links | `/demo/personal-agent` can use the same frontend deployment |
| `voice/presentation.py` | Process-local, clinic-specific conference events | Do not use as durable personal memory or event truth |

Local configuration inspection confirmed nonempty Twilio account credentials,
WhatsApp sender, Twilio phone number, public voice URLs, VoiceLink settings and
OpenAI key. No credential values were displayed. Presence does not establish
account permissions, sender approval, delivery or live callback compatibility.

No VoiceLink outbound adapter was found. Existing VoiceLink gateways expect the
called number to match the inbound DID, so outbound metadata needs explicit
handling. The existing Twilio media gateway is another receptionist path; it
cannot be assumed to provide Friday's Realtime callback behavior unchanged.

## 4. Decisions to resolve before dependent implementation

| Decision | Proposed default / required evidence |
| --- | --- |
| Outbound provider | VoiceLink, per owner decision; confirm outbound access on the existing DID |
| Callback caller ID | Must be the existing VoiceLink number; verify it is eligible for outbound caller ID |
| Demo profile | One owner linked to existing Supabase login and a registered E.164 phone; no arbitrary destinations from model arguments |
| Language | Adapt to English/Hindi/Hinglish if chosen; final preference remains open |
| Personal voice engine | Realtime first; receptionist engine configuration stays independent |
| Timer origin | Start at committed user request; defer dialing while a call with the owner is active |
| Retry/fallback | First attempt, one retry after five minutes, then WhatsApp if the update remains unresolved and fallback is enabled |
| WhatsApp eligibility | Verify existing sender vs sandbox, recipient enrollment, messaging window or approved template |
| Recent memory | Proposed seven-day window with bounded retrieval; retention remains a configurable demo setting |
| Event expiry | Keep unresolved work until resolved/cancelled or explicit expiry; do not silently drop it with recent memory |
| Due tasks | Define today in the profile timezone; propose today's and overdue pending tasks plus undated pending tasks, shown as separate groups |
| Acknowledgment | Interpret in context; clarify ambiguity instead of completing an event on the word "okay" |

Provider requests, outbound calls/messages, remote migrations and deployments
are operational steps to arrange during implementation; planning does not claim
they were performed. Do not print or copy secret values into module documents.

Twilio free-form WhatsApp messaging depends on a customer service window opened
by an inbound WhatsApp message; outside it an approved template is required.
A telephone call does not open that window. See
[Twilio WhatsApp](https://www.twilio.com/docs/whatsapp/api) and
[sandbox setup](https://www.twilio.com/docs/whatsapp/sandbox).

## 5. Isolation and proposed folder layout

```text
personal-agent/
  README.md
  docs/
    IMPLEMENTATION_PLAN.md
    PROVIDER_READINESS.md            # Phase 1 evidence
    REHEARSAL_RUNBOOK.md             # Final rehearsal/setup/reset
  scripts/
    seed_demo.py                     # Later, personal-only utility

backend/app/personal_agent/
  __init__.py
  config.py                         # Personal settings and feature gate
  schemas.py                        # API/tool contracts
  domain.py                         # Event/attempt states and transitions
  repository.py                     # Owner-scoped persistence and claims
  routes.py                         # /v1/personal-agent APIs
  service.py                        # Tasks and follow-up operations
  memory.py                         # Recent context assembly and expiry
  prompt.txt
  tools.py                          # Personal tool allowlist/executor
  routing.py                        # Mode resolution and call dispatch
  voice/
    session.py                      # Personal session and conversation state
    realtime_gateway.py             # Personal speech/tool orchestration
    voicelink.py                     # Provider transport as required
    twilio.py                       # Provider transport if Twilio selected
  worker.py                         # Due events, retries and recovery
  callbacks.py                      # Callback attempts and provider adapter
  messaging.py                      # WhatsApp continuation/delivery state

frontend/src/personal-agent/
  PersonalAgentDemo.tsx
  api.ts
  types.ts
  styles.css
  components/                       # Tasks, follow-ups, activity, readiness

backend/tests/personal_agent/
frontend/tests/personal-agent.test.mjs
supabase/migrations/<unique-version>_personal_agent_foundation.sql
supabase/verification/<matching-version>_personal_agent_checks.sql
```

File names may be adjusted as interfaces become concrete. Do not create empty
runtime scaffolding before its implementation phase. SQL stays in existing
migration directories with a personal prefix and unique versions; this avoids a
second migration discovery mechanism. Do not rename historical migrations.

Expected shared integration files:

- `backend/app/api/router.py`: mount personal routes.
- `backend/app/api/routes/voice.py`: route eligible authenticated starts.
- `backend/app/main.py`: start/stop personal worker behind a feature flag.
- `backend/app/core/config.py` and `backend/.env.example`: minimal additive wiring
  if required; personal settings otherwise live in the module.
- `frontend/src/main.tsx`: select separate demo entry before clinic initialization.
- Existing VoiceLink gateway entry signatures: only if necessary to hand off an
  already-read start message without dropping pre-start events.
- `.github/workflows/ci.yml`: ensure meaningful personal checks are included.

No planned edits to receptionist prompts, clinic tool definitions, appointment
SQL, clinic notification queries or patient records. Transport extraction is only
justified when it is small, necessary and covered by regression checks.

## 6. Data and memory contract

All personal rows are owner-scoped. The backend uses the authenticated principal
for dashboard requests and the registered profile/callback binding for voice.
Clinic membership alone must not expose another person's tasks or memory.

| Entity | Main fields / purpose |
| --- | --- |
| Profile | Owner ID, registered phone, timezone, language, enabled status, fallback preference |
| Mode configuration | Inbound number, selected mode, eligible profile, revision, updated by/at |
| Task | Owner, title, optional description/due time, pending/completed, completion time, version, deleted time |
| Follow-up event | Owner, type, request/context, task IDs and snapshot, next action/time, status, resolution, source call, version |
| Call session | Owner, provider, provider call ID, inbound/outbound, saved agent mode, linked event/attempt, start/end/status |
| Callback attempt | Event, attempt ordinal, lease, provider call ID, ringing/answer/end timestamps, failure and reconciliation state |
| Message attempt | Event, destination reference, content snapshot, provider message ID, delivery state, idempotency key |
| Recent interaction | Owner, session/event links, bounded dialogue or summary, provenance and expiry |
| Agent event | Owner, sequence, event type, concise description, safe metadata, call/event/attempt links, created time |
| Demo generation | Reset version used to invalidate stale queued actions and tool responses |

An event, a call and a message are separate records. Lifecycle status and business
resolution must remain separate. For example, an unanswered call is an attempt
result while its event remains pending.

Memory has three layers:

1. Current call context: this session's turns and active subject.
2. Recent interactions: a bounded set of saved exchanges/summaries with timestamps
   and source references. If text retention is disabled, retain safe structured
   outcomes and avoid claiming verbatim recall.
3. Unresolved events: durable facts needed to continue pending work, retained
   independently of recent conversation expiry.

Context assembly retrieves open events, relevant tasks and limited recent history.
It prioritizes an explicitly linked callback event over unrelated older work.
No vector database, embedding pipeline or growing preference model is needed.
Summaries are derived context, never authoritative proof that an action completed.

## 7. Natural intent and follow-up behavior

Friday receives current time/timezone, inbound or callback purpose, available
personal tools, pending-event context and recent interactions. It may phrase
greetings and updates naturally. Fixed wording is not an acceptance requirement.

Tools should cover task operations, pending/recent context lookup, scheduling,
rescheduling, cancellation, explicit event acknowledgment and WhatsApp handoff.
The backend chooses the owner, destination and authorized event scope. The model
does not call an arbitrary number, write arbitrary SQL or decide retry policy.

Behavior requirements:

- "Anything for me?" can surface pending updates and relevant tasks.
- "Yes, tell me" refers to the active offer/topic when available; otherwise clarify.
- "WhatsApp me" refers to the current update, not all private history.
- "Call me in sixty seconds" persists a follow-up for the current subject; ask for
  the subject if none is clear.
- "I'm in a meeting" alone does not invent a callback time or messaging request.
- "Call me later" needs a time clarification unless an agreed time is in context.
- "Got it" can resolve the update when context clearly supports acknowledgment.
- "Mark that task done" changes a task, which is a different action from receipt
  of its reminder; ambiguous task matches need clarification.
- Hangup, silence, generated speech, answer detection and carrier playback marks
  alone do not prove the user acknowledged an update.
- Provider/tool failure must not produce a false success response.

Suggested event states: `pending`, `scheduled`, `in_progress`,
`awaiting_acknowledgment`, `resolved`, `cancelled`, `needs_attention`.
Use `next_action` and `next_action_at` for call/retry/message scheduling instead of
encoding every transport stage as an event status.

Resolution reasons distinguish user acknowledgment, explicit dismissal, requested
channel handoff and policy-completed delivery. WhatsApp delivery can complete a
"send me the update" instruction without claiming the recipient read it. A failed
handoff remains unresolved. Provider "read" receipts, if available, are not task
completion.

Default follow-up policy, pending final agreement:

```text
Request committed -> event scheduled -> callback attempt
  unanswered/busy -> event pending -> one retry after five minutes
    still unanswered -> WhatsApp fallback if enabled and eligible
  answered -> conversation continues
    acknowledge -> resolve update
    WhatsApp request -> message attempt -> resolve handoff on agreed delivery evidence
    later callback -> reschedule same event
    cancel -> cancel event
    disconnect without resolution -> bounded retry/fallback, not endless redialing
```

Timeout/uncertain provider acceptance requires reconciliation before redialing.
Use a total call-attempt budget so unanswered and unresolved answered calls cannot
each start a fresh unlimited retry loop. An inbound call before the scheduled
callback can resolve/reschedule the event; the worker rechecks its version before
dialing. One active call per profile; multiple events remain separate and can be
presented together only with explicit links.

## 8. Phase-by-phase delivery plan

### Phase 0 — Analysis, scope and implementation contract

Deliverables: this plan, repository reuse map, isolation boundaries and open
decision list. Complete before creating runtime code.

- [x] Inspect inbound VoiceLink/Twilio routes and current gateways.
- [x] Inspect prompt/tool registration and conversation state.
- [x] Identify Twilio outbound script and absence of VoiceLink outbound adapter.
- [x] Inspect WhatsApp sender and its acceptance-only result.
- [x] Inspect frontend entry/routing, database sessions and background maintenance.
- [x] Confirm configured integration fields without exposing values.
- [x] Capture natural conversation, recent memory and persistent event requirements.
- [x] Create separate planning folder and progress checklist.
- [ ] Resolve the dependent choices listed in section 4.

Exit: product behavior is agreed and provider verification can be performed with
designated inputs. Planning is not implementation or live acceptance.

### Phase 1 — Provider feasibility and demo readiness

Deliverables: `PROVIDER_READINESS.md`, selected transport contracts and setup steps.

- [x] Obtain VoiceLink outbound API/stream/callback documentation from signed-in portal.
- [x] Read-only Twilio account/number checks: active trial account and owned voice-capable number.
- [x] Choose VoiceLink outbound on the existing DID; live caller ID check remains.
- [ ] Verify outbound answer connects bidirectional audio to our backend.
- [ ] Verify provider call ID mapping, direction, disconnect and unanswered status.
- [ ] Verify Twilio WhatsApp sender mode, recipient eligibility and message window.
- [ ] Verify acceptance and delivery/failure callbacks for WhatsApp.
- [x] Record available evidence and remaining limits without secrets.

Exit: actual callback audio and WhatsApp receipt work using the chosen providers,
or a concrete provider limitation is recorded and the demo requirement adjusted.
Do this before building a dashboard that promises those capabilities.

### Phase 2 — Isolated persistence, profile and API foundation

Deliverables: personal config/domain/schemas/repository/routes, additive migration
and verification, feature flag defaulting off.

- [x] Implement owner profile and registered caller record (voice binding still pending).
- [x] Add separate personal table migration, indexes, RLS and owner-scoped constraints.
- [x] Define event, call, attempt, message and resolution states explicitly.
- [x] Add saved mode configuration with update/activity fields and reset generation.
- [x] Implement personal route authorization and API errors.
- [x] Add optimistic versions and reset-generation foundations to personal APIs.
- [x] Implement persisted tool idempotency and stale-generation rejection in execution.
- [x] Validate migration dependency boundaries and new version in repository.
- [x] Record owner-supplied nine-table grant/RLS/policy and zero unexpected-FK checks.
- [x] Verify API owner guards and owner-scoped SQL with local foundation checks.
- [ ] Verify actual cross-user database isolation and live transaction behavior.

Local foundation now includes profile/mode, task and follow-up operations,
bounded activity/memory reads and guarded seed/reset APIs. Owner supplied all
nine table grant rows: anonymous read and client write are false. All nine tables
have RLS enabled and the owner read policy present; the owner reports zero
unexpected external-FK targets. Live owner isolation and API transactions remain
pending; Phase 2 is not fully accepted. See `SCHEMA_ISOLATION.md` and `SETUP.md`.

Exit: personal state persists across process restart and cannot be read or changed
by an unrelated authenticated owner. Receptionist remains default.

### Phase 3 — Tasks, recent memory and natural tool operations

Deliverables: task/event services, personal tools, prompt and memory assembly.

- [x] Implement task CRUD/completion and today/overdue/undated query in personal APIs.
- [x] Add owner-scoped follow-up and expiry-filtered memory read APIs.
- [x] Save task/context snapshots with follow-up requests.
- [x] Implement final-transcript capture with exact call/source references; transport hookup pending.
- [x] Assemble pending-event and recent-interaction context, prioritizing exact linked events.
- [x] Implement bounded context budgets, configurable memory expiry and owner cleanup function.
- [x] Implement version-checked event acknowledgment, reschedule and cancel APIs.
- [x] Build a personal tool allowlist and server-owned owner/call/generation binding.
- [x] Add natural conversation prompt with clarification and truthful capability rules.
- [ ] Handle ambiguous task matches, subjects, times and acknowledgments.
- [ ] Verify varied utterances choose appropriate actions without fixed dialogue.

Exit: personal operations work independently of telephone transport; tool results
are authoritative, retries are idempotent and unresolved context survives hangup.

### Phase 4 — Same-number mode routing and Personal AI voice

Deliverables: routing hook, personal Realtime session and selected transport adapter.

- [x] Authenticate/validate VoiceLink stream metadata before selecting the personal profile.
- [x] Resolve mode once and save it on the personal call session.
- [x] Route only the registered caller when toggle is enabled.
- [x] Fall back to existing receptionist for mode lookup failure or ineligible caller.
- [x] Supply personal prompt/tools/memory with no clinic context or tool leakage.
- [x] Implement natural inbound greetings, paced audio and interruption handling.
- [ ] Connect contextual outbound openings in the callback adapter.
- [x] Persist session outcome and final transcript items as recent context.
- [ ] Verify toggle changes never replace an active agent.
- [x] Run existing local receptionist startup/Realtime/booking regression checks after integration.
- [ ] Verify deployed receptionist inbound/booking behavior after gateway integration.

Exit: the existing number naturally answers as Friday for eligible calls and as
the receptionist otherwise. Personal runtime failure is surfaced accurately;
do not silently swap personalities during an established call.

### Phase 5 — Durable timers and scheduler

Deliverables: personal worker, transactional due-event claims and recovery rules.

- [x] Save follow-up creation/next-action time in UTC; display profile-local time.
- [x] Implement configurable polling approximately every second.
- [x] Commit claims and submitting state before dispatch; no SQL locks during network work.
- [x] Recheck event revision, reset generation and active-call exclusion.
- [x] Respect reschedule/cancel revisions; mark overdue events for review after configured lateness.
- [x] Recover unsubmitted claims; mark uncertain submissions for reconciliation without redial.
- [x] Wire worker startup/shutdown behind personal/scheduler/outbound flags and adapter presence.
- [ ] Verify restart recovery, competing workers and inbound resolution races.

Exit: due actions are persisted and claimed reliably. Browser countdowns do not
initiate calls. No missed reminder is silently discarded or dialed twice by workers.

### Phase 6 — Contextual callbacks, attempts and retry policy

Deliverables: outbound adapter, authenticated callback webhook/stream binding,
attempt tracking and event continuation.

- [x] Create a durable attempt before provider submission.
- [x] Bind VoiceLink's call ID and signed attempt to the exact event in local code; live check pending.
- [x] Route verified reminder callbacks into Personal AI regardless of inbound toggle in local code.
- [x] Prepare exact saved event context for the callback session.
- [x] Track VoiceLink ringing/answer/end separately from event resolution in local code.
- [x] Keep unanswered and unacknowledged events unresolved in the data model.
- [x] Schedule one five-minute retry from authenticated VoiceLink missed-call status in local code.
- [x] Hold ambiguous provider acceptance for review instead of retrying blindly.
- [ ] Handle user rescheduling/cancellation, concurrent inbound calls and voicemail limits.
- [ ] Verify contextual speech on real callbacks and receptionist regression.

Exit: actual incoming callback reaches the user with correct context; unresolved
events remain actionable and retry behavior is bounded and observable.

### Phase 7 — WhatsApp handoff and fallback

Deliverables: personal message service, delivery webhook and event resolution rules.

- [ ] Generate a bounded summary from the current event/tasks.
- [ ] Use registered destination; record explicit request or enabled fallback policy.
- [ ] Persist message attempt and duplicate-prevention key before sending.
- [ ] Reuse Twilio sender; add template support only if required by selected setup.
- [ ] Verify signed callbacks and correlate by provider message ID.
- [ ] Distinguish queued/accepted/sent/delivered/read/failed where supported.
- [x] Implement the monotonic message-status transition helper.
- [ ] Apply status transitions in authenticated duplicate/out-of-order delivery callbacks.
- [x] Trigger opted-in fallback after retry exhaustion in local code; Sandbox needs an open 24-hour window.
- [ ] Keep failed delivery pending/needs-attention and avoid false spoken success.

Exit: "WhatsApp me" works during an ongoing discussion and automatic fallback
works after unreachable calls. Delivery evidence and human acknowledgment remain
distinct. Reset/retry cannot send stale content unnoticed.

### Phase 8 — Separate dashboard, event history and rehearsal controls

Deliverables: `/demo/personal-agent`, personal API client/components/scoped styles.
An initial functional shell may be added after Phase 3 to inspect early phases.

- [x] Add separate entry using existing auth without clinic dashboard initialization.
- [x] Display saved mode/profile and truthful configuration/implementation readiness.
- [ ] Add measured runtime/provider readiness after transport integration.
- [x] Show/manage tasks and pending events; render available call/message attempt statuses.
- [x] Show recent activity and expiry-filtered stored memory.
- [ ] Add clear event/session/provider links as voice and messaging are connected.
- [x] Poll every two seconds; refresh on focus and skip polling while hidden.
- [x] Compute countdown from server time/trigger time; polling refresh restores saved state.
- [x] Add isolated seed/reset APIs and controls with generation increment and queued-action cancellation.
- [ ] Enforce reset-generation invalidation in workers, calls and tool execution.
- [ ] Cancel queued actions and attempt provider cancellation for ringing calls.
- [ ] Explain completed sends cannot be undone and active calls may remain connected.
- [x] Add scoped professional styling, semantic controls, focus indicators and reduced motion support.
- [ ] Review full populated dashboard, keyboard navigation and responsive states against working APIs.

Exit: the page reflects durable backend truth, refresh restores countdown/state,
and repeated rehearsals cannot affect receptionist data.

### Phase 9 — Acceptance, deployment and presentation preparation

Deliverables: meaningful regression checks, runbook, verified deployed demo.

- [ ] Run appropriate backend/frontend checks for the final changes.
- [ ] Verify real same-number inbound selection and active-call mode stability.
- [ ] Verify both task-initiated and event-initiated natural conversations.
- [ ] Verify 60-second callback and user-requested WhatsApp handoff.
- [ ] Verify unanswered attempt, five-minute retry and WhatsApp fallback.
- [ ] Verify answered-but-unresolved event, acknowledgment and cancellation.
- [ ] Verify restart during countdown, stale lease and duplicate provider callbacks.
- [ ] Verify early inbound call resolves the event without duplicate callback.
- [ ] Verify unauthorized caller/owner and ambiguous intent behavior.
- [ ] Verify reset with scheduled, ringing and messaging work.
- [ ] Recheck receptionist flow after every major shared integration and deployment.
- [ ] Deploy with Personal AI feature off initially; enable only after readiness.
- [ ] Rehearse at the actual presentation environment with designated recipient.
- [ ] Document WhatsApp setup/window, callback number, mute/DND/watch routing and rollback.

Exit: varied conversations and failure paths work with real providers; checklist
records evidence, not only source completion. Disable personal feature/routing as
rollback while retaining personal history for investigation.

## 9. Acceptance matrix

| Scenario | Required outcome |
| --- | --- |
| Registered caller, toggle off | Existing receptionist |
| Registered caller, toggle on | Friday with personal tools/context |
| Other caller, toggle on | Existing receptionist |
| Toggle changes mid-call | Original agent persists |
| Mode lookup fails | Receptionist for new normal inbound calls |
| "Anything for me?" | Relevant pending work/tasks surfaced naturally |
| "Yes, tell me" | Continues known subject; clarifies if no subject |
| Timer request then hangup | Event and countdown persist |
| Restart during timer | Due event recovers; no duplicate dial |
| Callback answered | Correct event context; no automatic resolution on answer |
| Callback unanswered | Same event pending; one five-minute retry |
| Retry also unanswered | Eligible WhatsApp fallback or visible needs-attention |
| "WhatsApp me" | Current update submitted and delivery tracked |
| "Call later" without time | Clarification, no invented schedule |
| "Got it" in clear context | Update resolved; tasks remain unchanged |
| Ambiguous "okay" | No unsupported completion claim |
| User calls before reminder | Pending update can resolve; queued dial suppressed |
| Provider timeout/duplicate webhook | Reconciliation/idempotent transitions |
| Reset demo | Personal state invalidated/reset; clinic data untouched |

## 10. Overall progress checklist

- [x] Product discussion and relevant repository analysis.
- [x] Separate module planning folder.
- [x] Phase plan, proposed file map and acceptance checklist.
- [ ] Finalize provider and behavioral decisions.
- [ ] Phase 1: provider feasibility verified.
- [ ] Phase 2: isolated data/profile/API foundation.
- [ ] Phase 3: tasks, memory and personal tools.
- [ ] Phase 4: same-number routing and natural voice.
- [ ] Phase 5: durable scheduler.
- [ ] Phase 6: callbacks, continuation and retry.
- [ ] Phase 7: WhatsApp handoff/fallback.
- [ ] Phase 8: dashboard, recent activity, seed/reset.
- [ ] Phase 9: real-provider acceptance, deployment and rehearsal.

Update checkboxes when their specific deliverable is complete. Record validation
date, evidence and limitations for provider/database/deployment checks. Do not
mark a whole phase complete because a local build passes.

### Foundation validation — 27 September 2026

- 23 personal backend checks passed: anonymous/wrong-owner denial, feature gate,
  safe readiness, input validation, stale task version and commit failure behavior.
- Backend mypy passed for 80 application files; Ruff passed.
- Frontend production build passed; 28 frontend checks passed including personal
  route isolation, saved-time countdown and unresolved-event filtering.
- Browser entry was rendered at `/demo/personal-agent`; the existing configured
  API deployment has not received these routes, so the UI reports backend setup
  pending. No full dashboard or live personal database workflow is claimed verified.
- Receptionist voice regression checks and personal foundation checks passed:
  72 checks covering startup, VoiceLink realtime, atomic booking, booking controller
  and personal owner/API behavior.
- Read-only Twilio account/number lookups passed. Account is trial, number is
  voice capable and differs from the existing VoiceLink number. Callback audio
  and WhatsApp delivery remain unverified; see `PROVIDER_READINESS.md`.
- Personal voice activation and automatic reminder execution remain explicitly
  unavailable. No external calls/messages or agent-run remote DB mutations occurred.

### Prompt/tools/memory implementation — 27 September 2026

- Added `prompt.txt`, `tools.py`, `memory.py` and `service.py` within the personal module.
- Ten allowlisted tools cover tasks, bounded context, reminders and acknowledgment.
  WhatsApp is not exposed until delivery integration exists.
- Results are persisted per call/request with an input hash. Profile/call locking
  and transaction boundaries serialize duplicates and reject reset generations.
  Commit completes before a tool result is returned by the runtime.
- Memory retains final transcript items only, with duplicate suppression and
  configurable expiry. Context includes up to 20 tasks, 10 unresolved updates,
  12 exchanges and the exact linked event, within a 16,000-character budget.
- Registered phone saved in local backend config as requested; dashboard uses
  this setup default. The owner profile still requires authenticated registration.
- Python static typing and frontend type checking passed for this slice.
  Natural intent behavior and real SQL transaction execution remain unverified.

### Inbound voice implementation — 27 September 2026

- Added personal `routing.py` and `voice/voicelink.py`. Authenticated VoiceLink
  entry reads and validates start once, then selects the saved registered-caller
  mode. Other callers and lookup failures retain the existing receptionist.
- Realtime receptionist accepts an already-read start message. Its prompt,
  tools and booking logic are unchanged.
- Friday has a separate Realtime session, audio queue, carrier clear/marks,
  tools, transcript capture, heartbeat and termination record. Normal hangups
  do not resolve events. Stale calls are expired before a new personal call.
- Mode API supports Personal AI when voice configuration and registered profile
  match. Local owner/feature enabling and deployment were not performed.
- Receptionist startup/Realtime/booking and personal foundation checks passed
  (72 checks). Live Friday audio, natural intent and active-call toggle behavior
  still require the owner UUID, deployed routes and real registered-number calls.
- Automatic callbacks and WhatsApp execution remain unavailable.

### Live foundation setup — 27 September 2026

- Enabled the local personal foundation/rehearsal controls with the supplied
  Auth UUID and registered phone. Outbound and WhatsApp execution remain disabled.
- Added a repeatable owner setup script. It only writes personal profile/activity
  data, preserves existing profile preferences and selects Receptionist mode.
- Saved the profile and independently read it after commit: owner/phone matched,
  timezone Asia/Kolkata and WhatsApp fallback off.
- Existing owner login restored in the local browser. Authenticated readiness
  and snapshot returned HTTP 200, and the dashboard displayed the saved phone,
  Receptionist mode and activity. No tasks or reminders were seeded.
- Local backend runs with lifespan off to prevent shared maintenance jobs during
  UI review. Production deployment, cross-user RLS behavior and live phone calls
  remain unverified. See `SETUP.md` for preview commands.

### Durable worker implementation — 27 September 2026

- Added `worker.py`: owner/profile lock, due-event claim, lease token, queued
  attempt and submitting recheck are committed before the injected adapter runs.
- Active calls and outstanding callback attempts prevent overlapping submissions.
  Version/generation/lease checks suppress cancelled, rescheduled and reset work.
- Expired queued claims can recover safely. Submitted/uncertain work requires
  reconciliation; late reminders and exhausted attempt budgets become visible
  needs-attention events. No uncertain network result automatically redials.
- Main lifespan can start/cancel the worker with an injected provider adapter.
  No VoiceLink outbound adapter is connected. Local scheduler/outbound flags
  remain disabled, so no reminders dial.
- Local Friday API URL now persists independently of the receptionist API URL.
- Static typing passed. Live lease/restart/concurrency and provider behavior are
  still pending; no scheduler/database mutations were executed for this slice.

### Callback provider decision — 27 September 2026

- Owner confirmed callbacks must use VoiceLink and the existing number; Twilio
  will be used only for WhatsApp.
- Twilio voice adapter work was removed. VoiceLink outbound API, credentials,
  stream metadata and signed event/status format are not present in this repo.
- The provider-independent worker remains gated. No actual outbound call has
  been placed or claimed as working.

### WhatsApp handoff implementation — 27 September 2026

- Added an owner-bound voice tool for explicit “WhatsApp me” requests. It builds
  a bounded update from the current linked event and today's tasks, stores a
  message/deduplication record before network submission, and sends only to the
  registered number through the existing Twilio client.
- Added a signed Twilio status endpoint that advances submitted, sent, delivered,
  read and failure evidence without marking provider acceptance as delivery.
- Local WhatsApp execution remains disabled. Sender eligibility, sandbox/session
  window or template requirements, real receipt and fallback after missed calls
  are not verified or complete.

## 11. V1 exclusions

Long-term learning, vector/graph memory, calendar/email, family/world models,
IoT, multi-agent coordination, preference learning, memory consolidation,
unbounded outreach and arbitrary autonomous actions remain outside scope.
Persistent recent context and bounded user-authorized follow-up policies are
included. Recording and a second Personal AI voice engine are optional future
work, not prerequisites for the agreed V1.
