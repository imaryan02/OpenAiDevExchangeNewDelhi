# Call review dashboard and conversation capture

The clinic call history now has a filtered call index and a dedicated detail view: Overview, Conversation, Turns, Actions, Performance, Usage, and Diagnostics. Ended calls are not labeled successful bookings. Outcomes come from linked durable operations. Repeated audio transport events are collapsed; directions, elapsed time, tool invocation IDs and database query IDs are retained for new calls. Old events without measured time remain explicitly unmeasured.

Conversation messages use a separate table and authenticated backend endpoint. Current reception/clinic access is preserved; no additional roles were introduced. Every successful text read commits an access audit before returning text, and responses use `Cache-Control: no-store`. Direct authenticated/anonymous Supabase text reads are revoked. Caller messages are transcriptions; agent messages are generated text or generated audio transcripts, not evidence that playback was heard. Raw recordings are not implemented.

## Enable after deployment

1. Apply only `supabase/migrations/20260927000300_voice_review_observability.sql` in the Supabase SQL editor. Do not replay historical migrations or assume a migration ledger exists.
2. Run `supabase/verification/20260927000300_voice_review_checks.sql`. The first result should contain all `true` values. The second query returns recent counts without conversation text.
3. Deploy backend and frontend. The backend database credential must have trusted write/read access to these tables; browser Supabase credentials intentionally cannot read messages directly.
4. In Azure, select the existing `ai-receptionist-backend` container and add/update these environment variables without removing its other settings:

   ```env
   VOICE_TRANSCRIPT_CAPTURE_ENABLED=true
   VOICE_TRANSCRIPT_RETENTION_DAYS=7
   ```

   These are configuration values, not secrets. Save a new revision. Capture defaults to `false` in code and `.env.example`; no private local `.env` was changed.
5. Place an approved inbound test call, review Conversation, then run the verification query again. Confirm retained messages and audited reads increase. Repeat for both engines, including interrupted playback. Older calls with capture disabled cannot be backfilled.

## Retention and limitations

Expired text is excluded immediately by the read endpoint and removed by the existing minute maintenance loop when the backend is running. Turning capture off stops new text capture; previously captured unexpired messages remain readable until expiry. Seven days is the default, configurable from 1 to 90 days; adopt the organization's approved retention and caller-disclosure policy before enabling production capture. Text may contain personal information and is stored as text in the database; this change does not add application-level encryption.

The asynchronous capture queue remains best effort. Overflow/write failure marks incompleteness where possible, but process crashes can lose queued records. Connection attempts require a configured organization to be attributed; no token or caller text is stored. Attempt and technical/audit metadata retention, shared ingestion, collector export, quality evaluation, recording consent/storage, cost calculation and alerts remain later work. Operations (100) and usage (500) are bounded detail snapshots, so very large calls can have additional records outside the displayed snapshot. Events and conversation messages have load-more controls.

## Local validation

Backend: 276 passed, 15 skipped; Ruff and mypy pass. Frontend: production build and 23 tests pass. Browser preview with synthetic data confirmed the call overview and Hindi/Hinglish chat evidence labels at the narrow in-app viewport. The preview screenshot is synthetic, not a customer call. Live Supabase migration, deployed capture and provider acceptance remain pending.
