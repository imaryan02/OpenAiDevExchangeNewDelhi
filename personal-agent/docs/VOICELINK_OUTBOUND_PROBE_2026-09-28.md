# VoiceLink outbound probe, 28 September 2026

The owner authorized a single-purpose outbound diagnostic to their registered
phone. The diagnostic file is `personal-agent/scripts/voicelink_outbound_probe.py`.
It uses the same `POST /api/v1/add_lead` request shape and signed Friday binding
as the production VoiceLink adapter. It is read-only by default; `--call` places
one call after checking the owner phone, DID, and absence of an active attempt.
It prints no bearer token or signed binding.

## Observation

- Caller DID: `+919429397279`; destination: the registered owner phone.
- At **11:28:19 IST**, VoiceLink returned HTTP **201**, `status: true`,
  `message: Lead added successfully`, and outbound queue ID **4005951**.
- Friday's attempt ID is `a21d1299-038c-495a-b919-02ff05a3cb7c`.
- At **11:31:22 IST**, the attempt remained `accepted`, with no provider call ID,
  ringing event, answer event, or final event in Friday's database.
- VoiceLink **Call Logs** later showed this as a `VL-OUT` call from
  **11:28:20–11:28:39 IST**, status **NoAnswered**, duration **18s**, cost
  **₹0.00**, call ID `baba1331-6d8b-44d2-a197-da42b24bc486`, cause and
  disconnect reason **38 - Network out of order**.
- The **11:17:11–11:17:30 IST** diagnostic request also appeared in Call Logs
  as `VL-OUT`, **NoAnswered**, **18s**. Its local logger crashed after the HTTP
  request, so its queue ID was not captured; the provider log nevertheless
  confirms a call record was created.
- For these `VL-OUT` rows and in the 11:28 call detail, VoiceLink displays
  **From = 918529586946** (destination mobile) and
  **To = 919429397279** (configured DID). The API request submitted
  `did_number = 919429397279` and `customer_number = 918529586946`.
  This could be a UI/CDR convention or a reversed carrier leg; the portal
  alone cannot distinguish them.
- Two prior VoiceLink attempts to the same owner phone ended as
  `VOICELINK_CAUSE_38_NETWORK_OUT_OF_ORDER`. Their provider call IDs were
  `b41f5fd4-30f6-4f48-9a9b-6d30cc1cc142` and
  `cf9371f6-326c-4593-8b32-af385921ec03`.
- A separate Twilio callback completed previously, so the destination phone and
  Friday's voice flow have worked through another carrier.

The logger was fixed and checked with a fake HTTP response before the 11:28
IST probe. No automatic retry was configured.

## What is still unknown

HTTP 201 establishes only that VoiceLink accepted a lead into its outbound
workflow. The Call Logs show that the provider created an outbound call record
and failed the call with cause 38. They do not show whether it sent a carrier
INVITE or whether the destination was alerted. A missing Friday webhook alone
would not prove the absence of a carrier attempt.

Ask VoiceLink support to trace queue **4005951** and call ID
`baba1331-6d8b-44d2-a197-da42b24bc486`. Confirm the actual dialed party
and outbound CLI, why the CDR shows the destination mobile in its **From**
field, the carrier INVITE timestamp, whether `180 Ringing` occurred, and the
specific SIP/Q.850 source of cause 38. Also confirm that this DID has an
outbound carrier route and that the client has an outbound channel/CPS
allocation. The client management page shows one allocated channel, but that
does not establish that this route has outbound carrier capacity.

## 29 September 2026: national-number probe

At **20:29:33 IST**, one authorized probe sent the owner mobile as a **10-digit**
`customer_number` with `country_code = 91`. The DID remained 12 digits. VoiceLink
returned HTTP **201** and outbound queue ID **4116108**. The owner confirmed the
phone rang and that he answered it, but heard no Friday audio; he ended the
silent call himself.

Friday's database shows provider call ID
`b96db3fb-00c8-48cf-9856-f80f30c25ea0`, an outbound stream from
**20:30:30–20:30:39 IST**, and a `callback_started` event. There is no saved
assistant speech for this call. The provider accepted the new number format and
delivered the call, unlike the earlier 12-digit probes. This establishes a
successful outbound phone leg, while audio delivery still needs diagnosis.

The production adapter now sends the 10-digit customer number for Indian
callbacks. The Friday VoiceLink gateway also logs Realtime readiness, first
generated and sent audio, opening interruptions, and stream end timing for the
next deployed call. These code changes have not been deployed as part of this
probe. The callback provider remains Twilio until Friday audio is verified.

## 29 September 2026: post-deployment retest

At **21:32:59 IST**, a second authorized 10-digit probe returned HTTP **201**
and outbound queue ID **4116431**. The owner reported that the phone rang but
disconnected immediately on answer. The Friday follow-up ID is
`7e4839a2-b038-463c-ab36-d910b0acfa21`.

Two database reads through **21:34:39 IST** showed the attempt still `accepted`
with no provider call ID, no `personal_agent_calls` row, and no Friday media
event or transcript. The public backend liveness endpoint returned HTTP 200.
This retest establishes carrier ringing but does not establish that VoiceLink
opened a usable Friday media stream. Inspect Azure application logs around
21:33 IST for `voicelink_connection_rejected`, `personal_route_lookup_timed_out`,
`voicelink_protocol_error`, or `voicelink_gateway_failed` before another call.

The supplied Azure logs resolve that uncertainty: VoiceLink opened the media
WebSocket at **16:03:08.185 UTC**, but the backend logged
`personal_route_lookup_timed_out` three seconds later, followed by
`Unrecognized Friday callback.` VoiceLink reported `call.ended` about one
second after answer. The three-second database lookup timeout prevented Friday
from taking over the first post-deployment call.

At **21:40:20 IST**, a user-requested retry returned HTTP **201**, queue ID
**4116459**, and follow-up ID `5f854ff7-6051-4c04-b7f5-91f559f844cd`.
The owner again reported ringing followed by disconnection on answer. This
time the media WebSocket opened at **16:10:25.918 UTC** and Friday recorded
`callback_started` at **16:10:26.407 UTC**, so routing succeeded. VoiceLink
reported `call.ended` at **16:10:26.972 UTC**, roughly one second after the
answer, and `call.completed` at **16:10:27.161 UTC**. Friday recorded the stream
as ended at **16:10:35.885 UTC**, without a transcript. The later Azure logs
show `personal_voicelink_realtime_ready` at **16:10:33.178 UTC**, followed
immediately by `personal_voicelink_stream_ended` with both
`first_audio_generated` and `first_audio_sent` false. The carrier ended the
call over six seconds before Friday was ready to speak. This points to startup
timing in the callback path; it does not establish an audio codec fault.
VoiceLink's own CDR lists the retry as answered at **21:40:26 IST**, ended at
**21:40:27 IST**, with cause **16 - Normal Clearing**. That code does not show
which side initiated the hangup.

The diagnostic script's active-attempt guard now treats unresolved attempts
older than five minutes as stale while still refusing to place a call when an
active media session has heartbeated in the past minute. This enabled the
explicit retry without altering the unresolved prior callback record.

## Startup fix prepared

The Friday outbound WebSocket path now sends 20 ms G.711 A-law silence frames
as soon as it validates VoiceLink's signed stream start. The startup frames
continue through the database lookup and Realtime connection, then stop before
Friday's first speech frame. The route lookup timeout is now ten seconds rather
than three. This is meant to keep the media leg active while Friday initializes
and prevent a slow database lookup from rejecting a valid callback. The live
result follows below.

## Post-deployment result

Revision `ai-receptionist-backend--0000075` ran the startup-media change. A
single test around **23:57 IST** reached the owner phone, but disconnected
after answer. The diagnostic HTTP request itself timed out, so it returned no
queue ID; the signed callback nevertheless appeared as provider call ID
`f077db28-308e-4267-90c1-9304500679b1` and follow-up ID
`f3ea600a-f5cd-4a9b-a16f-4464af7afc6c`. Do not retry an uncertain HTTP
submission automatically.

Azure logs show the media WebSocket accepted at **18:27:14.309 UTC** and the
first A-law startup frame sent at **18:27:14.341 UTC**. VoiceLink reported
`call.ended` at **18:27:15.352 UTC**, about one second after answer, despite
startup audio. Friday's Realtime session became ready at **18:27:22.151 UTC**;
the stream ended immediately, with 378 startup frames sent and no generated or
sent Friday speech. This rules out a missing WebSocket connection or a complete
absence of outbound media. It does not prove why VoiceLink cleared the phone
leg. VoiceLink support needs to trace this exact call and identify which side
sent the disconnect and why. The documented outbound media JSON matches the
current `event=media`/base64 payload shape; no provider documentation found
that explains a one-second silence cutoff.

## Immediate opening experiment prepared

The next revision includes a one-second, pre-generated A-law "Hi Boss" using
Friday's configured Marin voice. It sends the first audible frame immediately
after the signed VoiceLink stream start, then silent frames while Realtime
connects. Once the live session is ready it knows the greeting already played,
so it waits for the owner's request rather than greeting again. This tests
whether VoiceLink is ending the leg for lack of audible speech; a continued
one-second disconnect would point more strongly to provider/carrier clearing
independent of our media content. The live result follows below.

## Immediate opening live result and next code change

Revision `ai-receptionist-backend--0000076` ran the audible opening. The
single controlled call was accepted at **00:24:42 IST** on 30 September,
queue ID `4116961`, provider call ID
`aacbafdf-f44c-4cf3-ba00-111437ce0bb6`. The owner heard a fragment of
"Hi Boss" before disconnection. VoiceLink's call log shows answer at
**00:24:49 IST**, end at **00:24:50 IST**, one second of connected audio, and
disconnect reason **16 - Normal Clearing**. The log does not identify the
side that released the call. Its seven-second call duration includes ringing.

Azure logged `personal_voicelink_opening_audio_sent` at **18:54:49.200 UTC**
and VoiceLink's `call.ended` at **18:54:50.198 UTC**. The Realtime session did
not become ready until **18:54:56.416 UTC**. Sending audible media did not
keep the carrier leg open. The later database end timestamp reflects delayed
processing of the already ended stream, not a nine-second connected call.

Code inspection found that the working inbound chained gateway consumes
VoiceLink WebSocket frames immediately, whereas Friday's callback gateway
did not begin reading them until route lookup and Realtime initialization
finished. The next revision starts a bounded receive pump as soon as the
signed outbound stream starts. It buffers incoming frames for Friday and logs
the provider's stop or disconnect when it arrives. Whether VoiceLink requires
continuous consumption for outbound calls remains unverified until a live
call on that revision. The bot is active, its DID is assigned to outbound,
its codec is G.711 A-law, and the owner heard audio, so a missing bot URL or
zero wallet balance is not supported by this call's evidence.
