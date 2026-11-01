# Observability implementation plan

Prepared: 27 September 2026.

Discovery: [OBSERVABILITY_DISCOVERY_2026-09-27.md](OBSERVABILITY_DISCOVERY_2026-09-27.md).

Status: The owner has applied and verified the Phase 1–2 and Phase 4 migrations in Supabase. The backend is deployed and the owner confirmed an inbound call works after removing the duplicate container and restoring its 28 environment variables onto the remaining backend. Local backend checks pass against the lockfile: 269 tests passed, 15 skipped, Ruff passed, and mypy passed for 73 source files. Initial Phase 3 tracing and Phase 4 usage capture are implemented; external trace export remains disabled. Frontend deployment and durable call/timeline/usage inspection still need explicit runtime verification. The implementation notes below describe the original implementation checkpoint; this status and checklist reflect subsequent verification.

## Intended result

Clinic staff can find a call, open its timeline, inspect permitted conversation and operation evidence, and understand failures and delays. Authorized operators can monitor reliability and usage without receiving unrestricted patient content. Both Chained and Realtime produce the same basic call-history contract while retaining engine-specific detail.

The earliest useful release is **Phases 1–2**: persistent call summaries, safe timelines and a clinic dashboard. **Phases 1–3** establish the operational MVP with timing and tool/operation tracing. Later phases add usage/cost, optional content, quality/alerts and platform administration.

Do not enable provider recording, send notifications, change booking consent, replace the voice engines or introduce a second conversational model as part of this project. Capture-disabled and unavailable fields remain visible as such. Existing demonstration/rehearsal data stays clearly distinct from production history.

## Phase overview

| Phase | Deliverable | Depends on | Release checkpoint |
| --- | --- | --- | --- |
| 1 | Durable call lifecycle and safe event APIs | Existing auth/database | Both engines can be inspected after a restart |
| 2 | Clinic Call History dashboard | 1 | Browse recent calls and open a real call timeline |
| 3 | End-to-end timing, OpenTelemetry traces and operation links | 1–2 | Identify a slow/failed turn and its actual business outcome |
| 4 | Usage ledger and cost estimates | 3 | Explain cost provenance and missing usage |
| 5A | Optional permissioned transcript review | 1–3 and capture policy | Review conversation text with audited access |
| 5B | Optional recording and playback review | 5A access foundation plus recording consent/storage policy | Inspect authorized audio without putting it in telemetry |
| 6 | Quality review, operational dashboards and alerts | 3–4; content access as applicable | Turn incidents into actionable monitoring and evaluations |
| 7 | Multiple replicas, platform roles and production hardening | 1–6 | Validate shared visibility, isolation and collection overhead |

Phase 6 metadata-only monitoring does not depend on recording. Phases 5A/5B are optional capabilities, not prerequisites for the operational MVP.

## Phase 1 — Durable foundation

### Work

- Define typed, versioned call/event schemas and safe error categories.
- Create `observability_calls` and selected safe timeline storage, separate from `voice_call_sessions` consent runtime.
- Link call, carrier call/stream, connection attempt, runtime session, response, proposal and operation identifiers explicitly.
- Instrument both gateways and the VoiceLink route for authenticated start, actual engine/fallback, greeting, ending and failures.
- Keep pre-auth/unassigned attempts separate from tenant call records; never trust supplied caller metadata for authorization.
- Create an idempotent event sink with bounded asynchronous collection, retry/drop reporting and a reconciliation policy for interrupted capture.
- Normalize provider callbacks, persist safe allowed fields and deduplicate supported identifiers. Confirm actual callback schema/capabilities before claiming carrier coverage.
- Add tenant-scoped summary/detail/event endpoints with stable cursor pagination.
- Add RLS, tenant-qualified relationships and backend membership/permission checks. Verify effective SQL role behavior before production exposure.
- Preserve contact linkage only when supported; do not equate a phone number with one patient or permanent identity.
- Keep transcript and recording capture off. Do not store provider payloads, raw tool inputs or arbitrary exception text.
- Create an additive migration, safe recovery notes and read-only verification queries. Do not replay historical migrations or create an invented migration ledger.

### Principal files

New backend `observability/` contracts/service/repository and `api/routes/observability.py`; registration in `api/router.py`; targeted hooks in both voice gateways and `api/routes/voice.py`; new additive Supabase migration and verification SQL. Small lifecycle changes in `main.py`/maintenance only if needed for collector shutdown and reconciliation.

### Acceptance

- Both engines create correctly scoped durable calls without changing spoken interaction or booking behavior.
- Early disconnect, rejected start and database/collector failure have explicit safe evidence or visible capture gaps.
- Duplicate callbacks/stream events do not duplicate calls or regress terminal status.
- A crash/restart is not displayed as a normal successful completion.
- Rejected or expired tenant access cannot enumerate another clinic's calls/events.
- A collector outage cannot block the media receiver or consent transaction; no claim of lossless capture from an in-memory queue.

## Phase 2 — Clinic dashboard

### Work

- Add **Call History** navigation to the existing React clinic workspace.
- Build a list with clinic-local start time, masked caller/contact reference, actual engine, duration, lifecycle, operation outcome, evidence availability and View action.
- Add date, status, engine and safe-error filters; contact/authorized phone lookup; cursor pagination.
- Build a call detail overview and safe event timeline with engine segments, errors, interruptions and evidence completeness.
- Introduce loading, empty, permission-denied, capture-disabled, expired and incomplete states.
- Use shared authenticatedFetch and centralized domain types.
- Keep **Inside the call** conference view intact. Reuse presentational pieces only where their event assumptions fit the durable contract.
- Start with bounded polling or read APIs backed by shared storage. Add resumable live transport only when necessary; never depend on a process-local call directory.

### Principal files

New `frontend/src/components/CallHistoryPage.tsx`, call detail components, `frontend/src/observability/` types/client/state and scoped styles; narrow navigation changes in `App.tsx`.

### Acceptance

- Authorized clinic users can find/open persisted calls after a server restart.
- Filter changes, authentication refresh and pagination behave consistently.
- No fabricated names/language/accuracy/cost values; absent evidence displays Unavailable/Unknown.
- Multiple operations in one call are represented independently of call closure.
- Synthetic rehearsal records never appear as actual production calls.

## Phase 3 — Performance and action tracing

### Work

- Add OpenTelemetry libraries, contextual instrumentation and configurable export. Use one backend first; Azure Monitor is the current hosting-aligned candidate, not an assumed configured service.
- Instrument model/provider requests, tools, queries and job operations; connect them to call/turn IDs.
- Add voice-specific spans/events instead of relying on HTTP auto-instrumentation for WebSockets.
- Record Chained endpointing/queue/STT/agent/tool/TTS-first-audio and Realtime application wait/tool/generation/playback-buffer timings.
- Distinguish filler from substantive response and audio sent from acknowledged playback.
- Trace cancellation, stale output, clear requests, late marks and playback timeout/estimated-duration fallback.
- Link existing Realtime operation records and consent/readback evidence through authorized read models.
- Add reliable append-only operation transition evidence where needed. Operational telemetry must never become the mutation authorizer.
- Show Chained mutation rejection as intentional policy denial, not infrastructure failure.
- Build per-turn waterfall and operation/consent tabs. Add safe diagnostic detail gates.
- Snapshot model/voice, release SHA and instruction/configuration fingerprints without storing secrets.

### Acceptance

- A delayed turn identifies the measured bottleneck; overlapping span durations are not incorrectly summed.
- Correction/interruption traces link to the right response and proposal.
- COMMITTED, FAILED and unresolved outcomes agree with durable backend evidence.
- Completed text/audio generation is not interpreted as caller approval or completed playback.
- Context survives asynchronous task boundaries and instrumentation creates no duplicate model/provider requests.

## Phase 4 — Usage and cost

### Work

- Capture provider-supported usage from text-model metadata and Realtime completion events, plus classifier and separate audio calls.
- Store usage provenance, request/response identity, model and pricing version; deduplicate completion/retry events.
- Track audio duration estimates only where token billing is unavailable, and label those estimates.
- Calculate AI cost separately from telephony, infrastructure and observability allocation.
- Include cached-token pricing and unsuccessful/discarded work when reported.
- Add call usage detail and aggregate cost per call/completed task with explicit denominators.
- Add reconciliation/import boundary for provider billing; avoid assuming credentials grant billing API access.

### Acceptance

- Missing usage is Unknown, never zero. Estimates are not displayed as an invoice.
- One provider response contributes once; retries contribute their actual usage.
- Rate/model changes do not silently rewrite historical estimates.
- Simulated payments are not confused with AI operating cost or real settlement.

## Phase 5A — Optional transcript review

### Work

- Define separate transcript capture/read/export permissions and an organization capture policy.
- Persist permitted caller/assistant segments with source, turn/response links and generated/sent/interrupted status.
- Audit content access and exports; improve allowlisting/redaction beyond presentation regexes.
- Build conversation view and human correction capability with original/proposed text kept distinct.
- Implement configurable retention and purge behavior before enabling capture in production.

### Dependency decisions

Capture disclosure/consent requirements, retention periods, authorized clinic roles and encrypted storage approach. Messaging consent is not reused for transcript/recording consent. Policy must be resolved before enabling dependent collection; metadata development can continue.

### Acceptance

- Disabled policy captures no conversation text; view permissions are backend enforced.
- No raw transcript in general metrics/logs/exports.
- Content disabled, expired and redacted states are understandable.
- Review corrections do not overwrite historical operation/approval evidence.

## Phase 5B — Optional audio recording

### Work

- Implement an explicit per-call recording policy and consent reference.
- Capture separate caller/assistant tracks or timestamped segments with buffer limits and gap reporting.
- Store audio in protected object storage, not SQL event JSON or OTel spans.
- Persist manifests with format, offsets, object key/checksum, capture scope and retention state.
- Issue short-lived playback access only after authorization and access audit.
- Build synchronized audio/transcript review with interruption and missing-segment labels.
- Add cleanup, storage failure and upload retry handling without delaying the live call.

### Dependency decisions

Storage account/container, region, credentials/managed identity, recording disclosure/consent, retention and export roles. Historical audio cannot be reconstructed where it was not captured.

### Acceptance

- Nonconsenting/disabled calls are not recorded.
- Audio access remains tenant scoped; object paths and logs contain no raw phone/patient names.
- Upload failure does not disrupt speech and never falsely indicates a complete recording.
- Generated assistant audio is not presented as proof it was all heard.

## Phase 6 — Quality, monitoring and alerts

### Work

- Add reviewed labels for transcription, wrong entity/date, missed negation, response grounding, tool choice, consent, pronunciation and task completion.
- Require label provenance, reviewer/version and sample size; link language cohorts only to supported evidence.
- Build operational dashboards for first greeting, response delay, call failures, dependency throttling, denied operations, unknown commits and collection gaps.
- Add maintenance/outbox/frontend/auth/platform instrumentation and job heartbeats.
- Separate notification acceptance from delivery; WhatsApp remains deferred unless scope is resumed.
- Define configurable alert windows/thresholds and incident evidence links. Expected conflict/permission denial is not automatically an outage.
- Turn approved failure examples into de-identified evaluation cases; do not upload patient content to external evaluation tools by default.

### Acceptance

- Alerts identify actionable failures without reporting every policy denial as a production incident.
- Quality reports cannot claim an overall accuracy percentage from unreviewed traces.
- Provider, model and collector failures remain distinguishable.
- No alert message includes patient conversation or credentials.

## Phase 7 — Scale, platform administration and release hardening

### Work

- Verify shared live discovery and history across replicas, collectors and reconnects.
- Measure ingestion overhead, database pool usage, telemetry volume and storage cost with synthetic calls/events.
- Tune batching, diagnostic sampling, retention and partitioning according to evidence.
- Add platform operational roles separately from ORG_ADMIN, plus time-limited scoped support access.
- Build aggregate platform views with patient content hidden by default and sensitive reads audited.
- Validate provider callback subscription and carrier-to-greeting on a designated call; do not infer carrier health from /health/ready.
- Review startup/shutdown/drain behavior, interrupted collection and rollback/recovery procedures.
- Resolve SQL migration ledger/grants, deployment export configuration and telemetry destination permissions before production rollout.

### Acceptance

- Multiple replicas do not fragment the dashboard or lose tenant boundaries.
- Telemetry failures/backpressure do not materially delay speech; overhead and capacity are measured, not promised.
- Platform role does not grant blanket access to recordings/transcripts.
- Rollout failure is recoverable without changing appointments or consent evidence.

## Cross-phase implementation rules

- Additive changes; preserve existing consent/booking invariants and reusable provider adapters.
- Small reviewable phase changes, each with migration/API/UI notes and actual verification results.
- Backend checks for schema/event contracts, idempotency, permissions, failure recovery and engine wiring; database integration where relevant.
- Frontend typecheck/build plus meaningful list/detail/auth/pagination checks. Avoid tests that only repeat implementation strings.
- Provider/call acceptance only with designated authorized test input; no unsolicited outbound calls or WhatsApp messages.
- Remote migration/deployment is a separate explicit operational checkpoint, not implied by a local build passing.
- No claims of recordings, accuracy, live payments, RAG, human transfer or capacity before those capabilities exist and are validated.

## Progress checklist

- [x] Inventory current evidence and implementation gaps.
- [x] Prepare phased implementation plan.
- [x] Phase 1 initial implementation: durable call lifecycle and safe APIs (Supabase schema verified; backend deployed; persisted call/timeline runtime acceptance still pending).
- [x] Phase 2 initial implementation: clinic dashboard (code built; frontend deployment and real call-history inspection still pending verification).
- [ ] Phase 3: performance/tool/operation tracing (manual OpenTelemetry spans and OTLP exporter implemented; locked dependencies install and backend checks pass; export disabled; collector integration, sampling, complete engine timings, and acceptance remain open).
- [ ] Phase 4: usage and cost (provider usage capture and call detail display implemented for supported Chained/Realtime signals; usage schema verified; backend deployed and an inbound call works; persisted usage inspection and separate acceptance calls for both engines remain; prices remain uncalculated).
- [ ] Phase 5A: optional transcript review (code implemented: separate opt-in text storage, chat UI, expiry and audited reads; new migration, deployment and live acceptance pending).
- [ ] Phase 5B: optional recording review.
- [ ] Phase 6: quality/monitoring/alerts.
- [ ] Phase 7: scale/platform/release hardening.

## Implemented in this workspace

Phases 1–2 currently provide a content-free VoiceLink call record for the Chained or Realtime engine selected for an authenticated stream, a bounded asynchronous database writer with brief retry and overflow/incomplete indicators, staff-authorized tenant-scoped list/detail APIs, and a clinic call-history view with engine filtering and pagination. Event metadata uses an allowlist. The dashboard does not show the carrier call identifier, raw phone number, transcript, or audio. The owner-provided Supabase verification result confirmed both tables, indexes, RLS and staff policies.

The initial Phase 3 slice adds Chained STT, agent, first-audio and playback durations; safe turn/generation/playback identifiers and tool/database timings; and a Realtime operation read model that exposes operation type/status/timestamps without returning saved results. The call detail page labels calls without linked durable operations. OpenTelemetry SDK/API and an OTLP/HTTP trace exporter are integrated manually: authenticated calls create a parent span, tools/database calls create child spans, and safe timeline events are attached to the call span. The call-start event stores a trace ID in its metadata so the clinic API can show that a trace is linked without returning the ID. Export is disabled until `OTEL_EXPORTER_OTLP_ENDPOINT` or `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is configured. No Azure Monitor, collector, or other trace destination has been selected or deployed. Example settings are in `backend/.env.example`.

Phase 3 remains open: there is no automatic FastAPI/HTTP instrumentation (intentionally, to avoid capturing tokenized URLs), no individual OpenAI request spans, no Realtime latency breakdown beyond emitted events, no metrics/log export, no sampling policy, and no consent-to-operation trace linkage. The new OTLP dependency pins were added to the lock file but package installation/resolution still needs CI verification.

Phase 4 discovery confirmed the original adapters discarded usage metadata and Realtime completion usage. That gap has an initial implementation below. Pricing still requires a dated provider/model-specific rate source; audio-duration proxies may only be added as explicitly labeled estimates, never as a bill.

Phase 4 now includes usage capture from OpenAI transcription responses when usage is returned, LangChain `AIMessage.usage_metadata` for Chained agent responses, and Realtime `response.done` usage. A new idempotent tenant-scoped usage table stores units/model/request identity; the clinic call detail displays reported units and explicitly labels missing usage as unknown and cost as not calculated. Usage rows are not linked to billing prices and do not include input text/audio. OpenAI TTS currently returns audio bytes without provider usage in this adapter, so no TTS cost is claimed. The owner applied `20260927000200_voice_usage_observability.sql`; the reported verification confirms the usage table, call index, RLS and staff policy all exist. An authorized provider call is still needed after application deployment to verify runtime usage data end to end.

This is the initial implementation slice, not the full Phases 1–2 acceptance scope: there is no retention job, transcript/recording policy, carrier callback reconciliation, global request trace, runtime-session/operation correlation, persistent collection-health alert, search, or automated retry reconciliation. Calls that fail before a valid stream start remain in existing provider logs rather than clinic history. The in-process collector is non-blocking and best effort; a process crash can lose queued events. Do not describe this as lossless or multi-replica reconciled yet.

The migration is additive and its schema checks passed in Supabase. The repository documents a historical migration-version collision; do not use automated migration push until the target ledger is reconciled. The new tables retain history indefinitely until the owner sets an approved retention policy.

Next: run CI to verify dependency resolution, deploy the backend/frontend changes, and make an authorized inbound test call for each engine. Confirm returned provider usage appears in clinic history and missing usage remains unknown. Prices remain uncalculated pending a dated provider rate source. `ruff`, Python bytecode compilation, frontend production build and `git diff --check` pass locally; Python package resolution could not be verified because dependency downloads are blocked in this environment.


## Call review redesign implementation — 27 September

- [x] Filtered call index with call status separated from business outcome.
- [x] Dedicated overview, conversation, turns, actions, performance, usage and diagnostics views.
- [x] New event occurrence/elapsed timing, tool/database correlation and sampled audio directions.
- [x] Opt-in message storage, existing tenant authorization, audited reads and expiry cleanup.
- [x] Safe connection-attempt history and additive migration/verification query.
- [x] Local regression checks and synthetic browser chat inspection.
- [ ] Apply `20260927000300_voice_review_observability.sql` in Supabase and verify.
- [ ] Deploy both applications; explicitly enable text capture for approved calls.
- [ ] Verify new conversation/turn/action evidence for both engines, interruptions and expiry.

This extends the initial slices described above: search, connection attempts, tool correlation and optional transcript retention are now implemented. It does not complete collector integration, recordings, evaluation, price calculation or scale hardening. Setup and operational limitations are documented in `CALL_REVIEW_SETUP.md`.

## Caller history — 27 September

- [x] Caller number column, phone search and clinic-scoped repeat-call counts.
- [x] Number link opens caller history; individual reviews link back.
- [x] Validated carrier identity capture; numbers excluded from technical events.
- [x] Additive migration applied to Supabase; column/index/RLS/policy and backend SQL verified.
- [x] Existing call number recovered from an exact trusted runtime-session match.
- [x] Synthetic browser test of repeated calls and review navigation.
- [ ] Deploy both applications and verify two new inbound calls from the same number.

See `CALLER_HISTORY_SETUP.md` for identity limitations, migration provenance and rollout.

## Enterprise investigation expansion — 27 September

The current enterprise capability matrix, screen specification, implementation sequence and
acceptance criteria are in [ENTERPRISE_VOICE_OBSERVABILITY_SPEC.md](ENTERPRISE_VOICE_OBSERVABILITY_SPEC.md).
This preserves technical depth and connects conversation, execution and durable business outcomes.

- [x] Live Realtime call history, caller repeat count and captured conversation observed in supplied screens.
- [x] Live booking commit verified in Supabase; earlier failed proposal remains separate.
- [x] Future configured fee corrected to INR 50000 minor units for the affected doctor.
- [x] Explicit currency-unit instructions/display and bounded event batching implemented.
- [x] Batch sequence/lifecycle SQL verified against Supabase using rolled-back synthetic data.
- [x] Capability matrix and enterprise screen specification prepared.
- [ ] Deploy these foundational code changes; verify fee wording and collection freshness.
- [ ] Complete correlation, enterprise views, evaluations, costing and platform monitoring.

Correlation implementation now propagates captured identifiers through async execution and exposes
exact chat source links, readback failure states and call-detail collection health. See
[VOICE_CORRELATION_IMPLEMENTATION.md](VOICE_CORRELATION_IMPLEMENTATION.md). Deployment and new
call acceptance remain pending; complete provider causal linkage is not claimed.

Earlier rollout checkboxes are historical snapshots. These observations verify Realtime behavior,
not Chained acceptance, recording support, cost accounting, OTLP delivery or load capacity.

### Connected investigation UI - 27 September 2026

- [x] Outcome summary and key milestones replace the overview raw event log.
- [x] Audited conversation messages link to exact captured identifiers without time-proximity guesses.
- [x] Execution trace provides scope, stage and search filters, measured waterfall and field inspector.
- [x] Operation status is separated from proposal/readback/approval event evidence.
- [x] Collection health exposes loaded ingestion delay, gaps, paging and runtime disagreement.
- [x] Usage shows input/output, audio and cached subsets; cost and incomplete coverage remain explicit.
- [x] Diagnostics filter issues and expand consecutive noise groups into every original event.
- [x] Frontend build and 25 tests pass; synthetic browser render, keyboard tab navigation and inspector checked.
- [ ] Deploy and verify new captured calls. Historical calls cannot reconstruct missing correlation.

No migration or secret changes required. Existing tenant authorization and audited transcript reads remain in use. Quality evaluations, dated pricing, version snapshots and fleet monitoring remain future phases.
