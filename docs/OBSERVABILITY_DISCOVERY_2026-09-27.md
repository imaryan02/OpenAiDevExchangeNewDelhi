# Observability discovery and implementation specification

Date: 27 September 2026. Scope: current source checkout, not a live deployment audit.

This document inventories the evidence we have and specifies the observability system to build next. No application changes, migrations, provider calls, recordings, messages or deployment were performed for this discovery. Statements marked existing describe source behavior, not proof that the corresponding production provider callback is configured.

## 1. Product boundary

Build a durable, tenant-scoped **Call History** area in the clinic workspace, with a call detail timeline linking conversation, tools, timing and business outcomes. Reuse the existing presentation renderer where useful, but keep production history separate from opt-in conference telemetry and synthetic rehearsal data.

Use OpenTelemetry for operational traces and metrics and a custom dashboard for voice-specific inspection. Store call metadata and business audit evidence in PostgreSQL. Conversation content is separately permissioned. Audio recording is optional and requires its own consent, retention and storage design.

One call is a record containing many turns, responses, tool invocations and events. Calls are not stored under a phone number as their primary key. Link known contacts within an organization; preserve unmatched callers and reassigned/shared-number cases. Caller ID is routing/lookup information, not sufficient proof of patient authority.

## 2. Evidence inventory

Legend: **P** persisted application data; **L** structured logs; **D** temporary demo telemetry; **R** obtainable in the current runtime but not durably captured; **N** new instrumentation, storage or feature required. Multiple labels indicate partial coverage.

| Area / field | Today | Evidence / gap | Required implementation |
| --- | --- | --- | --- |
| Carrier call and stream IDs | L/R; P for Realtime runtime | Both gateways validate start metadata; Realtime session table stores provider_call_id | Canonical observability call ID and provider ID mapping for both engines |
| Organization and voice actor | P/R | Voice settings route to an organization/actor; runtime and tools are scoped | Snapshot safe routing IDs on call record; do not export credentials |
| Actual engine | L/D/R | Canary routing can enter Realtime gateway then fall back to Chained | Record selected engine, actual engine segments and fallback reason separately |
| Connection acceptance/rejection | L | voice.py logs incomplete configuration and invalid stream token | Durable safe connection attempt and stage/error code |
| Failure before start metadata | L/N | A rejected connection may have no provider call ID or trusted tenant | Connection-attempt ID; platform-only unassigned record until trusted routing is established |
| Call start/end | L/D; P for Realtime | Gateway lifecycle events and runtime status | Common lifecycle model for both; terminal reason and evidence provenance |
| Provider lifecycle callback | L/R | /voicelink/events logs event, callId, direction, callStatus, duration; actual subscription not verified | Validate schema, authenticate, correlate, persist and deduplicate callbacks |
| Caller phone | R/P for Realtime | Normalized incoming metadata; logs generally use suffixes | Restricted tenant contact reference and safe lookup token; masked list display |
| Caller/contact name and recognition | R/D | lookup_caller_family result | Nullable contact linkage and lookup outcome; no guessed identity |
| Patient and family relationship | P/R | Contact-patient relationships and appointment snapshots | Per-operation patient links; one caller can discuss multiple patients |
| Direction | R/L | Available in some provider callbacks | Nullable direction and source; never invent it if absent |
| Caller utterance / transcript | R/D | Chained STT result; Realtime input transcription; demo content gated/truncated | Separate content capture setting, provenance, turn ID and controlled retention |
| Assistant text | R/D | Chained reply and Realtime output transcript | Separate generated content from sent/acknowledged/interrupted speech |
| Original input/output audio | R only | Audio passes through gateways; presentation explicitly does not store it | Optional asynchronous capture, protected object storage and manifest; disabled initially |
| Language | R/N | Consent/proposal may contain language, but no uniform measured call-language field | Language per turn with source and unknown state; human labels where needed |
| Speech start/stop | R/D/L partial | Local turn detector and Realtime provider events | Uniform timestamps and source; no claim all events are emitted by both engines |
| Chained captured/dequeued turns | L | CapturedTurn IDs, queue depth, age and audio duration | Durable event mapping and turn metrics |
| Queue overflow / expired turn | L | TURN_BACKLOG_EXCEEDED and TURN_EXPIRED paths | Rejection reason, counts and alertable queue pressure |
| Echo/duplicate suppression | L | Chained heuristic suppression | Record safe decision and turn link; review false positives with permitted audio |
| Chained stage latency | L | stt_ms, agent_ms, tts_first_audio_ms, tts_and_playback_ms | Persist compatible measurements; definitions below; existing timing is not end-to-end latency |
| Greeting first audio | L partial | Chained _send tracks first audio sent | Standard connection/start/first-greeting clocks across engines |
| Realtime audio buffering | R | Playback queue bytes, epochs and response generation state | Queue gauges, waiting time, cancellation and stale output events |
| Playback mark acknowledgments | R/L/D partial | Realtime marks and controlled ledger; Chained event/estimated-duration handling | Acknowledgment source, segment ID and interruption reason; distinguish timer fallback |
| Readback preparation/completion | P/R/D | Runtime state plus controlled playback ledger | Proposal/segment linkage and append-only transition evidence |
| Approval / change / refusal / unclear | R/P/D partial | ConfirmationIntentClassifier and operation states | Safe intent outcome and correlated caller turn; no codes or secrets in telemetry |
| Operations and current status | P | voice_operation_records: proposal version, idempotency key, result, timestamps | Use ledger as authoritative outcome; add timeline without rewriting consent state |
| Full transition history | N | Operation row is updated; persisted current state is not an immutable transition history | Append safe transition audit evidence transactionally where necessary |
| Tool/database duration and summary | D/R | ToolExecutor emits tool/database events only to enrolled presentation scope | General-purpose spans and durable sanitized invocation references |
| Transaction commit / uncertainty | P/L/D partial | Runtime fences uncertain commits; result and state vary by path | COMMITTED/FAILED/UNKNOWN or unresolved outcome with positive evidence; absence is not rollback |
| Chained mutation blocking | R/D | allow_appointment_mutations=False | Explicit policy-denied outcome, not generic system failure |
| Appointment quote/contact/consent | P | Appointment snapshots and source fields | Role-controlled business links; preserve historical snapshot, not current join only |
| Cancellation/reschedule/payment visibility | P | Appointment linkage and payment attempts | Multiple operation rows per call; simulated payments labeled; no settlement claims |
| Provider/model/prompt versions | R/N | Models in Settings, instructions in source | Safe model, voice, instruction hash, configuration fingerprint and release SHA snapshot |
| LLM token/audio usage | N/R | No explicit application usage ledger found; Realtime loop does not capture response.done usage | Capture supported provider usage; text response metadata; classifier usage; unknown when absent |
| Estimated cost / invoice reconciliation | N | No cost ledger | Versioned rates, cache-aware usage and separate telephony/infrastructure allocations |
| HTTP request correlation | L | CorrelationIdMiddleware, JSON logs | Map to validated internal trace IDs; middleware does not automatically cover WebSocket lifecycle |
| Call-wide tracing IDs | N | HTTP, provider, presentation and operation IDs are distinct | Explicit mapping; never equate presentation's random operation ID with durable proposal ID |
| Background maintenance | L/P | Hold, verification and stale-session expiry; rolling schedules | Job run status/duration/heartbeat and last successful run |
| Outbox | P/L/R | Claims, retries and errors; provider send result currently discarded by dispatcher | Persist provider message reference/status when enabled; acceptance is not delivery |
| Notification consent | P | messaging_consent gate | Separate from transcript/recording consent; WhatsApp testing remains deferred |
| Staff/frontend errors | R/N | UI/API failure responses and auth refresh paths | Browser instrumentation with safe request/trace links and action outcomes |
| Platform health | R/L | /health/live and SQL /health/ready; deployment readiness gate | Historical probes, dependency/error/resource metrics; health check is not carrier acceptance |
| Existing audit table | P/N | audit_events schema and append-only trigger exist | Audit coverage and reader permissions must be implemented/verified; schema alone is insufficient |
| Cross-tenant platform super admin | N | Existing roles: ORG_ADMIN, RECEPTIONIST, VIEWER | Separate explicit platform authorization, scoped support grants and access audit |
| OpenTelemetry export | N | No configured OTel SDK/exporter found | Instrumentation, bounded exporter, backend and collection-health metrics |
| LangSmith integration | N | langsmith exists transitively in lock; no configured tracing integration found | Optional backend choice, not an existing observability capability |
| Document RAG and retrieval tracing | N | Current tools query clinic/business data; no general document retrieval pipeline | Future extension only; not represented as current functionality |

## 3. Source map

- `backend/app/api/routes/voice.py`: stream authentication/routing, error closure and carrier callback.
- `backend/app/voice/events.py`: event structure with call/turn/generation/playback/operation IDs and local monotonic time.
- `backend/app/voice/voicelink_gateway.py`: Chained receiver/queue/worker, STT, graph, TTS and playback.
- `backend/app/voice/voicelink_realtime_gateway.py`: Realtime event consumer, output queue, cancellation, tools and readbacks.
- `backend/app/voice/presentation.py`, `backend/app/api/routes/presentation.py`: demo-only capture, redaction, bounded memory and SSE.
- `backend/app/agent/tools.py`: tool wrapper and query timing; presentation-safe argument/result allowlists.
- `backend/app/agent/service.py`, `backend/app/agent/graph.py`: model invocation, graph state and in-memory checkpoint.
- `backend/app/voice/session_store.py`, `backend/app/agent/operation_service.py`, `backend/app/voice/call_runtime.py`: persisted state and transaction lifecycle.
- `backend/app/voice/confirmation_intent.py`, `readback.py`, `readback_player.py`: intent interpretation and playback evidence.
- `backend/app/core/logging.py`, `request_context.py`: structured logs and HTTP correlation.
- `backend/app/services/maintenance.py`, `outbox.py`, `health.py`: jobs and readiness.
- `supabase/migrations/20260912000100_voice_call_sessions.sql`: call runtime and operation tables.
- `supabase/migrations/20260910000100_phase1_tenant_foundation.sql`: memberships and audit foundation.
- `frontend/src/components/PresentationPage.tsx`, `Observatory.tsx`, `frontend/src/presentation/`: reusable rendering and SSE behavior.

## 4. Canonical record and identity model

Use a new `observability_calls` summary for **both** engines. Do not expand the consent runtime into an all-purpose telemetry store or create fake Realtime runtime rows for Chained calls.

Proposed fields: id, organization_id, provider, provider_call_id, connection_attempt_id, stream reference, contact_id nullable, restricted phone linkage, direction nullable, selected engine, actual engine history, started_at, connected_at, first_audio_sent_at, ended_at, lifecycle status, terminal reason, business outcome summary, capture-policy snapshot, release/model/config references, last_event_at and evidence completeness.

Unique trusted provider identity: organization + provider + provider_call_id. Use provider identity to correlate reconnects; a new stream ID alone does not prove a new call. Unknown/pre-auth attempts remain separate and do not get assigned to a tenant based on attacker-supplied metadata.

Maintain call-to-runtime-session and call-to-operation links explicitly. A call can have zero or many operations and patients. A committed booking followed by failed rescheduling is not accurately described by one `success` boolean.

History is scoped to organization and contact identity. Keep a restricted normalized-phone search capability for unmatched callers, with an HMAC-based lookup value using a dedicated managed key where appropriate. Plain hashes of phone numbers are enumerable. Matching a phone is a search result, not automatic authority or a permanent identity link.

Existing payment and consent snapshots may contain personal data; summaries must select safe fields. Never return entire JSON blobs to the frontend by default.

## 5. Storage separation

| Store | Purpose | Reliability policy |
| --- | --- | --- |
| observability_calls | Durable lifecycle summary and business links | Idempotent updates; explicit incomplete/unresolved status; reconciliation after crashes |
| observability_call_events | Bounded-volume timeline events with schema version, source, sequence and identifiers | Append/deduplicate; capture policy; telemetry gaps visible |
| Restricted conversation segments | Caller transcripts and generated assistant text, speaker/turn/response/segment links | Optional separate permission, redaction/encryption and retention |
| Recording manifest + object storage | Input/output segments, offsets, format, checksum, consent reference and storage key | Optional; short-lived authorized playback links; gaps and deletions explicit |
| Existing operation ledger + append-only audit evidence | Approval and consequential business outcomes | Transactional evidence; never sampled or dependent on the telemetry exporter |
| OTel backend | Detailed diagnostic spans, logs and metric aggregates | Asynchronous bounded export; sampling/retention configured; collection health monitored |
| Review/usage records | Human quality labels and provider usage/cost estimates | Provenance, reviewer/version and rate-version references |

PostgreSQL can serve early call summaries and selected events. Do not store every audio packet or arbitrary raw provider payload in PostgreSQL. Index tenant + start time + stable ID, call + event sequence, operation links and safe error categories; use cursor pagination. Partition or move high-volume diagnostics according to measured volume.

One call can group multiple turn traces. Long-lived call IDs and span/trace links should not require keeping one huge trace open for the whole call. Carry explicit context into background tasks. Collector arrival order is not necessarily event order.

## 6. Event contract

Common fields: schema_version, event_id, event_type, source, organization_id when trusted, observability_call_id, provider_call_id when known, turn_id, response_id, generation_id, playback_segment_id, proposal_id, operation_id, tool_invocation_id, trace_id, span_id, occurred_at UTC, process instance/boot identifier, source sequence, duration_ms where meaningful, safe status/error code and allowlisted metadata.

Use a shared event sink independent of presentation enrollment. Presentation can subscribe to sanitized events; it is not the authoritative sink. Normalize events across engines but preserve their provenance and different capabilities. Additive instrumentation must not alter consent decisions.

Groups to implement:

- Connection: attempt, authenticated, rejected, start_validated, start_rejected, provider_connected/disconnected, callback_received, end_observed.
- Input: speech_started/stopped, turn_captured/dequeued/expired, transcript_completed/failed, suspected_echo_suppressed, duplicate_suppressed.
- Generation: request_started/completed/failed/cancelled, response_obsoleted, first_audio_generated, usage_reported.
- Playback: segment_prepared/sent, first_audio_sent, mark_acknowledged, interrupted, timeout, clear_sent, late_ack_ignored, queue_pressure.
- Tools: requested/validated/rejected/started/completed/failed/cancelled, safe result summary.
- Operations: proposed, proposal_invalidated, readback_started/acknowledged/interrupted, intent_classified, approval_accepted/rejected, commit_started/confirmed/uncertain, reconciliation_started/resolved/unresolved.
- Runtime: checkpoint/state write outcome, ownership/version conflict, expiry, cleanup failure.
- Collection: export failure/drop, recording gap, missing lifecycle event, capture disabled or content expired.

No API keys, stream tokens, JWTs, verification codes, owner tokens, signed offers, raw idempotency secrets, full query strings, arbitrary exception bodies or unrestricted tool arguments. Redaction must happen before export, not only in the dashboard.

## 7. Metrics and correct definitions

| Metric | Definition / caveat |
| --- | --- |
| Greeting delay | Validated stream start to first greeting audio sent; carrier dial-to-answer needs carrier evidence |
| Turn response delay | Caller speech end to first response audio sent; distinguish filler from substantive reply |
| Caller-perceived delay | Use playback-start evidence when available; do not relabel send time as heard time |
| Chained stage delay | Endpointing, queue wait, STT, agent/tools, TTS first audio and transport separately |
| Realtime delay | Turn finalization/application wait, response/tool work, first audio and playback buffering |
| Interruption reaction | Detected speech onset to clear/cancellation action; carrier stop time only when measurable |
| Playback completion | Explicit acknowledged / interrupted / estimated-duration / unknown states |
| Call/operation outcome | Normal call closure separate from task success; multiple outcomes per call |
| Availability/conflict rate | Tool/business conflict counts with denominators; expected rejection is not always outage |
| Usage/cost | Provider-supported counts with source; absent usage is unknown, not zero; reconcile estimates |
| Quality | Human/benchmark labels with sample size; model confidence is not measured accuracy |
| Health | Attempts, established streams, greetings, failures by stage; avoid counting unidentified HTTP probes as calls |
| Collection completeness | Dropped events, recording gaps and export delay; missing evidence remains visible |

Use monotonic differences inside a process, UTC timestamps for cross-service alignment and synchronized clocks. Existing monotonic_ms is not globally comparable across replicas/restarts. Overlapping spans are not summed as a sequential delay. Report p50/p95/p99 with sample size and comparable cohort. Do not infer language from engine or consent-language field.

Low-cardinality metric labels: engine, stage, safe error category, environment and bounded language/model dimensions. Put call IDs, phone/contact IDs and arbitrary queries in authorized records/traces, not metric labels.

## 8. UI specification

Clinic workspace navigation: **Call History**. Keep **Inside the call** for presentation/rehearsal. Clearly separate live observations, historical records and synthetic scenarios.

### Call list

Filters: date range, engine, lifecycle, operation outcome, safe error category, contact/authorized phone search; language only when supported by evidence. Cursor pagination and export permissions required.

Illustrative record, not observed production data:

| Call | Started (clinic timezone) | Caller | Engine | Duration | Lifecycle | Business outcome | Content | Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CALL-001 | 27 Sep, 10:30 | Known contact / masked phone | Realtime | 3m 42s | Ended normally | Booking committed | Transcript disabled; recording not captured | View |

Duration, language and outcome display `Unknown`/`Unavailable` until supported. Never show a green success merely because CALL_ENDED was emitted in a finally block.

### Call detail

1. Overview: source/engine segments, release, timeline bounds, lifecycle, trusted identity linkage and evidence completeness.
2. Conversation: permitted text, source, turn and playback status; content-disabled/expired state explained.
3. Timeline: chronological events with filters, overlapping work, interruptions and gaps.
4. Tools: validated safe arguments, result/error category, timing, trace link and backend authorization outcome.
5. Operations/consent: one card per proposal/operation, exact authorized details for permitted roles, readback and approval evidence, actual commit state.
6. Performance: per-turn waterfall, substantive first audio, queue pressure and p95 cohort comparison.
7. Usage/cost: reported versus estimated versus unavailable; pricing version and retry/discard usage.
8. Recordings: optional input/output tracks, gap/consent/retention status and auditable playback access.
9. Review: human labels, notes and supported benchmark references; no automatic fabricated quality score.

Later pages: platform health, aggregate cost, quality review and active calls. All data access remains server-authorized; hiding a tab is insufficient.

## 9. Access model

Existing membership roles are ORG_ADMIN, RECEPTIONIST and VIEWER. Current presentation API permits any active organization member. That rule must not automatically carry over to recordings, transcripts or full technical traces.

Proposed default:

| Capability | ORG_ADMIN | RECEPTIONIST | VIEWER | Platform operator (new) |
| --- | --- | --- | --- | --- |
| Own-clinic call summary | Yes | Yes | Restricted aggregate only | Aggregate operational metadata through separate authorization |
| Contact/patient-linked outcomes | Yes | Within normal clinic permissions | No by default | No automatic access |
| Conversation text/recordings | Separate content permission and enabled policy | Explicit grant only | No | Time-limited scoped support grant only |
| Technical trace detail | Redacted diagnostic view | Safe failure summary | No | Redacted platform diagnostics |
| Content export/delete policy | Explicit admin capability + audit | No | No | Separate operational policy, not blanket tenant access |

Do not overload ORG_ADMIN into platform super admin. Introduce explicit platform authorization and support grants if a platform portal is required. Audit sensitive reads/playback/export as well as writes. Enforce tenant-qualified joins, backend permissions, effective SQL role/grants and restrictive RLS for new tables. Revalidate permissions on long-lived streams.

## 10. Capture, privacy and retention decisions

- Operational metadata on for real calls; optional conversation and recording capture off initially.
- Notification messaging consent is not recording/transcript consent.
- Capture policy snapshot per call records permitted fields, purpose, disclosure/consent evidence and retention class.
- Existing regex redaction protects some numbers/emails/IDs but not all clinical content or names. Use allowlists and selective content capture, not regex-only privacy claims.
- No personalized filler text in general operational logs: current filler logging can contain a first name and needs normalization.
- Unknown/error exception strings may contain provider payload or personal data; normalize before export.
- Object keys do not contain raw phone numbers or patient names. Signed playback URLs are short-lived and authorization checked at issuance.
- Separate retention for metadata, diagnostics, transcripts, recordings and required audit evidence. Concrete periods are a policy decision, not assumed from demo TTL.
- Purge jobs cover indexes, objects, caches and exports; preserve approved legal-hold/audit exceptions. Do not weaken existing append-only audit behavior blindly.
- No retroactive transcripts, recordings, exact latency or costs can be reconstructed where they were never retained. Existing logs and durable operation rows can support partial historical import, explicitly labeled incomplete.

## 11. Ingestion and failure handling

Persist call summaries and selected safe timeline events with bounded asynchronous processing; keep external telemetry export out of the speech critical path. Use idempotent event IDs and bounded queues. Detailed diagnostics may be sampled, but lifecycle summaries and business evidence use their dedicated reliable path.

Exporter failure must not stop a call. Queue/drop/retry health is observable; an overflow must not create a false complete history. Backoff and bounded retention prevent telemetry from exhausting memory or database connections. A restart marks abandoned observability calls unresolved/interrupted based on evidence rather than inventing a normal end.

Sensitive operation audit remains part of the business transaction or its durable outbox, not a best-effort logging callback. Critical metadata durability should be specified explicitly; do not promise lossless capture with an in-memory queue alone. A dedicated durable ingestion/outbox can be added when required.

Provider callbacks may be duplicated, late or reordered. Store occurrence and receipt time where available, correlate trusted IDs and resolve conflicts by explicit lifecycle rules. Authentication rejection is recorded without the supplied secret or arbitrary payload.

Use one telemetry backend first (e.g. Azure Monitor for the Azure deployment); detailed agent tooling such as Langfuse or LangSmith is optional. The custom dashboard's call/audit API should not depend on a specific vendor's internal trace schema. No new telemetry vendor is connected during this discovery.

## 12. Proposed read APIs

- GET /v1/observability/calls: tenant-scoped cursor list and supported filters.
- GET /v1/observability/calls/{id}: safe summary and completeness/capture metadata.
- GET /v1/observability/calls/{id}/events: bounded cursor timeline, optionally resumable live transport.
- GET /v1/observability/calls/{id}/operations: trusted ledger links and permitted evidence.
- GET /v1/observability/calls/{id}/conversation: separate content permission.
- POST /v1/observability/calls/{id}/recordings/{recording_id}/access: authorized short-lived URL and access audit.
- POST /v1/observability/calls/{id}/reviews: permitted human assessment with source/version.
- GET /v1/observability/metrics: scoped aggregate metrics with definitions/sample size.

These are design proposals only. A tenant query parameter is not authorization. Recording access needs a non-cacheable response and no signed URL in general logs. Distinguish missing, not captured, expired, permission denied and incomplete states without revealing another tenant's record.

## 13. Build sequence and acceptance evidence

### Stage 1: Durable call history for both engines

Deliver canonical IDs, connection/lifecycle instrumentation, safe summaries/events, database schema and clinic list/detail APIs/UI. Preserve demo behavior. Resolve historical migration-ledger ambiguity before applying the additive migration; do not run all historical migrations blindly.

Acceptance: both engines create correctly scoped records; rejected/early-disconnect cases are represented safely; repeat callbacks do not duplicate calls; cursor pagination is stable; restart/incomplete evidence visible; no content leakage or business behavior changes.

### Stage 2: Timing, tools and operations

Deliver OTel spans and explicit voice metrics; safe tool and graph timing; operation ledger links; shared clocks/context; playback acknowledgment versus estimation; stale/denied/uncertain outcome detail.

Acceptance: a slow turn identifies its actual stage; correction/playback interruption remains correctly correlated; transaction evidence matches ledger; Chained policy block is clear; provider/model errors remain distinguishable.

### Stage 3: Permissioned conversation review

Deliver optional durable transcript capture, roles/capture controls, sensitive-access audit and retention jobs. Recording requires an additional consent/storage implementation and designated acceptance audio; not automatically included with transcript capture.

Acceptance: capture disabled persists no content; restricted users cannot read/export it; opted-in call text/audio is correctly aligned; interrupted speech is labeled; expired/deleted content unavailable; missing segments explicit.

### Stage 4: Usage, quality and operational monitoring

Deliver provider usage capture, versioned estimates, cost summaries, human review, alerts, maintenance/outbox/frontend/platform metrics and collection-health monitoring.

Acceptance: unsupported usage shown unknown; counted usage reconciles with provider evidence; quality reports include sample size and review provenance; alerts actionable; no noise/denied action misclassified as outage.

### Stage 5: Scale and platform administration

Deliver shared live discovery across replicas, ingestion load validation, data partitioning as justified, platform roles and scoped support access. Broad RAG, live payments and human transfer remain separate product projects; their telemetry can be added when they exist.

Acceptance: calls remain visible across replicas, ingestion backpressure does not delay speech, tenant isolation holds, sensitive access is audited, and telemetry storage/retention cost is measured.

## 14. Decisions before dependent implementation

Recommended initial defaults: clinic-scoped Call History; summaries and safe timeline only; content capture disabled; no audio recordings; existing operation ledger retained; OTel backend configurable; platform content access absent until explicit roles/grants exist.

Resolve before each relevant stage: metadata/content retention periods; transcript/recording disclosure and permission; hosting/storage destination; expected call volume; technical-view role grants; platform-admin/support workflow; provider callback capabilities and subscription; regional-language quality acceptance. Current consent SQL supports English/Hindi variants only, so observing Marathi does not establish supported Marathi booking consent.

This discovery can proceed to Stage 1 implementation without promising later recording, provider delivery, broad multilingual transaction support or enterprise capacity. No production migration or deployment is part of this document-only step.
