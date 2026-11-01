# Provider readiness

Initial read-only checks were performed on 27 September 2026. Later that day,
the owner joined the Twilio Sandbox and authorized one free-form Friday check
message to their registered number. No phone call or VoiceLink configuration
change was made; credential values were not logged.

| Check | Observed result |
| --- | --- |
| Twilio account lookup | HTTP 200; active account |
| Account type | Trial |
| Configured Twilio number lookup | HTTP 200; owned and voice capable |
| Existing VoiceLink number equals configured Twilio number | No |
| Outbound streamed call and audio | Not verified |
| WhatsApp free-form delivery | One authorized API message accepted; Twilio status `read` |
| Friday's signed delivery callback | Not verified on deployed backend |
| VoiceLink outbound adapter in this repository | Implemented locally; unverified live |
| VoiceLink outbound API credentials | Bearer token configured locally; Azure not configured |
| VoiceLink account documentation | Signed-in portal reviewed; single-lead API and WebSocket/call webhooks documented |

The owner requires the existing VoiceLink number for inbound calls and callbacks.
Twilio is reserved for WhatsApp. The signed-in VoiceLink account shows the existing
DID selected for both inbound and outbound on its active WebSocket bot. Its
[API documentation](https://app.voicelink.co.in/developer/docs) documents
`POST /api/v1/add_lead` with bearer authentication, DID, destination and custom
parameters. The [call flow](https://app.voicelink.co.in/documentation/call-flow/),
[stream events](https://app.voicelink.co.in/documentation/websocket-events/), and
[call webhooks](https://app.voicelink.co.in/documentation/webhook/) describe
answer/start/end and context propagation. No live acceptance or caller ID check
has been performed.
Do not enable callback execution yet.

The configured sender is Twilio's Sandbox. The owner joined it, replied to the
trial template, and a short free-form Friday message sent through the configured
account reached Twilio status `read`. This confirms free-form delivery in the
current 24-hour window. Automatic fallback is coded for opted-in profiles, but
the recipient must reopen that window before each rehearsal. The Sandbox does
not support custom templates; Friday's deployed tool and signed callback still
need end-to-end verification.

`personal-agent/scripts/provider_preflight.py --remote` repeats these read-only
account/number checks. The default invocation only reports configuration presence.
