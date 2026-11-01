# Remediation plan

This plan implements the findings in `PROJECT_CODE_REVIEW_2026-09-26.md` in an order that protects callers and appointment data first.

1. **Consent and voice execution** — require a server-held preview and a later explicit confirmation for every cancellation and reschedule; return a concrete server result to the Realtime conversation.
2. **Appointment integrity** — make rescheduling enforce target eligibility, cutoff, price/currency compatibility, snapshots, and payment visibility in the database transaction.
3. **Operational correctness** — require a direct database connection for readiness, generate rolling sessions in maintenance, refresh Supabase sessions, paginate dashboard records, and correct dashboard metrics.
4. **Privacy and lifecycle** — stop logging caller content, expire/end voice operation sessions, mark AI voice bookings with the proper source, and archive patients by default.
5. **Delivery and deployment** — implement outbox dispatch/gating and make deployment wait for the same checks as CI.
6. **Migration release check** — reconcile the duplicate historical migration version against the deployed Supabase migration ledger before any rename. Renaming an already-applied migration would make an environment unrecoverable, so this step requires the ledger as external evidence.

Each implementation change is accompanied by the narrowest useful automated verification, then the backend and frontend validation suites are run before release.

Cross-check status and remaining acceptance evidence are recorded in
`CHANGE_CROSSCHECK_2026-09-26.md`. The migration ledger step remains pending; the
historical duplicate filename is preserved until that evidence is available.
