# HospitalOS demo implementation plan

Status: Phase 1 and the core Phase 2 request workflow are implemented locally. The Phase 1 demo rows and Phase 2 RLS tables are verified in the intended Supabase database. Deployment is deferred by the owner.

## Progress tracker

Update this checklist as each step is verified. A checked implementation item means the code exists locally; it does not mean the feature is deployed.

### Development audit — 1 November 2026

| Demo capability | Current state | Gap before the blueprint's five-minute demo |
| --- | --- | --- |
| Three synthetic facilities | Database rows verified; only Geeta is connected | None for the three-listing demo |
| Public locator and explainable ranking | Implemented with fixed Delhi origins, straight-line demo distance, resource checks, preference sorting, listed capabilities, and active-hold-adjusted ED/ICU availability | Road ETA, independently verified evidence, and a separate clinical-requirement path for qualified users |
| Geeta resource manager | Admin update API and clinic board show ready, held, available, pending, capability, source, and freshness details; isolated DB edit-to-locator and hold-aware tests passed | Occupied/blocked states, staffing/equipment evidence, branch-specific roles, and deployed verification |
| Patient and ambulance entry | One shared screen with an audience switch; patient mode keeps the requirement unknown/general | Verified EMS/clinician identity and distinct workflow rules remain future work |
| Request to Geeta and admin decision | Local API, public tracking, Geeta inbox, accept/decline, optional admin arrival note, timeout, withdrawal and ETA update implemented; Phase 2 tables created with RLS | Live two-browser rehearsal and verified contact/navigation details remain |
| Resource hold and conflict | Transactional pooled ED/ICU hold; locator subtracts active holds and a new request is rejected when all ready spaces are held; simultaneous two-case local test yields one acceptance and one conflict | No per-bed identity or lifecycle beyond active/released/expired demo hold |
| Supervisor and specialist activity | Optional AI supervisor chooses a bounded task; admin triggers deterministic checks; actual results are persisted as events | Live model invocation and wider autonomous task orchestration are untested/not in this demo |
| Release verification | Isolated PostgreSQL flow, RLS, reset, concurrency, frontend build/tests and targeted backend checks pass; owner verified four Phase 2 RLS tables | Live two-screen rehearsal and deployment checks |

**Assessment:** The core synthetic demo passed against an isolated database, and the owner applied the Phase 2 schema to Supabase. It is not live: the Azure/Vercel versions have not been activated. Road ETA, real contact details, detailed staffing/equipment states, and a full network command center remain outside this thin demo.

**Resource presentation update:** The clinic now shows a connected Geeta resource board and a read-only three-facility comparison. The locator displays ready, active hold, and available ED/ICU counts, plus all four listed capability flags. The receiving inbox has a guided empty state. These values come from the existing Phase 1 and 2 tables; no new migration is required. Frontend build/typecheck, matching unit tests, backend lint/typecheck, and the isolated PostgreSQL request workflow passed locally. A visual two-browser rehearsal and deployed verification remain open.

### Phase 1 — Resource manager and locator

- [x] Write the two-phase implementation plan and demo boundaries.
- [x] Prepare the isolated facility migration, three-facility synthetic seed, and verification queries.
- [x] Build the deterministic matching logic and public facility API.
- [x] Build authenticated resource viewing and admin-only updates with version checks and audit events.
- [x] Build the public patient/ambulance locator at `/demo/hospitalos`.
- [x] Add Resources to the existing clinic workspace.
- [x] Pass frontend typecheck/build and 28 frontend tests, backend lint and HospitalOS typecheck, and four matching tests. Full local backend typecheck is blocked by missing OpenTelemetry packages; two async access tests are skipped in the Windows sandbox.
- [x] Keep patient specialty selection hidden and reset to unknown/general when switching from ambulance mode; EMS demo copy requires a clinical source.
- [x] Run the access and resource update-to-locator checks against an isolated PostgreSQL test database.
- [x] Confirm the intended Supabase database and review its migration ledger (no Supabase migration ledger table was present in the earlier schema inspection).
- [x] Apply the Phase 1 migration and synthetic seed; verify the three facility rows. Owner-provided result shows only Geeta connected.
- [ ] Enable `HOSPITALOS_DEMO_ENABLED` on the backend connected to that database.
- [ ] Enable `VITE_HOSPITALOS_DEMO_ENABLED` in Vercel after the backend is ready, then redeploy the frontend.
- [ ] Verify the live two-screen flow: edit Geeta resources, refresh the locator, and see eligibility change.
- [ ] Verify staff access controls and existing clinic behavior in the deployed environment.
- [ ] Deploy the frontend and backend changes when the database is ready.

**Phase 1 is complete when** all Phase 1 boxes are checked and its acceptance criteria below pass.

### Phase 2 — Receiving request and decision

- [x] Prepare the owner-run Phase 2 migration for durable requests, hashed tracking tokens, expiry, idempotency, holds, and append-only events.
- [x] Add public request submission and private tracking for Geeta Medicine only.
- [x] Add Geeta admin inbox with accept/decline, version checks, and resource recheck.
- [x] Add informational fallback, withdrawal, and updated ETA handling backed by persisted events.
- [x] Add a transactional pooled demo resource hold; the simultaneous two-case local test produced one accepted request and one conflict.
- [x] Add a bounded AI supervisor suggestion, human-triggered specialist checks, and real outcome events in the task panel.
- [x] Test duplicate, timeout, stale, cross-tenant, resource edit, and hold-conflict paths on isolated PostgreSQL; pass frontend build and tests.
- [x] Apply the Phase 2 migration to the intended database; owner verification shows RLS enabled on cases, requests, holds, and events. Do not run a broad migration push.
- [ ] Rehearse the request-to-decision flow in two browsers and verify the real model suggestion path if enabled.
- [ ] Deploy and verify the complete request-to-decision flow.

**Phase 2 is complete when** all Phase 2 boxes are checked and its acceptance criteria below pass. The owner has deferred the database and deployment steps.

## Product boundary

- Keep the existing Geeta Medicine appointment, patient, voice, and Friday workflows intact.
- Show three clearly labelled synthetic facilities in a public patient/ambulance locator. Geeta Medicine's Main Branch is the only connected receiving desk.
- HospitalOS resource values are demo data. They are separate from appointment-session capacity and must never be presented as verified live emergency capacity.
- The locator provides facility information and a direct 112 call action. It does not diagnose, triage, direct transport, or guarantee treatment.
- Only Geeta's authorized organization administrators can edit its resource values or decide its receiving requests.

## Phase 1 — Resource manager and public locator

Build a thin end-to-end read path before adding consequential requests.

1. Add one isolated hospitalos_facilities table with synthetic facility profiles, coordinates, capability flags, resource counts, update timestamps, versioning, and an optional link to an existing organization/location. Enable RLS. Provide a separate idempotent demo seed for three facilities, linking Geeta to its existing Main Branch.
2. Add a public, curated facility API. Deterministic matching excludes closed, stale, or missing required resources from the recommended group. Rank eligible options by distance and affordability preference, and return explicit reason codes. Unknown clinical requirements remain the default.
3. Add an authenticated Geeta resource read/update API. Enforce organization-admin access, optimistic versioning, bounded counts, and a server-generated verification timestamp.
4. Add /demo/hospitalos for patient/ambulance discovery and a Resources page in the existing staff workspace. Both display the synthetic-data boundary clearly. A Geeta resource update must change the next locator response.
5. Verify matching edge cases, tenant authorization, stale data, frontend typecheck/tests/build, and existing clinic regressions.

**Phase 1 acceptance:** Three facilities appear; Geeta's saved readiness affects eligibility; an admin can edit Geeta resources; stale or unavailable resources are never labelled ready; the existing clinic workspace still builds and operates. No request is presented as accepted.

**Database gate:** The owner applied the new migration and synthetic seed to the intended database and supplied a verification result with three rows. Geeta is the only connected facility. The broader historical migration set remains untouched; its duplicate version still rules out a blind `supabase db push`.

**Enable sequence:** The owner has completed the database scripts and row verification. Deploy the new backend image with `HOSPITALOS_DEMO_ENABLED=true` on the Azure app connected to that database. Set `VITE_HOSPITALOS_DEMO_ENABLED=true` in Vercel and redeploy the frontend. Visit `/demo/hospitalos`, then sign in to the existing clinic and open Resources. The Vercel flag keeps the Resources navigation hidden until the backend is ready.

## Phase 2 — Receiving request and decision

1. Add durable hospitalos_requests and append-only event records. A public requester receives a private tracking token, and only the addressed Geeta staff can see the inbox.
2. Implement one active request per demo case, idempotent creation, a configurable deadline, explicit accept/decline, version checks, and safe expiry. Acceptance rechecks Geeta resource state in the transaction. Expiry never auto-accepts.
3. Add request tracking to the public portal and a Receiving requests page to the Geeta workspace. Poll the persisted state; show contact details only after an authorized decision. Other synthetic facilities remain comparison listings.
4. Add an auditable hold-conflict/fallback scenario and a task panel driven by persisted backend events. Implement narrow supervisor/resource/coordination task tools for the demo; keep agent suggestions informational and outside the acceptance transaction.
5. Run the two-browser demo, timeout/duplicate/unauthorized tests, reset procedure, and deployment checks.

**Phase 2 acceptance:** A request sent from the portal appears in Geeta's inbox; an authorized admin decides it; the requester sees the persisted result; stale, duplicate, expired, or cross-tenant actions fail safely.

**Phase 2 database gate (passed):** The owner applied `supabase/migrations/20261101000200_hospitalos_requests.sql` and supplied verification showing RLS enabled on all four new tables. The optional owner-run reset is `supabase/seeds/20261101000200_hospitalos_demo_reset.sql`; it clears only synthetic cases, requests, holds, and events. The migration, checks, and reset were also exercised on an isolated PostgreSQL 18 fixture.

**Release order after the owner resumes deployment:** Apply and verify the Phase 2 migration; deploy the backend image with the HospitalOS demo flag; enable the Vercel demo flag and redeploy; then rehearse the patient/Geeta two-browser flow. Keep the old Azure deployment in place until the owner triggers its manual workflow.

## Demo script

Show Geeta's resource screen, then the patient/ambulance locator. Change a resource and refresh recommendations. In Phase 2, select Geeta, send a receiving request, accept it in the staff inbox, and show the tracking result. Finish with the existing OPD voice receptionist as a separate capability.
