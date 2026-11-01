# Personal AI database isolation

Reviewed 27 September 2026 against the owner's supplied schema context.

The supplied snapshot declares 30 existing public tables covering organizations,
clinic configuration, schedules, contacts/patients, appointment/payment operations,
provider inbox/outbox, voice sessions and voice observability. It contains no
`personal_agent_*` tables. Some exported type and composite-FK declarations are
contextual, not runnable SQL; do not execute the pasted snapshot to recreate data.

## Separate tables

| New table | Responsibility |
| --- | --- |
| `personal_agent_profiles` | Personal owner, registered phone, timezone/language, saved inbound mode and demo generation |
| `personal_agent_tasks` | Personal tasks, due times, completion and soft deletion |
| `personal_agent_followups` | Durable reminders and unresolved events, context snapshots, next action, lease and resolution |
| `personal_agent_calls` | Personal inbound/outbound sessions, fixed agent mode and linked event |
| `personal_agent_attempts` | Individual callback attempts and provider call status |
| `personal_agent_messages` | WhatsApp attempts, content snapshot and provider delivery evidence |
| `personal_agent_memory` | Expiring recent conversation context, separate from unresolved event memory |
| `personal_agent_events` | Owner-scoped dashboard activity with exact call/event links |
| `personal_agent_tool_results` | Persisted tool request/results for duplicate prevention |

All new tables are in `public` with the `personal_agent_` prefix. This works with
the existing SQL connection and migration convention without changing Supabase
schema exposure, shared search paths or the deployment topology. A separate SQL
schema is possible, but unnecessary for this demo's isolation requirements.

The only reference outside the module is:

```text
auth.users(id) -> personal_agent_profiles(owner_id)
```

This references the existing login identity; it does not alter `auth.users` or
create another authentication system. Personal entities reference other personal
entities through owner-scoped keys. The new tool-result foreign key also checks
that the call and owner belong together.

## Existing database boundary

The new migration contains no alteration, update, delete, insert, trigger or
policy change against any of the 30 existing tables. Its only `ALTER TABLE`
operations affect newly created personal tables. There are no cascades from
personal records into clinic data. Existing voice, observability, inbox/outbox
and appointment tables are not reused for personal business state.

Personal access is governed by `owner_id`, independently of clinic organization
membership. New tables enable RLS and provide authenticated owner-only SELECT
policies. Browser roles receive no write access; writes go through the personal
backend, which must enforce the configured demo owner and validated call binding.
The backend's elevated SQL connection still requires explicit owner predicates:
RLS alone is not a replacement for server authorization.

No global role grants, default privileges, `search_path` or existing RLS helpers
are changed. New identity sequence privileges are not granted to browser roles.

## Migration and verification

- Migration: `supabase/migrations/20260927000500_personal_agent_foundation.sql`.
- Checks: `supabase/verification/20260927000500_personal_agent_checks.sql`.
- The migration uses a new version, avoiding the repository's historical duplicate.
- It runs inside BEGIN/COMMIT and creates no synthetic personal or clinic records.
- It is intentionally a one-time migration; an existing object collision should
  fail instead of silently accepting an incompatible earlier schema.
- Verification lists the nine tables, RLS/policies, indexes, external foreign-key
  targets and effective browser grants.
- Runtime rollback is to disable Personal AI routing/worker and retain its tables.
  Routine rollback/reset must not drop clinic tables or delete clinic records.

## Current evidence and limits

- [x] All 30 existing table names inventoried from the supplied snapshot.
- [x] Nine proposed names checked: zero collisions.
- [x] New migration reviewed for clinic-table dependencies and mutation targets.
- [x] Personal tool-result ownership strengthened with a composite foreign key.
- [x] RLS/grant/FK verification queries prepared.
- [x] Owner-supplied output confirms all nine table names and effective grants:
  `anon_read=false`, `client_write=false` for every table.
- [x] Owner-supplied output confirms RLS enabled and owner read policy present on all nine tables.
- [x] Owner reports unexpected external-FK query returned zero rows.
- [ ] Run verification and real owner-isolation/transaction checks.

The owner supplied grant
and RLS/policy outputs and reported zero unexpected external foreign-key targets.
These checks establish the schema configuration checkpoint, not actual cross-user
access behavior, complete policy expressions or migration ledger contents.
The subsequent owner setup wrote only personal profile/activity data and verified
the committed profile in a fresh transaction. Authenticated readiness/snapshot
reads also succeeded through the local dashboard. Cross-user RLS checks and other
live operation transactions remain pending; no existing schema was modified.
