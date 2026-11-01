# HospitalOS demo implementation plan

Status: Phase 1 schema and synthetic seed verified by the owner; deployment and live end-to-end verification pending. Phase 2 has not started.

## Progress tracker

Update this checklist as each step is verified. A checked implementation item means the code exists locally; it does not mean the feature is deployed.

### Phase 1 — Resource manager and locator

- [x] Write the two-phase implementation plan and demo boundaries.
- [x] Prepare the isolated facility migration, three-facility synthetic seed, and verification queries.
- [x] Build the deterministic matching logic and public facility API.
- [x] Build authenticated resource viewing and admin-only updates with version checks and audit events.
- [x] Build the public patient/ambulance locator at `/demo/hospitalos`.
- [x] Add Resources to the existing clinic workspace.
- [x] Pass frontend typecheck/build, backend lint/typecheck, and four matching tests.
- [x] Confirm the intended Supabase database and review its migration ledger (no Supabase migration ledger table was present in the earlier schema inspection).
- [x] Apply the Phase 1 migration and synthetic seed; verify the three facility rows. Owner-provided result shows only Geeta connected.
- [ ] Enable `HOSPITALOS_DEMO_ENABLED` on the backend connected to that database.
- [ ] Enable `VITE_HOSPITALOS_DEMO_ENABLED` in Vercel after the backend is ready, then redeploy the frontend.
- [ ] Verify the live two-screen flow: edit Geeta resources, refresh the locator, and see eligibility change.
- [ ] Verify staff access controls and existing clinic behavior in the deployed environment.
- [ ] Deploy the frontend and backend changes when the database is ready.

**Phase 1 is complete when** all Phase 1 boxes are checked and its acceptance criteria below pass.

### Phase 2 — Receiving request and decision

- [ ] Add durable requests, events, tracking tokens, expiry, and idempotency.
- [ ] Add public request submission and tracking for Geeta Medicine only.
- [ ] Add Geeta admin inbox with accept/decline and resource recheck.
- [ ] Add task activity and fallback display backed by persisted events.
- [ ] Test duplicate, timeout, stale, and cross-tenant cases; rehearse the two-browser demo.
- [ ] Deploy and verify the complete request-to-decision flow.

**Phase 2 is complete when** all Phase 2 boxes are checked and its acceptance criteria below pass.

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
4. Add an auditable conflict/fallback scenario and a small task-activity panel driven by actual backend events. Keep agent suggestions informational and outside the acceptance transaction.
5. Run the two-browser demo, timeout/duplicate/unauthorized tests, reset procedure, and deployment checks.

**Phase 2 acceptance:** A request sent from the portal appears in Geeta's inbox; an authorized admin decides it; the requester sees the persisted result; stale, duplicate, expired, or cross-tenant actions fail safely.

## Demo script

Show Geeta's resource screen, then the patient/ambulance locator. Change a resource and refresh recommendations. In Phase 2, select Geeta, send a receiving request, accept it in the staff inbox, and show the tracking result. Finish with the existing OPD voice receptionist as a separate capability.
