# Enterprise voice observability: capability audit and screen specification

27 September 2026. Scope: the existing Chained and Realtime voice agents and clinic application. This is an implementation specification, not a certification or a claim that every capability below is available.

## Objective

An operator must establish what happened to a call and whether a business action committed. An architect must be able to investigate a particular utterance through its context, execution, dependencies, playback and durable outcome. All current viewers can access the same investigation surfaces; technical detail is progressively disclosed, not removed or hidden by new roles.

The navigation chain is: caller history → unique call → message/turn → response → tool/query → proposal → readback/confirmation → committed operation. Links must follow captured identifiers; time proximity alone is not proof of causality.

## Capability matrix

Status: Available = captured and exposed; Partial = some evidence exists but incomplete; Display gap = backend data exists but the UI does not use it; Missing = new instrumentation/storage required; Unavailable = evidence cannot currently be established.

| Capability | Current status and evidence | Work required | Destination |
|---|---|---|---|
| Unique call and repeat caller history | Available: call UUID, tenant-scoped normalized number, count and filters | Preserve unique-call navigation and clinic scope; a shared number is not a verified person | Call index/header |
| Connection attempts | Available: accepted, rejected configuration/authentication, failed | Correlate attempt to call where identifiers are supplied; record safe disconnect categories | Diagnostics/platform |
| Call lifecycle | Available but eventually consistent: start/end and monotonic duration | Batch writes; expose freshness and distinguish runtime status from delayed telemetry | Header/Overview |
| Conversation | Available when opted in: separate retained caller/assistant text; audited reads | Link messages to turns, responses and segments; keep evidence provenance | Conversation |
| Audio recordings | Unavailable: recording capture is not implemented | Separate consent, storage, retention and access design before enabling | Conversation, future |
| Caller turns | Partial: captured IDs and speech/transcription events | Propagate IDs consistently through response/tool/playback; avoid assigning uncorrelated events by guesswork | Execution/Conversation |
| Model responses | Partial: generation/response events and some request IDs | Stable response linkage, model and prompt version snapshots, safe termination/failure categories | Agent/Execution |
| Agent decision evidence | Partial: selected tools, execution results and policy-controlled business state | Show validated parameters, validation failures and allowed-tool/policy versions; do not claim hidden chain-of-thought | Agent/Workflow |
| Context supplied to agent | Partial: backend caller context, prompts and tool results exist at runtime | Version/source metadata and safe context snapshots; token budget/truncation evidence | Agent & Context |
| RAG/retrieval | No demonstrated production retrieval trace in this audit | Show only if implemented: document/source/version IDs, retrieval scores and actual context inclusion | Agent & Context |
| Tool execution | Available: invocation IDs, start/end/failure, duration | Correlate to turn/response and durable operation; expose safe validation/retry evidence | Execution/Workflow |
| Database work | Available: query IDs and parent tool linkage for instrumented work | Show child spans, failure categories and transaction outcome; redact sensitive SQL parameters | Execution/Diagnostics |
| Business transaction | Available: persisted operation type/status/time; proposal-to-commit runtime controls | Link appointment reference/detail through authorized API; show all recorded transitions and stopping point | Business Operations |
| Readback/confirmation | Partial: readback event, carrier acknowledgment and confirmation signals | Persist interrupted/failed/timed-out readback and invalidation reasons; distinguish prepared from played | Business Operations/Quality |
| Audio delivery | Partial: transfer counters, segments, carrier marks, interruption events | Segment-level start/end and buffer/codec boundaries where observable; aggregate chunks | Execution/Diagnostics |
| Turn latency | Partial: Chained timings and Realtime event boundaries | Match speech end to first audio sent by response ID; label boundary and missing data | Performance |
| Realtime model internal timings | Unavailable for opaque provider stages | Never manufacture separate STT/LLM/TTS timing from Realtime events | Performance |
| Provider usage | Available: normalized usage records; Display gap for audio/cached tokens | UI breakdown and idempotent request aggregation; explicit coverage and truncation flags | Usage & Cost |
| Cost | Missing: prices and cost calculation | Dated model/rate catalog; distinguish cached audio/text where needed; telephony/TTS coverage; currency conversion provenance | Usage & Cost |
| Evaluations | Missing in production review | Deterministic amount/date/action checks first, then documented human/model review; pass/fail/not evaluated with evidence | Quality |
| OpenTelemetry | Partial: optional OTLP traces and manual call/tool/query spans | Configure collector/export destination; verify delivery; sampling and metrics/log export remain open | Execution/platform |
| Trace navigation | Partial: API exposes trace availability, not trace ID | Authorized trace link and provider/destination validation; recording a trace ID is not export proof | Diagnostics |
| Telemetry health | Partial: ingestion delay, bounded queue, incomplete markers and logs | Expose queue depth/drops/freshness and alerting; durable queue/reconciliation for crash recovery | Platform/Diagnostics |
| Infrastructure/deployment | Missing from call review | Safe deployment/model/config version metadata; Azure restart/resource/concurrency metrics correlation | Platform |
| Audit/governance | Available for conversation access, expiry and existing tenant authorization/RLS | Configuration-change audit, operational retention policy and recording governance if introduced | Audit |

Sources in repository: `backend/app/observability/{capture,usage,telemetry}.py`, `backend/app/api/routes/voice_observability.py`, `backend/app/voice/{presentation,call_runtime,voicelink_realtime_gateway,readback_text}.py`, `frontend/src/components/VoiceCallHistoryPage.tsx`, `frontend/src/lib/callReview.ts`, existing observability migrations.

## Screen specification

### Call index and caller history

Purpose: find relevant calls across callers and time. Retain number, repeat count, engine, duration and separate lifecycle/outcome. Replace generic committed-action counts with evidence-backed action labels when the API supplies them. Add outcome/issue filters and server-side pagination before large-volume use. Connection failures belong in an investigation view, with a compact warning/link when they need attention. Display telemetry freshness; do not silently label a delayed ended call as active.

### Overview

Purpose: establish outcome, anomalies and next action. Show durable outcome, linked appointment, duration, engine, recording/transcript availability, evidence completeness and ingestion freshness. Present a short milestone summary with links to detailed evidence. Remove repeated audio/generation events from this summary, but retain them in Diagnostics. Distinguish no action requested, pending/unconfirmed, failed, committed and outcome unknown only when evidence supports the distinction.

### Conversation

Purpose: inspect what was recognized and generated. Show chat with caller/agent, language when measured, timestamps and provenance. Add linked workflow markers and per-message inspection of turn/response/playback. A prepared readback is not proof it was delivered; interruption and matching carrier acknowledgment must be separate evidence. Audited access and expiry remain mandatory. Never label transcripts as verbatim recordings.

### Execution trace

Purpose: explain one turn or the whole call, including concurrency. Tree: call → turn → response → tool → query; playback segments are linked to the generating response. Include start, duration, outcome and safe failure category. Use a shared, labeled time axis with zoom and a selected-span detail panel. Keep overlapping child database time inside its parent, not in additive totals. Uncorrelated events remain visibly uncorrelated. Raw frames aggregate into segment summaries with expandable detail.

The current Turns screen does not yet represent complete turn execution. Replace it only after linking conversation, response, tools and playback using real IDs; until then label its coverage honestly.

### Agent & Context

Purpose: inspect what the agent was given and what it selected. Show engine/model, versioned prompt/policy/tool definitions, context sources, safe tool result evidence, context budget/truncation and validation failures. Where RAG exists, show retrieval evidence and document versions. Context content access needs the same privacy design as transcripts. Do not display fictional model reasoning or imply provider internals are observable.

### Business Operations

Purpose: verify the authoritative outcome. Show proposal → prepared/readback sent → carrier acknowledged → caller approved → committing → committed, or recorded rejected/interrupted/expired/failed transitions. Clearly separate preview/tool success from database commit. Open the resulting appointment through existing authorization. Include idempotency and operation ID in technical inspection; do not expose signed offer tokens.

### Quality

Purpose: verify correctness. Initial checks: saved/configured/quoted amount consistency; selected versus committed doctor/date/session; required approval after readback; unsupported booking-success claims; missing result delivery. Each evaluation records rule/version, evidence references, scope, result, time and reviewer. Use pass/fail/not evaluated/insufficient evidence. Language quality and transcription correctness require reviewed ground truth; no arbitrary accuracy percentages.

### Performance

Purpose: explain delays. Lead with measured caller-end-of-speech to first audio sent, greeting first audio, tools, database and readback timings. State explicitly that audio sent is not human-perceived latency. Provide trace waterfall and comparison across calls/engines/languages only when sample size and coverage are available. Missing boundaries are unavailable, not zero. Fleet p50/p95/p99 require a well-defined population and time window.

### Usage & Cost

Purpose: explain resource consumption. Summaries by provider/model/operation; reported input/output tokens, audio tokens, cached input and duration. Audio/cached counts are subsets of total input/output, not extra tokens to add. Request identities prevent duplicate accounting. Expose missing components, record caps and estimated versus provider-reported units. Cost requires applicable dated rates and adequate modality/cache breakdown; unknown components must not be silently priced as zero. Include telephony/TTS separately before claiming complete per-call cost.

### Diagnostics

Purpose: investigate a precise technical issue. Default to errors, warnings and broken/incomplete stages; permit all events, stage/turn/operation filters, search and export with appropriate redaction/audit. Expose correlation IDs and trace links in advanced details. Show event occurrence separately from ingestion delay. Collapsing repeats must preserve their count and time range. Never export auth URL tokens, offer tokens, arbitrary patient values or raw provider exceptions by default.

### Platform and audit

Purpose: identify cross-call problems. Monitor connections, concurrent calls, completion/abandonment, queue health, telemetry drops/lag, resource usage, restarts and dependency availability. Correlate changes with deployment/prompt/model versions. Tenant-scoped analysis remains the default; do not create unapproved cross-tenant access. Audit configuration/content access and retention execution separately from business quality metrics.

## Visual semantics

Green = confirmed success; amber = pending/attention; red = failed check/operation; blue = currently processing; neutral = unavailable/not evaluated. Pair colors with text/icons. Ended is a lifecycle state, not a green success result. No rainbow assignment to every technical event. Keep diagrams dense enough for architects and use filters, zoom and drill-down instead of deleting evidence.

## Implementation sequence and progress

- [x] Audit current code and supplied screens; identify confusing presentation and missing correlation.
- [x] Verify latest appointment fee: 500 paise was stored, not 500 rupees.
- [x] Correct only the affected doctor's future configured fee to 50000 paise; historical appointments unchanged.
- [x] Add explicit fee units/display in booking offer and Realtime currency instructions.
- [x] Implement bounded consecutive-event batches with atomic per-call sequence allocation and lifecycle updates.
- [x] Verify batch SQL with 64 synthetic events across two calls in Supabase, fully rolled back.
- [x] Prepare this capability matrix and screen specification.
- [ ] Deploy foundational fixes and verify a new Hindi/Hinglish booking quotes and saves INR 50000 minor units.
- [ ] Verify production ingestion lag under actual concurrent calls; rollback probe is not a load test.
- [x] Add captured turn/response/message/segment/operation identifiers and call-detail collection-health fields.
- [ ] Verify correlation on deployed Chained/Realtime calls; missing provider causal links remain unknown.
- [x] Implement connected investigation views: message links, scoped waterfall, operation stages, usage breakdowns and searchable diagnostics.
- [ ] Verify deployed UI on new calls; evaluation, dated pricing and fleet views remain separate phases.
- [ ] Implement quality evaluation storage, dated pricing and verified usage coverage.
- [ ] Add fleet monitoring, alerts and crash/retry reconciliation.
- [ ] Verify Chained/Realtime success, changed request, interruption, dependency failure and wrong-fee detection.

No new migration is needed for this foundational batch writer or fee configuration correction. Future evaluation, version snapshots and correlation fields require explicit schema design. Use existing event JSON for safe scalar telemetry, separate messages for retained text, existing operation records for transaction truth, and usage records for accounting; do not create duplicate stores merely to add another tab.

The initial correlation implementation reuses existing message source IDs and event JSON and needs
no migration. See [VOICE_CORRELATION_IMPLEMENTATION.md](VOICE_CORRELATION_IMPLEMENTATION.md) for
the identifier contract, readback evidence and rollout limitations.

## Acceptance and remaining reliability limits

Batching is bounded at 64 consecutive events and adds no waiting window. A single SQL statement updates call summaries and inserts ordered events atomically. Non-event queue entries remain barriers so starts, messages and usage keep queue order. Database failures retry and mark affected calls incomplete. Queue overflow and process crashes remain best-effort limitations; this is not a lossless distributed collector. Ambiguous commit acknowledgments need idempotent event identities before claiming exactly-once retries. No fabricated telemetry should fill absent provider stages.

Design references: [OpenTelemetry signals](https://opentelemetry.io/docs/concepts/signals/) and [Langfuse trace structure](https://langfuse.com/docs/observability/best-practices). These inform separation of execution, metrics and evidence; they do not imply those products are deployed here.
