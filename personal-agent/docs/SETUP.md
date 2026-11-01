# Local foundation setup

Current implementation: owner-protected personal APIs and a separate dashboard.
The personal prompt/tools/memory runtime and VoiceLink inbound dispatch/gateway
are implemented locally. The VoiceLink outbound adapter and signed callback
binding are implemented locally; the account API token and live verification
are still required. Twilio is reserved for WhatsApp.
Actual callback and WhatsApp execution remain pending.
A saved follow-up is persistent data, not an active callback.

## Backend

The owner has supplied grant-check output showing all nine tables exist and
anonymous reads/client writes are disabled. All nine tables have RLS enabled and
the owner read policy present; the owner reports zero unexpected external-FK
targets. Do not reapply the migration blindly.

Use the normal backend deployment/build; its router now mounts
`/v1/personal-agent`. Configure:

```env
PERSONAL_AGENT_ENABLED=true
PERSONAL_AGENT_OWNER_ID=<existing Supabase Auth user UUID>
PERSONAL_AGENT_REGISTERED_PHONE=<registered E.164 phone>
PERSONAL_AGENT_DEMO_CONTROLS_ENABLED=true
PERSONAL_AGENT_OUTBOUND_ENABLED=false
PERSONAL_AGENT_WHATSAPP_ENABLED=false
```

Use the existing login's user ID from `/v1/me`, or the authenticated
`/v1/personal-agent/readiness` response when the owner is not yet configured.
Do not use the organization UUID or assume `VOICE_ACTOR_ID` is the correct owner.
Restart the backend after settings change because settings are cached.

The feature is disabled by default. The owner ID is an explicit server allowlist;
other authenticated staff are not automatically entitled to personal records.
The browser cannot choose another owner through request arguments.

Backend writes require a SQL connection authorized to write the new personal
tables. Browser SELECT policies do not grant the backend elevated SQL access.
Keep database credentials server-side.

## Dashboard

Open `/demo/personal-agent` on the existing frontend. It reuses sign-in and token
refresh, but initializes its own workspace rather than the clinic dashboard.
The Vercel SPA rewrite already supports this route.

Ensure `VITE_API_BASE_URL` points to a backend containing the new personal APIs.
Alternatively set `VITE_PERSONAL_AGENT_API_BASE_URL` for Friday only. Local
`frontend/.env.local` now contains this override to `http://127.0.0.1:8001`, so
restarting Vite preserves the demo connection without changing receptionist API
configuration. Restart the local backend on 8001 when it is not running.
Deploying the new frontend against an old backend produces a clear
"Personal AI not deployed" error. Vite API configuration is embedded at build
time. The current local review launches Vite with a process-local API override;
the deployed frontend API URL has not been changed.

After signing in as the configured owner:

1. Register the E.164 phone, timezone and language.
2. Seed rehearsal tasks if demo controls are enabled, or add tasks manually.
3. Edit/complete/remove tasks and inspect activity.
4. Save, reschedule, acknowledge or cancel a follow-up. The saved countdown uses
   backend time, but the screen explicitly reports execution as pending.
5. Reset only when there are no active calls or uncertain/in-progress provider
   actions. Reset hides old activity through a new generation, clears recent
   memory, soft-deletes personal tasks and restores receptionist mode.

Personal AI mode can be selected once the deployed backend is enabled, its owner
profile is registered and voice configuration is present. Call the existing
VoiceLink number from the registered phone to verify Friday. Other callers still
reach the receptionist; changing the toggle does not replace an ongoing agent.
Implementation/configuration indicators do not establish live call acceptance.

## APIs in this slice

| Path | Operations |
| --- | --- |
| `/readiness` | Authenticated setup/capability flags; no provider health claim |
| `/profile` | Owner profile GET/PUT |
| `/mode` | Saved new-call mode with voice configuration/registered-phone checks |
| `/snapshot` | Bounded personal dashboard data and server time |
| `/tasks` | List/create; today filter includes overdue and undated pending tasks |
| `/tasks/{id}` | Version-checked update and soft delete |
| `/followups` | Save a contextual reminder and selected task snapshot |
| `/followups/{id}/action` | Version-checked acknowledge/cancel/reschedule |
| `/events` | Activity paging with a stable ID cursor |
| `/memory` | Expiry-filtered owner conversation review and access activity |
| `/demo/seed`, `/demo/reset` | Explicitly enabled owner-only rehearsal controls |

All paths are prefixed `/v1/personal-agent`. Successful writes commit before the
HTTP response is sent. Conflicting versions return an error rather than
overwriting newer data. The UI retains edit text after failed saves.

## Remaining acceptance

- Verify actual owner isolation and API transactions against the applied database.
- Verify task/follow-up/profile operations against the applied database.
- Configure demo owner and deploy both applications.
- Verify the new personal gateway, tools and memory with real inbound calls.
- Select/verify outbound provider and visible callback number.
- Connect registered-caller voice dispatch, scheduler, retry and WhatsApp delivery.

Read-only account/number checks are recorded in `PROVIDER_READINESS.md`. The
configured Twilio account is a trial account, and its voice number differs from
the existing VoiceLink number. Actual callback audio and WhatsApp receipt remain
unverified.

Initial browser inspection found that the deployed API did not serve the new
personal routes. The later owner setup below saved only personal profile/activity
data and verified the local dashboard against the applied database. No provider
call or message was sent.

## Verified local owner setup — 27 September 2026

- Owner UUID and registered phone saved in ignored `backend/.env`.
- Local personal feature and rehearsal controls enabled; outbound and WhatsApp disabled.
- `scripts/setup_owner.py --apply` confirmed the existing Auth user and saved the
  personal profile. A new transaction verified owner/phone, Receptionist mode,
  Asia/Kolkata timezone and WhatsApp fallback off.
- The authenticated local dashboard loaded real profile, activity and empty
  tasks/follow-ups through `/readiness` and `/snapshot`. No tasks/reminders seeded.
- This is not a production deployment or live Friday voice acceptance.

To repeat the local preview, run these in separate PowerShell terminals from
the repository root. Backend lifespan is off to avoid running shared maintenance
against the live database during UI review:

```powershell
$env:CORS_ORIGINS='["http://127.0.0.1:5173","http://localhost:5173"]'
Set-Location backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --lifespan off
```

```powershell
$env:VITE_API_BASE_URL='http://127.0.0.1:8001'
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/demo/personal-agent`. Use the existing owner login.
Production needs its own personal environment settings and normal deployments;
these local processes do not receive the existing number's public carrier stream.

## Personal runtime contract

`service.PersonalRuntime` is an internal interface for the next voice phase, not
a browser tool-execution endpoint. Construct it only after authenticating the
carrier and persisting a personal call owned by the configured demo user.

- `prepare()` returns the separate instructions and ten personal tool schemas.
- `execute()` validates arguments, checks active call/reset generation, persists
  duplicate-request results and commits before returning.
- `remember()` stores a bounded final transcript item using its provider source
  ID and speaker; persist items before changing the call to an ended state.
- `memory.prune_expired()` is available for owner-scoped worker cleanup.

The gateway must supply exact call/source/request identities, handle unexpected
errors truthfully, and avoid publishing uncommitted success. SQL transactions
finish before network/audio work. The personal VoiceLink gateway invokes this runtime.

The registered number requested in this chat is saved in the ignored local
backend environment. For deployment, copy the registered-phone setting through
the deployment configuration; existing live profiles are not silently overwritten.

## Scheduler gates

`PERSONAL_AGENT_SCHEDULER_ENABLED` defaults false. Startup also requires the
personal feature, configured owner/database, outbound enablement and
`PERSONAL_AGENT_VOICELINK_API_TOKEN`. Local execution flags remain off.
Lease duration defaults to 120 seconds. Reminders more than 900 seconds overdue
require review instead of triggering an unexpected late call. Both are configurable.
The worker records attempts and protects against duplicate submissions. An
authenticated missed-call final status schedules one five-minute retry; uncertain
results stay for review. This requires live provider verification. Automatic
Automatic WhatsApp fallback is coded for opted-in profiles after the final
missed attempt. The configured sender is Twilio's Sandbox, which cannot use
custom templates. The recipient must join it and send a WhatsApp message within
24 hours before the demo for a free-form reply window. One short free-form Friday
message was sent through the configured account on 27 September 2026 and reached
Twilio status `read`. The deployed Friday tool and its status callback remain
unverified.

## WhatsApp gate

`PERSONAL_AGENT_WHATSAPP_ENABLED` defaults false. When enabled with the Twilio
WhatsApp sender, public backend URL and registered profile phone, Friday exposes
`send_whatsapp_update` during a personal call. The tool submits a server-built
summary after an explicit request and stores provider status callbacks. Provider
acceptance is reported as submitted, not delivered. Verify sender/recipient
eligibility and the WhatsApp conversation window or approved template before
enabling this for the presentation. For business-initiated messages outside the
24-hour window, set `PERSONAL_AGENT_WHATSAPP_CONTENT_SID` to an approved Twilio
template with one text variable (`{{1}}`) for the update body. Without it, the
client sends a free-form body, which requires an open service window. A custom
approved template requires a registered WhatsApp sender; the Sandbox does not
support custom templates.
