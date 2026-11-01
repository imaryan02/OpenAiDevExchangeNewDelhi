# Supabase migration convention

Phase 1 database implementation has begun. The first migration establishes the tenant and authorization foundation; later phases add operational and patient-facing data.

## Owner-run workflow

When migrations begin, each SQL file will be:

1. Added here with a sortable, immutable name: `YYYYMMDDHHMMSS_short_description.sql`.
2. Written for PostgreSQL/Supabase and reviewed with an explicit rollback/recovery note in its header.
3. Sent to the product owner for execution in the intended Supabase project's SQL editor or migration workflow, unless the owner later grants tool access.
4. Followed by the owner supplying the exact non-sensitive result/error output so the next migration can be adapted safely.
5. Applied once per environment, in lexical order. Never paste secrets or production patient data into a migration result.

Two historical files use version `20260911001400`. Their names are preserved until
the target environment's `supabase_migrations.schema_migrations` ledger has been
checked. Do not run an automated migration push with this collision unresolved.
Use `supabase/verification/20260926000200_migration_ledger_checks.sql` to collect
the ledger and session-window constraint evidence before reconciling the names.

## Rules for future migrations

- Use `BEGIN`/`COMMIT` where PostgreSQL/Supabase supports it safely for the contained operations.
- Make additive changes first; do not drop or rewrite user data without a separate approved, recoverable migration plan.
- Enable and test RLS before exposing application data.
- Use tenant-scoped foreign keys/constraints and database invariants for booking capacity; do not rely only on frontend or LLM logic.
- Include a comment with the phase, requirement IDs, dependencies, validation query and safe recovery approach.
- Put synthetic seeds in a separate clearly labelled file; production-like schema migrations must not seed demonstration patients automatically.

## Implemented migration

`20260927000100_voice_observability.sql` adds content-free call summaries and event timelines for authenticated VoiceLink Chained and Realtime calls. It depends on the existing organization tables and `private.is_org_booking_staff(uuid)`. It must be applied by the project owner after resolving the historical migration-ledger collision described above; run `supabase/verification/20260927000100_voice_observability_checks.sql` afterward. The rollback is to disable the new API deployment and retain these additive tables for investigation; do not drop collected history as a routine rollback.

`20260927000200_voice_usage_observability.sql` adds idempotent provider-reported usage rows, scoped to the associated call and organization. It stores usage units, model and request identity only; it does not calculate price. Apply after the call-history migration and run `supabase/verification/20260927000200_voice_usage_observability_checks.sql`. Keep the API/UI deployment behind this migration because call detail reads the new table. Its rollback is to disable the usage read/write path and retain recorded usage evidence.

`20260910000100_phase1_tenant_foundation.sql` introduces only foundation tables and authorization primitives: organizations, locations, departments, doctors, doctor assignments, organization users, role helpers, RLS policies and audit foundation. Booking/session/token tables are Phase 2.
9. `20260911000900_phase2_payment_methods.sql` — records Cash, UPI, Card, or Online on each simulated payment attempt.
10. `20260911001000_phase2_relationship_integrity.sql` — standardizes family relationships and permits only one active self-patient per unique caller mobile.
11. `20260911001100_phase2_verification_challenge_operations.sql` — enforces one pending challenge per saved mobile and adds bounded issue, verify, lock, and expiry operations.
12. `20260911001200_phase2_durable_booking_side_effects.sql` — synchronizes expiry/confirmation side effects and adds recoverable provider inbox/outbox leasing.
13. `20260911001300_phase2_quote_consent_snapshots.sql` — requires explicit booking consent and freezes patient, caller, schedule, doctor, location, fee, and consent evidence on each hold.
