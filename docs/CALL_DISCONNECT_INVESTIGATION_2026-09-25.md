# Incoming-call disconnect investigation

## Evidence

The caller reported that calls sometimes end immediately, or connect for about
10 seconds and disconnect just before the AI greeting.

The frontend points to `ai-receptionist-backend.kindocean-a1f0cf18.centralindia.azurecontainerapps.io`.
An initial public `/health/live` request took **25.253 seconds**. The next request
took **0.168 seconds**; `/health/ready` returned 200 in **1.293 seconds**. Liveness
does not query a database or AI provider. This timing difference is consistent
with container cold start, though it alone cannot prove a particular call's cause.

The authenticated Azure portal subsequently confirmed revision `0000046` had
**minimum replicas 0**, maximum 10, with an HTTP scaling rule. This allows the
backend to stop between calls. A carrier's call-setup deadline can expire before
the application is available.

## Applied in Azure

Changed the minimum replica count to **1**, preserving maximum replicas and the
existing scaling rule. Azure created revision `0000047`; the portal verified it
was **Running**, with **one replica and 100% traffic**. The old revision had 0%
traffic and was deprovisioning. Public liveness then returned 200 in **0.226 seconds**.
An idle running replica consumes Azure credits. This was a configuration change
using the existing image; the local code changes below are not yet deployed.

The user reported the subsequent real telephone test **still failed**. Therefore,
scale-to-zero was a confirmed deployment risk, but eliminating it has not resolved
the full incident.

### Confirmed cause from the VoiceLink call record

On follow-up inspection, the VoiceLink call detail for the 02:01 inbound attempt
identified the disconnect reason as **Insufficient Wallet balance**. The dashboard
showed eight `NoAnswered` inbound calls at 0 seconds, and the selected call's detail
showed the same reason. The reseller account displayed ₹168.33, while the assigned
client account showed **-₹0.50**. The client plan lists **₹0.50 inbound per pulse**.
These are separate balances: reseller funds do not automatically make the client's
wallet positive. VoiceLink is rejecting the call at billing/routing setup, before
it starts a backend WebSocket. This explains why no carrier call appeared in the
Azure logs and why the symptom persisted after the warm-replica change.

The DID call-setting page also showed “No active agents found.” That may be another
configuration issue, but the call's explicit billing disconnect reason takes
priority; the no-agent warning alone does not establish the cause of these calls.
Do not add a mobile agent as a workaround without confirming it preserves the
intended AI route. The next required action is to add funds to the **client wallet**
so its balance is positive, then retest and inspect the new call's disconnect reason
and Azure log entry. This billing action was not performed here.

An authenticated direct WebSocket handshake to the deployed gateway succeeded.
A synthetic chained call-start probe returned the first audio packet in **4.750
seconds**, including a **328 ms** handshake. It sent `stop` immediately afterward;
no appointment was requested. This tests backend greeting generation, not carrier
delivery. The portal showed `VOICE_ENGINE=chained` with five Realtime canary caller
numbers configured. Caller-specific routing must be considered in live diagnosis.

Historical logs loaded after the reported failure showed application lifecycle
and health checks, but no telephone call attempt in that retrieved window. Azure
warns that historical logs can lag by 1-5 minutes, so absence is not conclusive.
Initially, the next required evidence was the VoiceLink destination and failed-call
record. A later historical-log refresh showed both diagnostic connections:
On a later historical-log refresh, both diagnostic connections appeared: the
handshake-only check at 20:27 UTC and the synthetic call at 20:29 UTC, including
an OpenAI speech HTTP 200 response. No real carrier call appeared between startup
and those probes in the retrieved hour. This confirms the synthetic Azure probe
ran independently of the failed carrier call; it does not show that VoiceLink
dispatched the incoming call to Azure.

## Code and deployment review

- The GitHub deployment workflow did not enforce a minimum replica count and
  contained unused template-placeholder inputs. It now selects the root
  Dockerfile, port 8002, and enforces and verifies a minimum of one after deployment.
- In the chained VoiceLink gateway, a cold greeting waited for full TTS synthesis
  under the same global lock used for fillers. It now streams first audio without
  that lock and only caches successfully completed synthesis. Caller profile lookup
  has a five-second wait bound after greeting playback; lookup failure uses the
  existing unknown-profile fallback.
- Chained outgoing media and marks lacked the active stream ID already used by
  the Realtime gateway. The shared send method now supplies it.
- Added connection-rejection reasons, disconnect codes, and chained first-audio
  latency logs, without recording stream secrets.
- The deployment guide supplied a nonexistent media route and omitted required
  voice settings. Corrected the URL to `/v1/voicelink/media?token=...`, documented
  required settings, always-running replicas, and rollout checks.

## Remaining diagnostic limits

The frontend is not in the carrier audio path. Backend route registration,
provider adapters, database session setup, call runtime, deployment files, existing
project audit and regression tests were reviewed for this incident. This is not
a line-by-line security audit of every screen and database migration.

The Realtime engine still performs database and OpenAI session setup before its
controlled greeting. Its per-stage connect timeouts can exceed the reported
10-second cutoff when dependencies are slow. Do not switch engines or relax call
ownership/consent guards without measuring the deployed engine and failure logs.

The generic readiness service can report success through Supabase Auth HTTPS
even when direct PostgreSQL is unavailable. A green health endpoint therefore
does not prove voice database queries, TTS, or carrier audio work.

The local backend environment contains a historical tunnel URL; local settings
must not be treated as the deployed Azure configuration. No secrets were rotated.

## Live acceptance

Test an immediate call and several calls after idle periods exceeding the prior
five-minute cooldown. Verify the greeting is audible promptly and the conversation
continues. Correlate carrier call IDs and timestamps with `voicelink_call_started`,
`voicelink_greeting_failed`, `voicelink_protocol_error`, and `voicelink_gateway_failed`.
After deploying the local changes, also inspect `voicelink_connection_rejected`
and `voicelink_first_audio_sent`. If a failed call never reaches the gateway,
inspect carrier setup/CDR errors and Azure ingress/system logs.

Do not infer end-to-end telephone success from an HTTP health check alone.

## Local validation

Backend: **261 passed, 8 live database tests skipped**. Ruff passed; Mypy passed
for 68 source files. Frontend production build passed. A pre-existing Starlette
test-client deprecation warning remains. The startup regression explicitly tests
first audio while TTS is still pending, independence from the filler lock, stream
IDs, completed cache reuse and rejection of partial failed synthesis.
