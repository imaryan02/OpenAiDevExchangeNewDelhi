# Voice agent industry upgrade plan

## Semantic confirmation implementation — 13 September 2026

- Realtime confirmation now uses `ConfirmationIntentClassifier`: the server-owned readback and latest caller transcript go to the configured OpenAI text model with a strict CONFIRM/CHANGE/DECLINE/UNCLEAR schema. The previous phrase matcher is no longer used by the Realtime gateway.
- CONFIRM dispatches the existing private booking/operation only after carrier playback acknowledgement. CHANGE/DECLINE withdraw it; UNCLEAR asks a contextual clarification. Model failure/refusal/malformed output cannot approve. New speech or a replaced pending offer invalidates an in-flight interpretation.
- Semantic VAD remains enabled; automatic response creation is disabled. The backend requests the conversational reply after interpreting/capturing the caller turn, preventing premature waiting speech. Failed preparation and unsuccessful booking results explicitly resume dialogue.
- Uses existing OPENAI_API_KEY and OPENAI_MODEL (gpt-4o-mini if unset). No new environment variable or database migration. This adds one bounded text-model request after a completed summary; it depends on the caller transcript being delivered accurately.
- Validation: complete offline backend suite passed with 8 live DB tests skipped; expanded focused suite passed (50 tests). Live OpenAI synthetic classification: 11/11 expected intents including Hindi/Hinglish approvals, changes, refusal, payment questions, unclear audio and instruction manipulation. No real appointment was created by these checks.
- Deployment acceptance remains a successful telephone booking and matching dashboard/payment record. Do not equate synthetic classification with a completed end-to-end live booking.

## Booking verification follow-up — 13 September 2026

- Latest supplied call: controlled readback acknowledged; pending booking preserved; all three later replies classified as non-approval. No final booking dispatch was established by those logs. The reported Hinglish phrases are now covered by gateway dispatch regressions.
- Read-only check against the database configured in local backend settings passed: both booking SQL functions exist, configured voice actor has organization membership, and payment constraints support `DUE_AT_CLINIC`. This does not verify Azure configuration parity or execute a booking.
- Found and fixed silent handling of a rejected/unsuccessful booking result in the Realtime gateway. The model now receives failure context and requests a fresh availability check instead of waiting indefinitely. Dispatch start/completion logs distinguish confirmation failure from booking execution.
- Validation: 79 focused tests passed across approval, Realtime gateway, atomic booking, runtime, booking controller, and booking errors. Database transaction tests use mocks; no live appointment was created.
- Remaining acceptance: deploy, complete one live telephone booking, verify its confirmed dashboard record and due-at-clinic payment. Unknown commit outcomes still require reconciliation; do not claim end-to-end readiness before live evidence exists.

## Latest continuation — 13 September 2026

This section supersedes the handoff's older validation counts and statements that no reconciliation/canary code exists. Phase 3 remains incomplete.

- Added `VoiceCallRuntime.reconcile_booking(fresh_session)` and a tenant/session/owner/caller/operation/version-scoped committed-result query. After an uncertain booking commit, a separate database session can retrieve positive persisted success without replaying the mutation. Missing evidence stays unresolved, malformed success records are rejected, and the uncertain runtime remains fenced. This does not yet handle restart recovery, resume the call, or connect reconciliation to the live gateway.
- Added `VOICE_REALTIME_CANARY_CALLERS`, a validated JSON list of exact E.164 numbers. When nonempty, only listed callers reach Realtime; all other callers use the chained engine, even if `VOICE_ENGINE=realtime`. The list can select internal callers while the global engine remains chained. An empty list leaves `VOICE_ENGINE` in control. Selection uses validated carrier start metadata after endpoint authentication, before Realtime connection/state creation; the original start message is handed to the legacy adapter. Settings are selected once per call. No real environment settings were changed and the example defaults to an empty list.
- Tests cover commit-result isolation, missing/malformed evidence, no duplicate booking after reconciliation, configuration validation, and both canary routing branches. Full suite: **194 passed, 8 live DB tests skipped**; Ruff clean, Mypy clean across 65 source files, and `git diff --check` passed. Live DB/carrier acceptance remains unverified.

Next priorities remain: actual booking proposal/readback/approval/atomic-result gateway wiring; equivalent cancellation/rescheduling guards; response suppression and delivered-readback context synchronization; bounded missing-transcript/mark recovery; reconciliation integration/restart behavior; then controlled database and carrier acceptance. The canary code is ready for later controlled testing, not authorization to enable it now. Work is uncommitted; no push or deployment occurred.

### Booking gateway increment

The Realtime session now exposes one additional, non-mutating `prepare_booking_offer` function. On a successful offer it creates the durable proposal, keeps the signed token only in server memory, and sends backend-owned controlled readback audio. The Realtime function output contains the public offer details and `readback_playing`, never the signed token. A matching carrier mark advances the durable readback state. A finalized exact approval that starts after that mark is the only path to the existing atomic booking transaction; unclear/early input and corrections permanently discard the private offer. A committed result then authorizes a concise Realtime success response.

This is code and simulated-event coverage only: **196 passed, 8 live DB tests skipped; Ruff and Mypy clean**. It is not yet an accepted production booking flow: missing-mark/transcript recovery, direct committed-result context details, reconnect/restart reconciliation, cancellation/rescheduling, live DB permissions and carrier semantics remain. Realtime and canary configuration stay disabled in deployment settings; no push or deployment occurred.

### Carrier acknowledgement increment

Controlled-readback mark processing is now a single gateway operation. It ignores every nonmatching mark, verifies the matching ledger segment, persists that evidence through the runtime, and only then enables explicit approval. A caller barge-in clears both carrier playback and the in-memory signed offer immediately, including when no transcription later arrives. Full local validation is now **197 passed, 8 live DB tests skipped**; Ruff, Mypy and `git diff --check` pass. Carrier mark/clear behavior is still awaiting a controlled real VoiceLink call.

### Bounded readback recovery and committed context increment

`VOICE_READBACK_ACK_TIMEOUT_SECONDS` defaults to 30 seconds (bounded 5–120). When the controlled-readback carrier mark does not arrive within that window, the active ledger segment is interrupted and the private offer is discarded; no later caller approval can use it. The timer is cancelled by the matching mark, caller barge-in, replacement readback and gateway cleanup. A confirmed booking result is now inserted into the Realtime conversation as server-provided assistant context before generating the short success reply, carrying a booking reference only when the committed backend result supplies one. Full local validation is **199 passed, 8 live DB tests skipped; Ruff and Mypy clean**.

This completes the safe booking-path implementation currently possible without external services. Phase 3 remains incomplete: cancellation/rescheduling need the same proposal/readback/atomic mutation lifecycle; persisted restart reconciliation and durable expiry/end-of-call handling need integration; and Supabase authorization plus VoiceLink real-call evidence are mandatory. No push, deployment, or runtime flag change occurred.

### Cancellation and rescheduling transaction increment

The existing cancel/reschedule executor paths can now defer their internal commits when invoked by the voice runtime. `VoiceCallRuntime.prepare_operation` and `confirm_operation` provide the same proposal-versioned, caller-bound, tenant-bound atomic transaction boundary used for booking: a server-held canonical argument hash is compared before consent, the backend authorizer accepts only the exact approved tool call, and the appointment mutation plus operation-ledger result share one final commit. Focused tests cover cancellation and rescheduling success, authorization rejection, deferred mutation commits, ledger ordering and replay prevention. Full local validation is **201 passed, 8 live DB tests skipped; Ruff and Mypy clean**.

These mutation paths are deliberately **not yet exposed as Realtime functions**. Their read-only proposal lookup, deterministic readback wording, private pending arguments, carrier-mark lifecycle and gateway result handling must be wired as one unit; exposing the raw executor methods before that would bypass the safety rules. Live Supabase/VoiceLink proof and restart recovery remain Phase 3 acceptance gates.

### Consequential-operation gateway completion

Realtime now exposes `prepare_cancel_appointment` and `prepare_reschedule_appointment`, never the raw mutation functions. Each runs a server-injected read-only preview, persists a canonical-argument proposal, stores the actual arguments only in gateway memory, and uses the same controlled-readback, carrier-mark, timeout, correction and explicit-approval lifecycle as booking. Approval dispatches only to the matching atomic runtime operation. Preview flags, private arguments and raw mutation tools are never added to the model conversation. Cancellation preview/readback integration and cancellation/reschedule atomic-runtime regressions are covered locally. Full local validation: **202 passed, 8 live DB tests skipped; Ruff and Mypy clean; `git diff --check` passed**.

The remaining Phase 3 work is no longer ordinary code-path wiring: verify real Supabase authorization/transactions and VoiceLink clear/mark semantics, test controlled canary calls (booking, cancellation, rescheduling, interruption, correction, missing mark, disconnect), and integrate restart-time reconciliation/end-of-call state ownership. Until that evidence exists, Realtime stays disabled and the demo is not declared ready.

### Live database acceptance attempt — 13 September 2026

The opt-in Supabase suite was run with `RUN_G2_INTEGRATION_TESTS=1`. The sandbox initially blocked the TCP connection; an approved unrestricted retry reached the configured database. The expiry and failed-reschedule cases pass when run separately, including the assertion that a failed reschedule preserves the original confirmed appointment. Runs containing several cases still stop returning after two or three completed markers and leave worker processes until the runner ends; no application failure or failed assertion was reported. This is a live-test harness or connection-lifecycle issue to diagnose with per-test bounded execution, not evidence to change booking logic. No credentials were printed. This is not a passing full live-database acceptance result. The local suite still passes; the Phase 3 live carrier call remains unrun because the canary is not deployed or enabled.

### Phase 4 demo-dialogue increment — 13 September 2026

The Realtime prompt is now created at call start from trusted server-side clinic context. It queries the configured active organization for its name and timezone, and supplies the current clinic-local date/time when the timezone is valid; an optional deployment fallback (`VOICE_CLINIC_NAME`) is used only if that lookup is unavailable. `VOICE_PRONUNCIATION_GUIDANCE` is normalized and limited before inclusion. The former hardcoded clinic name is removed from the Realtime path.

The policy now explicitly covers language matching, an introduction only once, answer-first turns, one-detail-at-a-time collection, correction continuity, at most two availability choices, and one contextual acknowledgement only while a real tool lookup is in progress. It asks for calm, steady pace and restrained intonation, and prohibits repeated fillers, sing-song delivery, invented facts and premature mutation claims. Backend proposal/readback/confirmation checks remain authoritative.

The Realtime call now preloads the authenticated caller's saved name and linked patient profiles before configuring the model. Every booking must resolve and confirm the intended patient: SELF for the caller, the matching saved MOTHER/FATHER/SPOUSE/CHILD profile when unique, or OTHER for relationships outside those categories. Ambiguous saved profiles require a choice; a missing profile requires the patient's name and explicit booking intent before profile creation. The authenticated carrier number is removed from the model-facing booking schema and injected by the server, so the model cannot ask for, guess or substitute another phone number. This follows the official Realtime guidance to reuse current context and collect one unresolved entity at a time.

Local validation after this increment: the full local suite passes with 8 opt-in live database checks skipped; focused Realtime-policy, gateway, runtime and readback checks plus Ruff pass. This is prompt and configuration coverage, not acoustic acceptance. Remaining demo work is real canary listening/tuning for Hindi, Hinglish and English; update tenant pronunciation guidance; then complete the controlled caller scripts for greeting, lookup, booking, correction, cancellation, reschedule and interruption.

## New-thread handoff — 13 September 2026

Read this handoff and the current checkpoint first. Older progress counts and completion claims below are historical; they do not override the unresolved gates here.

### User objective and constraints

- Fix the actual telephone experience: inconsistent/overcorrected speed, exaggerated pitch changes, repeated "Geeta Medicine" introductions, missed instructions and corrections, and inappropriate fillers. The target is a reliable Hindi/Hinglish/English appointment demo with natural conversation and truthful business outcomes.
- The selected architecture is VoiceLink → FastAPI server WebSocket bridge → OpenAI Realtime, with backend-owned business guards and Supabase/PostgreSQL persistence. Continue implementation rather than reopening architecture without evidence. Do not add a second conversational model to the Realtime path.
- The user has repeatedly authorized proceeding and wants substantial remaining work completed in a continuous pass, with concise updates. They have low remaining usage: inspect the existing implementation, avoid repeating research or tests unnecessarily, and do not require a new "next" message for every small change.
- **Do not push, deploy, or enable Realtime production calls.** GitHub pushes may trigger Azure deployment. Keep the chained default and all existing environment secrets private. Previous authorization covered existing credentials for bounded integration checks; it does not establish live carrier acceptance or authorize calling arbitrary people.
- The user reports applying `supabase/migrations/20260912000100_voice_call_sessions.sql`. Do not blindly rerun migrations. Verify the schema/permissions before relying on them.

### Workspace and saved state

- Workspace: `E:\Projects\Ai_receptionist`. Use this same checkout in the new thread so uncommitted work is available.
- HEAD at handoff: `84837e1 feat: add guarded realtime voice foundation`.
- Corrective work after that commit is **uncommitted**, including modifications to tools, booking controller, runtime, readback ledger/player, session/store, Realtime gateway and associated tests. New untracked files are `backend/app/voice/caller_items.py`, `backend/tests/test_caller_items.py`, and `backend/tests/test_voice_atomic_booking.py`. Preserve them; start with `git status --short` and review the diff. The plan itself is modified too.
- Reference documents: this plan, `docs/PROJECT_AUDIT_2026-09-12.md`, and `ANTIGRAVITY_IMPLEMENTATION_SUMMARY.md`. The Antigravity production-ready claims are historical and were corrected by the audit. Legacy pacing guidance was revised from 0.85 to 0.95 after the caller reported slow speech. That TTS setting does not configure native Realtime audio.
- Prior account preflight opened audio-only sessions for `gpt-realtime-2.1` and `gpt-realtime`, accepting PCM24k, semantic VAD and `marin`. The configured plan keeps `gpt-realtime-2.1`; this is session/configuration evidence, not an acoustic evaluation. Check current official documentation when modifying API schema, using the OpenAI docs skill.

### Code map and important integration gaps

| File | Existing behavior / next engineer must know |
| --- | --- |
| `backend/app/voice/voicelink_realtime_gateway.py` | Independent reader and paced playback worker; bounded queues; epoch-based stale output handling; read-only tool tasks; clear/cancel/truncate; controlled readback helper. Only `get_clinic_information` and `search_availability` are exposed. Finalized caller items currently call `capture_turn` with default proposal invalidation and only log approval candidacy. There is no live booking dispatch. |
| `backend/app/voice/caller_items.py` | Correlates speech start/stop/final transcript by item ID, deduplicates and drains in onset order; capacity 256. Onset currently uses local UTC when the provider speech-start event arrives, not a proven audio-offset mapping. Missing/failed transcription recovery and timeout remain unfinished. |
| `backend/app/voice/call_runtime.py` | Owns one DB session, transition lock, ownership fence and rollback snapshots. `prepare_booking`, `acknowledge_readback`, and `confirm_booking` exist. Confirmation checks token hash, proposal, tenant/actor and captured turn; approval, appointment and operation outcome share one transaction. `_uncertain` prevents further dispatch after uncertain commits but does not reconcile them. |
| `backend/app/agent/tools.py` | Signed read-only `prepare_booking_offer` and existing mutation implementations. New `commit_mutations=False` defers booking confirmation's commit for runtime ownership; default preserves legacy behavior. Cancellation/rescheduling still have their own commits and need equivalent transactional proposal/consent integration. Inspect all side effects before sharing transaction ownership. |
| `backend/app/voice/booking_controller.py` | Earlier standalone controller, not live gateway wiring. It requires an existing caller turn and consumes the pending token before dispatch, but service approval, callback mutation and result recording are not automatically atomic. Do not connect it as-is and assume the runtime's guarantees apply. Consolidate ownership instead of adding a third competing controller. |
| `backend/app/voice/session.py`, `session_store.py`, `backend/app/agent/operation_service.py` | Versioned proposals/turns and durable operation lifecycle. Consent rejects input captured at/before readback completion. Store saves fence tenant, owner, active status, expiry and version. Service methods do not commit; the runtime must own transactions. |
| `backend/app/voice/readback.py`, `readback_player.py` | Carrier evidence ledger; register before synthesis; paced readback with per-packet interruption checks. Audio generated/sent is not completion evidence. No live proof of carrier clear/mark semantics yet. |
| `backend/app/voice/proposals.py`, `readback_text.py`, `approval.py` | Offer hash and deterministic wording; conservative explicit approval classifier. Review required detail validation, language/payment wording, numeric fee handling and natural short confirmations before integration. Do not weaken consent to compensate for dialogue issues. |
| `backend/app/api/routes/voice.py`, `backend/app/core/config.py` | Engine chosen once per call via `VOICE_ENGINE=chained|realtime`; internal-caller canary routing is not implemented. |

Additional transport risks to resolve: coordinate response creation with response completion and interruptions; synchronize only acknowledged controlled-readback text into model context; recover from missing marks with bounded waits; prevent stale model generations that arrive late from speaking. Current interrupted model truncation uses zero milliseconds because sent bytes are not evidence of heard audio. Do not replace that conservative boundary with elapsed-time guesses. Review call termination/expiry and state reconciliation; cleanup of sockets alone is not a durable end-of-call lifecycle.

### Next work, in dependency order

1. Finish the transaction/reconciliation boundary: query durable committed outcomes after uncertainty, bind reconciliation to tenant/caller/session/operation/version, and prevent duplicate mutations. Validate real database authorization and transaction behavior; mocks alone are insufficient.
2. Complete one server-owned booking lifecycle through the actual gateway: read-only offer → private pending token/version → controlled readback → valid carrier acknowledgement → correlated finalized explicit approval captured after delivery → atomic mutation → truthful committed result. Corrections and early speech must invalidate it; never manufacture a later consent timestamp. Keep tokens out of model output and logs.
3. Add cancellation/rescheduling equivalents using authorized records and version checks. Do not expose mutation tools before their guards and transaction ownership are complete.
4. Complete controlled-readback response suppression/context synchronization, transcript/mark timeout recovery, late-generation rejection, durable disconnect handling and internal-caller canaries. Add focused socket-level regressions for actual integrated behavior, including failure paths.
5. Run controlled database/carrier checks, then telephone scripts for pauses, interruptions, short approvals, corrections, duplicate/stale marks, delayed transcripts/tools and disconnects. Record specific evidence or the exact external blocker. Do not mark Phase 3 complete from unit-test counts.
6. Proceed to Phase 4 voice/dialogue tuning and listening acceptance, then the remaining evaluation/rollout phases in this document. Do not promise perfectly constant pitch or demo readiness before listening tests.

### Validation and efficient continuation

Last code validation: **202 passed, 8 live DB tests skipped**, Ruff clean, Mypy clean, and `git diff --check` passed. The isolated live Supabase expiry and failed-reschedule checks pass; the combined live suite remains an unresolved harness/connection-lifecycle check. One dependency deprecation warning is unrelated.

Run from `E:\Projects\Ai_receptionist\backend` using the root virtual environment (there is no backend-local venv):

```powershell
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check app tests
..\.venv\Scripts\python.exe -m mypy app
git diff --check
```

Use focused tests while changing code, then run the full relevant checks once. Key regressions are in `test_voicelink_realtime_gateway.py`, `test_voice_atomic_booking.py`, `test_voice_call_runtime.py`, `test_caller_items.py`, and the consent/readback/session-store tests. Update this plan with integrated behavior, exact validation, and outstanding external gates. Avoid informal completion percentages and do not label disconnected components a completed phase.

## Integration correction — 13 September 2026

### Current checkpoint

Local validation: **187 passed, 8 live database tests skipped; Ruff clean; Mypy clean across 65 source files; `git diff --check` passed**. These tests use simulated carrier/provider events; they do not establish live audio quality or database acceptance.

The Realtime event reader and carrier playback now run independently. Playback is paced in 20 ms packets, with at most 240,000 PCM bytes (five seconds, including the packet currently being processed) and 128 events pending. A new caller epoch invalidates queued output, and interruption stops remaining packets from the current item. A stale completion event cannot mark another item's audio complete. Playback failure cancels the event reader and propagates to call cleanup. Session handshake waits are bounded; cleanup attempts every provider/database closer even when another closer fails. A synthesis failure releases the controlled-readback state.

The durable runtime now commits proposal preparation and carrier-backed readback acknowledgement through a shared serialized transition boundary. It restores local state on rollback, fences uncertain commits, rejects rebinding to another caller/call, and does not retry an uncertain session creation. A lifecycle regression covers preparation, missing mark rejection, acknowledged readback, late-arriving early speech, and correction invalidation. Booking transaction tests cover mutation and operation-result commit ordering and failures.

**Phase 3 is not complete and Phase 4 acceptance has not started.** Remaining release blockers:

- Connect the live booking proposal/readback/finalized-approval flow to the atomic booking boundary; implement equivalent guarded cancellation/rescheduling paths. Realtime currently exposes only clinic information and availability.
- Complete unknown-commit reconciliation, autonomous-response coordination during controlled readbacks, delivered-readback context synchronization, bounded recovery for missing marks/transcripts, and internal-caller canary routing.
- Verify database authorization/transaction behavior and VoiceLink clear/mark semantics with controlled integration calls. Run interruption, correction and language/voice listening scripts against the deployed candidate before calling it demo-ready.

Deployment remains paused. Keep `VOICE_ENGINE=chained`; do not enable Realtime appointment calls based on local test counts. No deployment or push was performed for this checkpoint.

### Earlier corrective work

Atomic booking boundary added: `VoiceCallRuntime.confirm_booking` checks the signed offer against the proposal version and runtime tenant, then applies consent, appointment mutation and operation outcome through the same database session and final commit. The existing booking tool accepts a server-owned option to defer its internal commit for this path; legacy calls retain their original behavior. Pre-commit failures roll back. An uncertain commit blocks further dispatch in that runtime until reconciliation. Expired call rows no longer pass state-transition fencing. Tests cover success, booking rejection, operation-ledger failure, uncertain commit and duplicate dispatch. This internal boundary is not yet connected to Realtime appointment tools and does not complete Phase 3.

Transport hardening pass: caller transcripts are now correlated by item ID and drained in speech order with original onset timestamps. Duplicate transcript delivery is ignored and unknown/over-capacity items fail closed. Controlled readback registers its mark before synthesis, checks interruption before each paced packet, and invalidates on cancellation. Late audio from interrupted model items is discarded. Truncation uses zero as the conservative unacknowledged playback boundary rather than pretending all sent audio was heard. Lookups execute outside the event reader with bounded concurrent work; superseded results do not request spoken follow-ups. Output-reader failure now wakes the carrier loop.

Full local validation after this pass: **177 passed, 8 live database tests skipped**, Ruff clean and Mypy clean across 65 source files. This is transport and component evidence, not Phase 3 acceptance. Booking/cancellation/rescheduling are still not connected end to end; persisted mutation transactions, reconciliation, controlled readback context synchronization and live carrier proof remain outstanding. Realtime must remain disabled for production appointment calls.

The earlier percentage estimates were informal and are not release evidence. Phase 3 remains incomplete and Realtime appointment writes remain disabled. Review found that approval manufactured a new caller turn at processing time, and runtime caller-turn updates were not committed. Approval now requires an existing captured turn and rejects timestamps at or before readback completion. Booking dispatch consumes the in-memory pending offer before calling the mutation, preventing replay after an uncertain result. Runtime caller-turn capture now commits and restores local state after rollback on failure.

Validation for this correction: 12 focused consent/controller/runtime tests passed. Still required: correlate speech-onset timestamps and finalized transcripts by Realtime item ID, preserve valid consent across that lifecycle, complete transaction ownership and unknown-commit reconciliation, fix controlled-playback races, and wire booking/cancellation/rescheduling end to end. A controlled carrier call and listening tests remain mandatory before demo readiness.

Final decision: 12 September 2026
Status: architecture selected; implementation and live acceptance pending.

## Decision — follow this document

Build the new telephone assistant using **OpenAI Realtime API over a server-side WebSocket bridge**, with **VoiceLink for calls, FastAPI for application control, and Supabase/PostgreSQL for business data and durable call state**.

This is the single execution roadmap. It supersedes earlier phase numbering and architecture alternatives in the audit, Antigravity summary and earlier versions of this plan. Execute Phases 1–6 in numerical order and record evidence here.

The owner authorizes existing backend API credentials for implementation and bounded integration tests. Load them server-side without printing or exposing them. Verify account access in Phase 1; possession of a key does not prove model availability.

Realtime is our chosen direction for continuous audio, interruption and speech in one conversational session. The chained engine remains a temporary baseline and rollback path. GPT-Live, LiveKit, Redis and a carrier replacement are outside this implementation. Reopen architecture only for a demonstrated blocker with evidence and a proposed resolution.

## Architecture and ownership

```text
Caller <-> VoiceLink <-> FastAPI media adapter <-> OpenAI Realtime
                              |                         |
                              +-> per-call controller <-+
                                         |
                              guarded business services
                                         |
                              Supabase / PostgreSQL
                              state, operations, appointments
```

| Component | Responsibility |
| --- | --- |
| VoiceLink adapter | Authenticate and bind caller, receive/send audio, clear playback, correlate marks and disconnects |
| OpenAI Realtime | Interpret audio, conduct conversation, propose tool calls and stream speech |
| Per-call controller | Order events, own turn/generation/playback IDs, coordinate interruptions and results |
| Business services | Enforce authorization, current state, consent, validated arguments and permitted transitions |
| PostgreSQL | Persist state versions, operation/idempotency records and committed appointments |
| Dashboard | Show actual committed outcomes through existing APIs |

The Realtime path will not route every utterance through ReceptionAgent/LangGraph. Extract business guards from the graph before exposing tools to Realtime. Tool descriptions help the model; backend code enforces the rules.

Realtime semantic VAD initially owns end-of-turn detection. Local speech onset may stop playback promptly but must not independently commit caller turns. Input, generation, playback and database operations have independent state because they overlap.

## Mandatory correctness rules

1. Assign call, caller-item, generation, playback-segment, operation and state-version IDs. Bind tenant/caller identity server-side; model arguments cannot replace it.
2. Preserve input order with bounded audio bytes, queue length and age. Corrections invalidate prior uncommitted intent. Never silently drop input or execute an old queued confirmation because it is processed later. Overload has a defined recovery/close path.
3. Tool calls are proposals. Correlate asynchronous transcription by caller-item ID rather than arrival order. Mutations wait for finalized caller input and validated explicit consent; unclear confirmation requires clarification. No speculative tool execution initially.
4. Booking, cancellation and rescheduling require a versioned proposal, controlled readback, verified playback completion and explicit approval captured after completion. Corrections invalidate the proposal. These checks apply to every engine.
5. The backend supplies critical readback wording. Initially use an isolated server-generated TTS segment for exact wording, suspend autonomous Realtime output during it, track it in the same playback ledger, and synchronize delivered text into context. Its voice transition must pass listening tests. Replacing it with native Realtime speech later requires evidence of equivalent content and delivery control.
6. Accept a playback mark only for its matching, non-cleared segment under verified carrier semantics. A timer estimates delivery; it cannot authorize consent. Missing, cleared, duplicate and stale marks trigger safe bounded recovery.
7. On interruption, clear carrier output, cancel obsolete model output and truncate the appropriate Realtime audio item using conservative playback evidence. Never fabricate exact words heard from elapsed time or character count. Keep generated, sent, acknowledged and interrupted content distinct.
8. Cancellation is not transaction rollback. Validate authorization, proposal version and durable idempotency inside the mutation transaction where possible. Record committed outcomes and reconcile unknown commits before retrying. Concurrent tasks must not share database sessions.
9. Use PostgreSQL version checks and per-call ownership fencing. Persist business transitions rather than every audio frame. Persistence cannot restore a broken carrier connection; deployments drain active calls.
10. Speak success only after the actual committed outcome. Preserve caller binding and pay-at-clinic scope. Do not promise transfers or payments that are not implemented and verified.

## Phase 1 — connection proof, baseline and event contracts

Deliverables:

- Open an isolated Realtime session using existing credentials and synthetic audio, with no appointment writes. Prove inbound/outbound audio, interruption events and cleanup.
- Resolve and record one available production model ID, API/SDK version, voice, codec formats, session limits and account rate limits. Pin versions where supported; do not guess names from older notes.
- Verify VoiceLink packet timing, tracks, output pacing, clear/mark behaviour including marks after clear, hangup and reconnect through documentation and a sanitized protocol fixture. Block write-enabled calling if playback delivery cannot be established.
- Define common event records with monotonic timestamps and all IDs above. Instrument queue, STT, reasoning, first audio, playback and errors on the current path without expanding raw PII logging.
- Start synthetic fixtures now: Hindi/Hinglish/English, dates, names, corrections, early confirmations, interrupted readbacks and provider failure. Record the baseline before tuning.
- Finish the interim queue change with bounded backlog and stale-action protection. Avoid extensive new development of the old voice engine.

Main files: `backend/app/voice/voicelink_gateway.py`, new `backend/app/voice/events.py`, `backend/app/core/config.py`, new `scripts/realtime_preflight.py`, protocol/audio fixtures.

Gate: reproducible audio-only Realtime test, verified carrier playback semantics, recorded configuration and baseline event traces. Offline preparation may proceed around external blockers, but dependent live gates remain pending.

## Phase 2 — durable state and guarded business operations

Deliverables:

- Create typed state for caller, language, intent, patient, relationship, doctor, date, selected session, current question, proposal/version, playback evidence, consent, generation and operation status.
- Persist state in PostgreSQL with expiry, optimistic version checks and ownership fencing using backward-compatible migrations.
- Extract graph-only authorization, correction, readback and consent guards into shared services. Reuse existing signed offers and appointment functions after validating their boundaries.
- Add durable idempotency and uncertain-commit recovery to booking, cancellation and rescheduling. Inspect actual side effects before classifying tools as read-only; names such as lookup or prepare are insufficient.
- Reject stale generations/proposals and early-captured approvals. Use short transactions and separate database sessions per concurrent task.

Main files: new `backend/app/voice/session.py`, new `backend/app/agent/session_state.py`, new `backend/app/agent/operation_service.py`, `backend/app/agent/graph.py`, `backend/app/agent/tools.py`, `backend/app/agent/dialogue.py`, Supabase migrations.

Gate: tests prove tenant/caller isolation, valid consent, correction invalidation, duplicate-operation protection, competing-owner rejection and commit reconciliation. No Realtime write tools before this gate.

## Phase 3 — Realtime bridge and interruption

Deliverables:

- Build independent receive/send tasks coordinated by one per-call event owner, bounded queues, output pacing and deterministic cleanup.
- Forward audio continuously. Prefer native A-law passthrough when both selected endpoints support it; use tested stateful resampling only at a real format boundary. Add jitter buffering only for measured timing needs.
- Configure semantic VAD and supported noise reduction against fixtures. Noise reduction is not assumed to provide acoustic echo cancellation.
- Implement clear/cancel/truncate, stale-result rejection, false-interruption recovery and playback evidence. Implement the controlled readback path from correctness rule 5.
- Connect Realtime tools directly to Phase 2 services. Correlate caller items and tool results; serialize writes. Do not add a second conversational LLM.
- Add `VOICE_ENGINE=chained|realtime` when both adapters exist. Default to chained during development, select once per call, and support internal-caller canaries. Reject unsupported settings.

Main files: new `backend/app/integrations/openai_realtime.py`, new `backend/app/voice/realtime_gateway.py`, `backend/app/voice/session.py`, `backend/app/api/routes/voice.py`, `backend/app/core/config.py`, `backend/app/voice/codec.py`.

Gate: socket and controlled phone tests pass pauses, short approvals, rapid corrections, false interruptions, stale marks, late tool results and disconnects. Interrupted/unacknowledged readbacks never authorize writes.

## Phase 4 — natural dialogue, language and voice

Deliverables:

- Write a concise Realtime prompt: role, language matching, restrained delivery, short answers, clarification, current question and truthful tool outcomes. Business enforcement remains executable backend policy.
- Introduce once, answer the current question first, preserve known details and accept corrections without restarting booking.
- Inject verified tenant facts and pronunciation guidance. Remove hardcoded doctor names. Treat caller-provided content as data, never authority to bypass tool guards.
- Use a stable voice per session and only supported Realtime pace controls. Existing `OPENAI_TTS_SPEED` does not automatically configure Realtime.
- Replace automatic cached personalized fillers on the Realtime path with brief contextual acknowledgements only when a real lookup warrants them. Fillers cannot delay useful audio or overlap the caller.
- Compare identical telephone scripts across Hindi, Hinglish and English, including the controlled readback voice transition. Tune restrained intonation and pace; generative speech does not guarantee perfectly constant pitch.

Main files: new `backend/app/voice/realtime_policy.py`, `backend/app/agent/policy.py`, `backend/app/integrations/openai_audio.py`, tenant configuration and audio fixtures.

Gate: no repeated introductions in the suite, correct handling of questions/corrections, and human approval of pace, voice continuity and names/numbers.

## Phase 5 — evaluation and production preparation

Deliverables:

- Expand to at least 60 scenarios and 30 synthetic/approved audio fixtures. Repeat probabilistic cases at least three times. Include ambiguous names, language switches, noise, early yes, interrupted readbacks, corrections during tools and hangup.
- Measure business outcomes separately from naturalness. Compare with the original baseline using identical scenarios; publish per-language failures and results.
- Test provider timeout/rate limits, database failure, unknown commit, disconnect, restart, competing owners and deployment draining.
- Add concurrency/admission limits, safe bounded retries, spend telemetry and resource cleanup. Separate liveness from upstream health to avoid restart loops.
- Define redaction and retention for any enabled live recording. Use synthetic or explicitly approved evaluation audio.
- Record Azure configuration, measured supported concurrency, cost per minute and cost per successful call. Verify the actual deployment workflow/revision instead of assuming a push deployed successfully.

Gate: the release criteria below pass in the intended environment, with recovery procedures and known limits recorded. Mock/offline tests alone do not establish readiness.

## Phase 6 — controlled Azure rollout

Deliverables:

- Deploy with chained still serving new calls; enable Realtime for internal caller numbers.
- Complete at least ten live rehearsal calls across supported languages and operations. Check spoken outcomes against dashboard records.
- Expand new-call traffic in stages while monitoring completion, interruptions, latency, errors and spend. Promote Realtime to default only after acceptance.
- Drain existing calls on their selected engine/revision. Roll back new calls to the validated chained path if acceptance regresses; keep migrations compatible. Do not silently switch engines during an active call.

Gate: deployed revision/config verified, rehearsals and staged traffic accepted, rollback exercised and limitations documented.

## Release acceptance

These are project targets, not provider guarantees or universal industry certification.

| Area | Required evidence |
| --- | --- |
| Business correctness | Zero unauthorized, stale-consent or duplicate mutations in mandatory scenarios; spoken success matches committed state |
| Completion | At least 90% across repeated supported scenarios; report each language and every failure |
| Critical details | Correct patient, doctor, date/session and operation in every accepted mutation; uncertainty triggers clarification |
| Latency | No-lookup turns: target median <=1.5 s and p95 <=3 s from actual caller end to first useful audible response; report endpoint and carrier delay separately |
| Interruption | At least 95% stop audible output within 500 ms of confirmed speech onset; also report detection delay from actual onset |
| False interruption | Below 5% on counted noise/non-interruption trials; publish numerator and denominator |
| Voice quality | Human acceptance of Hindi/Hinglish/English pacing, pronunciation and pitch variation, including readback transitions |
| Recovery | Mandatory failure/restart/commit-uncertainty cases reconcile without duplicate actions |
| Operations | Correlated traces, active config/revision, measured cost/concurrency and exercised rollback |

Performance percentages cannot waive mandatory correctness cases. Playback delivery is not proof of human comprehension; explicit approval remains required.

## Progress and execution policy

| Item | Status |
| --- | --- |
| Final architecture and sequential roadmap | Complete — this revision |
| Realtime account/session preflight | Complete — `gpt-realtime-2.1` and the current `gpt-realtime` alias both opened audio-only sessions and accepted PCM 24 kHz, semantic VAD and `marin`; no caller audio or tools were sent. Keep `gpt-realtime-2.1` pinned for this rollout until evaluation proves a replacement. |
| Phase 1 event contracts | Complete locally — correlated call/turn lifecycle event types, identified bounded turns, stale-turn recovery and Realtime preflight script added |
| VoiceLink carrier proof | Partial — Azure trace confirms the authenticated media WebSocket opens and a Realtime canary call is selected. A 2026-09-13 controlled call exposed a five-second no-audio timeout because startup did not request the first Realtime response. Clear/mark/reconnect evidence still remains. |
| Synthetic audio fixtures and baseline measurements | Pending |
| Backend checks after Phase 3/4 local increments | Full backend suite passed on 2026-09-13 with 8 opt-in live DB tests skipped; all 22 focused Realtime gateway tests and Ruff pass after the startup-audio fix. |
| Phase 1 gate | In progress — account proof is complete; carrier proof and baseline evidence remain |
| Phase 2 deterministic consent guard | Complete locally — versioned proposals require completed readback and a later approval; corrections invalidate prior proposals |
| Phase 2 PostgreSQL store and migration | Complete locally — optimistic state version/ownership checks, operation ledger, and state restore path added; owner reports migration applied to Supabase |
| Phase 2 operation lifecycle | Complete locally — proposal/readback/approval/commit transitions persist to the voice operation ledger; executor has a server-side authorization hook for booking, cancellation and rescheduling |
| Legacy-engine adoption of the new operation lifecycle | Deferred by design — its current playback tracking cannot prove the required completed readback; Phase 3 Realtime bridge is the first guarded caller |
| Phase 3 Realtime transport | Implementation complete locally — feature-flagged VoiceLink-to-Realtime bridge has continuous A-law/PCM conversion, semantic VAD, streamed audio, carrier marks, clear/cancel/truncate, finalized transcription, deterministic cleanup, durable owner fencing, read-only tools and guarded booking/cancellation/reschedule wiring. Startup now explicitly requests the one-time greeting after `session.updated`; deployment and a controlled live call must verify audible output and carrier behaviour. |
| Phase 4 natural dialogue policy | Implementation complete locally — the structured prompt covers Hindi/Hinglish/English, a single introduction, current-question-first flow, corrections, family/self/other patient selection, contextual acknowledgements, restrained pace/pitch, tenant clinic facts, clinic-local time and pronunciation guidance. Human listening acceptance remains pending. |
| Phases 5–6 | Pending |
| Realtime enabled in production | Canary configuration is active; production acceptance is pending redeployment of the startup-audio fix and controlled calls. |

Record changed files, test commands/results, deployed evidence and unresolved gates after each phase. Continue authorized work without repeated architecture approvals. Do not mark partial evidence as complete. If an external limitation blocks the design, record the exact failure and smallest necessary amendment before changing architecture. Choosing supported model/voice settings within Realtime is routine implementation.

## Official references and remaining verification

- [OpenAI voice architectures](https://developers.openai.com/api/docs/guides/voice-agents): Realtime combines speech, reasoning and tools; chained and GPT-Live are distinct designs.
- [Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations): WebSocket clients manage playback clearing and truncation; exact word-aligned heard text is not supplied by truncation.
- [Realtime VAD](https://developers.openai.com/api/docs/guides/realtime-vad): verify supported semantic VAD settings against the selected session schema in Phase 1.

Unverified at planning time: account-specific model access/rates, VoiceLink clear/mark/reconnect semantics, exact codec compatibility, current Azure deployment and live acoustic quality. Phase 1 resolves integration assumptions; subsequent gates establish readiness.
