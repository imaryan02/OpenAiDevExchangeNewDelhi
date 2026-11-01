# Gate G2 evidence — scheduling and transactional booking core

Status: **passed on 2026-09-11**.

This record separates checks already demonstrated against Supabase from checks that still depend on the owner applying the final Phase 2 migration. All test data is synthetic and tenant-isolated.

## Verified database foundations

- Migrations 001–010: tenant, staff, scheduling, patient/contact, appointments, cancellation, rescheduling, simulated payments, payment methods, and relationship integrity were applied and verified.
- Migration 011: one pending verification challenge per mobile, issue/verify/expiry functions, bounded attempts, and replay protection were verified by the owner-provided all-true result.
- Migration 012: durable inbox, outbox claim/complete/fail operations, and appointment side-effect trigger were verified by the owner-provided all-true result.
- Migration 013: explicit consent and immutable quote/contact snapshots were applied; the owner-provided verification confirmed the consent-aware function is present and the legacy bypass is removed.

## Gate behavior already exercised live

The opt-in Supabase suite in `backend/tests/test_g2_database.py` previously collected and passed eight live tests covering:

- exact-time hold and confirmation replay;
- one active booking per exact slot;
- token capacity 30 under 50 mixed AI/staff contenders;
- cancelled token gaps without token reuse;
- expired hold release and simulated payment failure;
- failed rescheduling preserving the original confirmed appointment;
- verification success, lockout, expiry, and replay behavior;
- cross-tenant rejection and canonical-doctor overlap rejection;
- stale outbox lease completion rejection.

The suite passed again after migration 013 using the consent-aware hold signature. The migration removes the legacy hold entry point so a caller cannot bypass consent.

## Scheduling edit integrity

- Weekly rule overlap is rejected before generation.
- `CLOSED` exceptions suppress dated sessions.
- `REPLACEMENT_HOURS` exceptions replace weekly hours.
- Schedule rebuild, exception creation, rule changes, and assignment deactivation execute atomically.
- Existing sessions with appointment history are retained during rebuild.

These behaviors have focused unit coverage in `backend/tests/test_schedule_generation.py`.

## Current automated checks

- Ruff: passed.
- Mypy: passed for 35 backend source files.
- Backend unit/API tests: passed; eight live Supabase tests are intentionally skipped unless `RUN_G2_INTEGRATION_TESTS=1`.
- Frontend TypeScript and Vite production build: passed.

## Phase boundary

Gate G2 covers deterministic booking correctness and does not depend on an LLM. WhatsApp delivery, voice calls, the adaptive LangGraph workflow, multilingual agent evaluations, and concurrency benchmarking belong to later phases.
