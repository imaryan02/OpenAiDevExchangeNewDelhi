# HospitalOS synthetic demo runbook

The Azure and Vercel activation steps are deferred. The owner applied the Phase 2 migration and verified that all four new Supabase tables have RLS enabled. The request flow was tested on an isolated PostgreSQL fixture; the deployed two-browser flow has not been rehearsed.

## Before activating the demo

1. The owner has already run `supabase/migrations/20261101000200_hospitalos_requests.sql` and verified RLS on the four new tables. Do not run the historical migrations as a batch or share tracking-token hashes.
2. When deployment resumes, push the local Phase 2 code, check CI, then use the manual Azure workflow for the new backend. Set the Vercel `VITE_HOSPITALOS_DEMO_ENABLED=true` build variable after the API is ready, then redeploy the frontend.
3. Sign in as a Geeta organization administrator. Open Resources and save the synthetic snapshot shortly before rehearsal; stale snapshots are not recommended after 24 hours. Confirm at least one ready receiving space.

## Two-browser rehearsal

1. **Staff browser:** open `?page=receiving` in the existing clinic workspace. Keep it visible.
2. **Public browser:** open `/demo/hospitalos`. Confirm the synthetic banner and 112 action. Select Central Delhi, any cost preference, and Geeta Medicine. Send a demo receiving request. Do not enter real patient data.
3. **Staff browser:** confirm the new case reference and deadline. Optionally ask the AI supervisor for a bounded task suggestion, then choose whether to run a deterministic operational check. The suggestion never accepts a request.
4. Optionally add a synthetic arrival note, then accept the request. The API rechecks Geeta resources and creates a provisional pooled hold only if capacity is still ready. Return to the public browser and confirm the persisted `ACCEPTED` status, note and hold notice. This is a pre-arrival app response, not an admission or transport decision.
5. Repeat with Geeta's ready receiving space set to one and two concurrent cases. Exactly one acceptance should create a hold; the other should show `HOLD_CONFLICT` and human review. The isolated database integration test exercises this transaction path.
6. Also rehearse decline, timeout, withdrawal, and ETA update. The public tracking token stays in that browser's session storage and never appears in the URL.

## Reset between demos

After all browsers stop polling, the database owner can run `supabase/seeds/20261101000200_hospitalos_demo_reset.sql`. It clears only HospitalOS cases, requests, holds, and events. It keeps the three facility listings and their resource values. Refresh both browsers and clear the public browser's stored demo tracking before starting another case.

## Known demo limits

- Distances are synthetic straight-line estimates from fixed Delhi origins, not road ETA.
- The resource screen has pooled ready counts, not identified beds, staff shifts, or equipment maintenance states.
- The two comparison listings have no connected receiving desk. Fallback is informational and never sends them a request.
- The admin may provide a demo arrival note. No verified contact number, admission instruction, EMS dispatch, or navigation handoff is supplied.
- The AI supervisor requires an existing configured OpenAI key/model; its selection is a suggestion that an administrator must choose to run.
