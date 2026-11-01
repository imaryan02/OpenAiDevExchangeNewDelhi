# Changes cross-check — 26 September 2026

Compared the working diff with every step of the remediation plan and findings F01–F18.
This review found implementation gaps after the initial passing test run. They were
corrected locally; the initial statement that everything was complete was too broad.

## Corrections found during this cross-check

- **Consent dispatch:** LangChain's model-facing argument schema discarded the private
  preview flag. Cancellation/rescheduling now use the server executor directly for
  previews and approved execution. The graph emits a deterministic preview, requires
  approval in a later caller turn, and executes the original server-held arguments.
  Tests cover both operations, initial approval, later refusal, argument drift and
  fail-closed behavior when no server executor is supplied.
- **Active browser sessions:** restoration refreshed tokens, but ongoing polling and
  actions retained an expired token. Authenticated API requests now refresh on 401,
  serialize simultaneous refreshes, preserve request bodies, and retry once. Live
  observer discovery and stream reconnections use the same path. Mocked browser
  tests cover concurrent refresh, stale sessions, restoration and non-auth errors.
- **Notification durability:** provider sends previously shared the maintenance
  transaction and an uncommitted batch lease. Dispatch now runs in a separate session,
  commits each claim before sending, and commits each success or failure independently.
  Each job is leased immediately before sending. Mocked tests verify transaction
  order, provider failure and configuration gating. Delivery remains at least once:
  a crash after provider acceptance but before database completion can cause a retry.
- **Dashboard:** completed visits remain in today's totals but are excluded from
  upcoming/remaining confirmed visits. Appointment pagination uses an ID tie-breaker
  when creation timestamps match.
- **Reschedule readback:** destination previews include date/time and location;
  destination assignments and locations must be active in the tool lookup.
- **Migration history:** the historical duplicate filename is restored. No ledger
  evidence was obtained to justify renaming an applied version. Automated migration
  push remains pending ledger reconciliation.

## Plan coverage

| Plan step | Source cross-check | Verification limits |
| --- | --- | --- |
| Consent and voice (F01, F03) | Server-held text preview/approval; Chained appointment writes disabled; Realtime sends result to conversation | Real carrier playback/provider calls not exercised |
| Currency (F02) | Fee entry converts rupees to paise; edit and display convert back | Existing database fee values have not been reconciled |
| Appointment integrity (F04, F05) | Reschedule triggers check cutoff/active destination/currency, refresh quote and link payment visibility | User verified object existence; live transaction behavior remains unverified |
| Readiness and schedules (F06, F07) | SQL readiness required; maintenance generates rolling 21-day sessions hourly | Live DB connection, background execution and contention not exercised |
| Frontend operations (F08–F11) | Refresh, selection/search refs, paginated load, correct status metrics | Auth has behavioral tests; no complete browser booking-flow test |
| Privacy/lifecycle/source (F12, F13, F15) | Content logs removed; AI_VOICE attribution; expiry renewal, active call loading, closure and stale-session expiry | Full carrier reconnect/closure lifecycle not exercised |
| Outbox (F14) | Configuration and recipient consent checks; durable claims/results | Real WhatsApp acceptance/delivery not exercised |
| Patient archival (F16) | UI archives; hard deletion requires organization admin | Live role-based deletion acceptance not exercised |
| Deployment (F17) | Deployment depends on quality job | Workflow not pushed/run; actual Azure replica topology not inspected |
| Migration collision (F18) | Original history retained; read-only ledger query prepared | Pending actual ledger evidence |

## Local validation

- Backend Ruff and mypy pass (69 application files checked by mypy).
- Backend: 269 passing tests, 8 database integration tests skipped.
- Frontend: 14 tests pass, including 3 new authentication tests.
- Frontend typecheck and production build pass.
- Git diff has no whitespace errors.

No deployment, outbound messages/calls, or remote database mutation was performed
during this cross-check. No claim of full production acceptance is made.

## Remaining acceptance evidence

1. Run `supabase/verification/20260926000300_reschedule_dependency_checks.sql`.
   If the public reschedule function still references `private` while that schema
   is absent, object existence does not mean the function can execute successfully.
2. Run the statements in `supabase/verification/20260926000200_migration_ledger_checks.sql`
   as directed, checking ledger availability before the ledger SELECT. Resolve the
   duplicate migration version using those results.
3. The eight existing integration cases and seven dedicated reschedule checks have
   now passed against configured Supabase with owner authorization (see below).
4. Validate carrier lifecycle with a designated test call, then deploy the reviewed
   changes and check readiness. WhatsApp testing is deferred at the owner's request.

### Owner-supplied database evidence

The dependency output confirms `private` now exists, and both reschedule trigger
functions match the intended definitions. The follow-up output confirms that
`private.is_org_booking_staff(uuid)` and the session-window constraint both exist.
The ledger query returned SQLSTATE 42P01 because
`supabase_migrations.schema_migrations` is absent. There is therefore no CLI ledger
available in this environment to establish applied migration versions. The ledger
check file now uses catalog-only checks and does not select the absent relation.

### Live integration run — 26 September 2026

After the owner explicitly requested execution against configured Supabase, the
connection/Auth-user preflight passed and all eight tests in
`backend/tests/test_g2_database.py` passed in 109.44 seconds. No tests were skipped.
This establishes the tested idempotency, hold expiry, cancellation capacity,
failed-reschedule rollback, verification replay/lockout, tenant/doctor invariants,
stale outbox lease rejection and booking contention behavior on that database.
Seven tests rolled back their test transactions; the concurrency test completed
its tenant-scoped cleanup. Notification consent defaults to false in test fixtures.
One non-blocking local pytest-cache permissions warning was reported.

`backend/scripts/run_db_integration_checks.py` provides the bounded preflight and
test command without printing credentials. These existing eight tests do not
establish complete acceptance of the new successful-reschedule trigger behavior,
carrier lifecycle, or actual provider delivery.

### Additional reschedule acceptance — 26 September 2026

Seven new cases passed against configured Supabase in 80.03 seconds, all using
transactional fixtures that roll back synthetic data:

- Successful reschedule refreshes the doctor/location/time/price quote, records
  reschedule consent metadata, preserves prior consent evidence, copies payment
  visibility, links the replacement and preserves the original quote.
- Past sessions and sessions inside the booking cutoff are rejected.
- Inactive assignments and inactive locations are rejected.
- Fee changes and currency changes are rejected.
- Rejections preserve the original confirmed appointment, create no replacement or
  reschedule notification, and roll back token allocation.

Together with the earlier eight tests, 15 live database integration cases have now
passed. WhatsApp provider testing is explicitly deferred; no WhatsApp messages were
sent by these database checks. Live carrier acceptance and deployment remain pending.

### Voice greeting smoke test — 26 September 2026

The current code was served locally with background maintenance disabled. The
synthetic VoiceLink WebSocket start produced greeting media successfully using
the configured Chained engine and speech provider (`voicelink_greeting_media=ok`).
No telephone was dialed or appointment booked. This checks the gateway startup and
audio output path; it is not a full carrier call or playback/consent acceptance test.
The local backend suite also passed again: 269 passed and 15 live database tests
skipped by default (those 15 passed separately against Supabase as documented above).

Additional limitations in the original review (uncertain non-booking commit recovery,
process-local history/observation, rate limiting, simulated payments and broader
refactoring) remain outside the six-step remediation implementation. They should
not be represented as completed by this patch set.
