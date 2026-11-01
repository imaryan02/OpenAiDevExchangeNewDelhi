# Voice correlation implementation

27 September 2026. This is the instrumentation phase preceding the enterprise UI redesign.

## Evidence links now captured

| Identifier | Meaning | Captured from |
|---|---|---|
| Observability call UUID | Unique review record within a tenant | Existing call collector |
| `caller_turn_id` | Captured Chained turn or durable Realtime turn | Existing turn queue/runtime |
| `caller_item_id` | Provider's caller utterance identifier | Realtime speech/STT events; carried through durable turn capture |
| `assistant_item_id` | Provider's output item identifier | Realtime output events and playback |
| `response_id` | Provider response that generated output/tool activity | Provider event/response object; restored in playback worker |
| `provider_tool_call_id` | Provider function invocation | Realtime function-call output item |
| `tool_invocation_id` | Backend execution invocation | Existing tool scope; nested queries retain parent ID |
| `query_id` | Instrumented database operation | Existing database instrumentation |
| `message_source_id` / message `source_id` | Exact link between chat and its dialogue event | One shared ID allocated before storing/emitting a message |
| `playback_segment_id` | Readback or carrier completion-mark segment | Readback ledger/normal playback mark |
| `proposal_id`, `durable_operation_id` | Persisted operation being presented/committed | Runtime proposal and confirmation transaction |

The existing `operation_id` field can represent a tool invocation in conference telemetry.
Use `durable_operation_id` for business-ledger correlation; do not treat these as interchangeable.

## Propagation

An immutable-by-use, task-local ContextVar scope carries only allowlisted scalar identifiers.
Each scope copies values and resets on exit. Async child tool/agent tasks inherit the scope
at creation, while the independent playback worker restores links from the queued provider event.
Chained STT, agent, tools/database work and messages share the actual captured turn ID.
Realtime ready caller items each have their own scope, even when one callback drains multiple items.

No relation is fabricated from "latest turn" or timestamp proximity. Provider responses without
a captured causal caller link remain unlinked to a caller turn. Existing historical calls are not
backfilled with guessed identifiers. Unknown IDs stay unavailable.

## Readback evidence

- `proposal_persisted`: emitted only after the proposal transition commits.
- `readback`: text prepared with exact ledger segment, message source and operation link.
- `readback_sent`: audio and completion mark were sent; does not prove hearing.
- `readback_acknowledged`: matching carrier mark accepted by the playback ledger.
- `awaiting_confirmation`: durable acknowledgment succeeded and approval is awaited.
- `readback_interrupted`: speech detection interrupted the controlled segment.
- `readback_failed`: preparation/synthesis/transport did not finish; exception class only.
- `readback_timeout`: matching operation/segment did not receive its acknowledgment in time.
- Approval/commit/failure events and their nested tools use the real durable operation ID.

Initial greeting segments have no business-operation ID. Prepared/generated text remains separate
from sent/acknowledged playback. No confirmation safety rules or appointment mutation authorization
were relaxed. Each readback captures its local link snapshot so an older failed task cannot acquire
the IDs of a newer segment.

## API additions

The existing audited conversation endpoint returns `source_id`; text is still expiry-filtered,
tenant-scoped and withheld unless the access audit commits. It can be joined to safe dialogue
events using `message_source_id` and speaker.

Call detail includes `collection_health`: fetch timestamp, last persisted event's occurrence time,
capture completeness, loaded event count, whether another event page exists, maximum ingestion
delay measured in the loaded page, and runtime/telemetry lifecycle disagreement. These are not
fleet metrics or a claim that the queue is empty. Missing measured delay is null, not zero.

## Rollout

No new secrets or DB migration are required. Existing message source IDs and event JSON support
these changes. Deploy the backend, make a new call, then verify linked identifiers and readback
states. The enterprise execution/chat inspection UI is the next phase; this document does not
claim that new investigation views or production telemetry export have been deployed.

## Verification

Regression checks cover concurrent-task isolation, shared chat/event identity, sensitive-field
exclusion, provider caller/output distinction, readback failure linkage, and collection-health
reporting. Existing booking, cancellation, reschedule and interruption tests remain required.
