# Voice observability: implemented coverage and evidence limits

Reviewed 5 October 2026 against the current backend/frontend and owner-supplied context schema. The existing [enterprise observability specification](E:/Projects/Ai_receptionist/docs/ENTERPRISE_VOICE_OBSERVABILITY_SPEC.md) describes a broader capability roadmap; this record distinguishes current implementation from that roadmap.

## What the current section provides

The clinic call-history interface has seven investigation tabs: **Overview, Conversation, Execution trace, Business operations, Performance, Usage & cost, Diagnostics**. It links captured conversation messages to technical events, builds a scoped execution waterfall, exposes persisted business-operation outcomes, and allows filtering/inspection of safe event metadata. Separate conference presentation supports synthetic rehearsal and authenticated LIVE events.

The owner-provided schema includes `voice_observability_calls`, `voice_observability_events`, `voice_observability_usage`, `voice_observability_messages`, `voice_observability_content_access`, and `voice_observability_attempts`. Authoritative business transitions use separate `voice_call_sessions` and `voice_operation_records` tables. Observability is evidence about execution; its asynchronous collector is not the booking transaction authority.

| Investigation layer | Implemented evidence | Important boundary |
| --- | --- | --- |
| Connection and identity | Accepted/rejected/failed connection attempts; carrier call ID; review call UUID; normalized caller number, repeat count and filters | Connection attempts may not have enough IDs to join to a particular call; a phone number does not prove a person's identity |
| Lifecycle | Engine, start/end, duration, runtime status, persisted lifecycle and collection health | Ended means the call ended; it does not mean a requested task succeeded |
| Conversation | Optional retained caller transcription and assistant generated text/audio transcript; message source IDs; expiry and audited access | Text is not an audio recording or proof that generated speech was heard |
| Turns and responses | Captured caller turn/item, assistant item, response and generation identifiers | Some provider events lack a causal turn link; historical gaps remain unknown |
| Agent execution | Agent-stage events, selected tools, allow-listed result metadata and failure events | No hidden chain-of-thought; no complete versioned prompt/context snapshot store |
| Tools and database | Backend tool invocation IDs, query IDs, starts/completions/failures and durations; parent linkage and scoped waterfall | Instrumented paths only; nested query time overlaps parent tool time and must not be added twice |
| Proposal and consent | Proposal/operation IDs, prepared/sent/acknowledged readback, interruption/failure/timeout events, approval and mutation events | Carrier acknowledgement establishes playback completion under the provider protocol, not human comprehension |
| Business outcome | Persisted operation type, status and committed timestamp, correlated to captured operation events | Successful lookup/preview is not a committed appointment; operation ledger is authoritative |
| Audio and interruptions | Transfer counters, generation/response/segment links, clear/cancel/truncate and readback-interruption events where instrumented | No audio recordings, packet-quality analytics, or end-to-end hearing measurement |
| Performance | Chained stage timings, first-audio processing metrics and measured event/span timing | Realtime provider internals cannot be split into invented STT/LLM/TTS timings; fleet percentile dashboards are not implemented |
| Usage | Reported model/request identity, input/output tokens, audio/cached subsets and duration where provided | TTS/telephony coverage is incomplete; audio/cached counts are subsets, not extra tokens |
| Monetary cost | Schema has nullable `pricing_version` and `estimated_cost_microusd` fields | No implemented dated pricing calculation; UI explicitly says cost unavailable |
| Capture reliability | Event sequence, occurrence/ingestion evidence, completeness markers, bounded queue and lifecycle disagreement | Best-effort asynchronous persistence; process crashes and queue overflow can lose evidence |
| External tracing | Optional OpenTelemetry call/tool/query spans and OTLP exporter configuration | A trace ID/configured endpoint is not proof that the collector received it |
| Personal follow-ups | Separate Friday calls, attempts, messages, tool results, activity and memory records | The clinic's seven-tab investigation UI is not automatically a unified Friday trace viewer |

## How identifiers connect the evidence

The logical investigation path is:

```text
Caller history → call → captured message/turn → response
                          → tool invocation → database query
                          → proposal → readback segment → approval → committed operation
```

This path is traversable only where actual identifiers were captured. `message_source_id` connects conversation and dialogue evidence; `provider_tool_call_id` identifies the model's function invocation; `tool_invocation_id` identifies the backend execution; `query_id` identifies instrumented database work; `proposal_id`/`durable_operation_id` identify the business proposal and transaction; `playback_segment_id` identifies a controlled audio segment. A timestamp near another event is not a substitute for one of these links.

The final guide should include one annotated example of a successful booking and one interrupted/corrected readback. The example should explain which rows prove proposal preparation, audio transmission, carrier acknowledgement, later approval and commit, and mark any missing boundaries as unavailable.

## Broader observability roadmap

The repository specification already considers the larger set of possibilities: versioned prompts/policies/context and retrieval evidence, deterministic quality evaluation, dated pricing, infrastructure/deployment correlation, fleet metrics and alerts, richer recording/audio-quality evidence, and more durable telemetry delivery. These are valuable design topics, but they should be labelled future or partial capabilities according to the implementation.

Therefore the accurate publication claim is **“observability across instrumented voice, agent, tool, database and business-operation boundaries”**. “We trace everything possible” would overstate the current coverage and imply access to opaque provider internals.

## Sources

- [Investigation UI](E:/Projects/Ai_receptionist/frontend/src/components/CallInvestigation.tsx)
- [Call-history UI](E:/Projects/Ai_receptionist/frontend/src/components/VoiceCallHistoryPage.tsx)
- [Correlation and span helpers](E:/Projects/Ai_receptionist/frontend/src/lib/callReview.ts)
- [History and conversation API](E:/Projects/Ai_receptionist/backend/app/api/routes/voice_observability.py)
- [Persistent capture](E:/Projects/Ai_receptionist/backend/app/observability/capture.py)
- [Optional OTLP export](E:/Projects/Ai_receptionist/backend/app/observability/telemetry.py)
- [Correlation contract](E:/Projects/Ai_receptionist/docs/VOICE_CORRELATION_IMPLEMENTATION.md)
