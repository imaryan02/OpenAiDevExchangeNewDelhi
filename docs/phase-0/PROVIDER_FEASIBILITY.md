# Provider feasibility matrix

Legend: `RESEARCHED` means vendor documentation was reviewed. `VERIFIED` requires a reproducible account/test result. `BLOCKED` means a prototype path cannot proceed without a decision or account change.

| Capability | Planned provider | Minimum evidence | Status | Current finding / fallback |
| --- | --- | --- | --- | --- |
| Inbound telephone call | Twilio Programmable Voice | A consented India tester can call the configured number and reach a signed webhook | FEASIBILITY DEPENDENCY | Twilio states it has no voice-enabled numbers in India. Test a permitted international Twilio number that India callers can reach; do not promise a local `+91` AI number. [Twilio India voice pricing](https://www.twilio.com/en-us/sip-trunking/pricing/np) |
| Bidirectional call audio | Twilio Media Streams | One live call has isolated audio in/out over WSS | RESEARCHED | Twilio supports one bidirectional stream per call. Exact account/region path must be tested. |
| Human transfer | Twilio call control | Caller reaches configured fallback, including answer/busy/no-answer result | FEASIBILITY DEPENDENCY | Required for final demo. Verify an international-Twilio-number-to-India-reception transfer with the actual account/number. |
| Primary webhook failure fallback | Twilio/provider-hosted route | With main API unavailable, call reaches known reception route | PENDING | Must not depend on the unavailable API/database. |
| Speech-to-text | OpenAI realtime transcription | English, Hindi and Hinglish test audio yields usable final turns and latency | RESEARCHED | Available API path supports realtime transcription. Select a model after account checks and quality samples. |
| Text model | OpenAI | Typed extraction and response calls succeed within rate/cost budget | PENDING | Do not choose model/version from old examples; test actual account model access. |
| Text-to-speech | OpenAI | English/Hindi speech is intelligible after the telephony codec conversion | RESEARCHED | AI-voice disclosure is required. Audio conversion/streaming must be proven with the selected model. |
| WhatsApp delivery | Twilio WhatsApp | Consented India recipient receives a labelled booking message | FEASIBILITY DEPENDENCY | Required for first demo. Sandbox or approved sender/template route and account access must be tested. Twilio documents two-way WhatsApp capability between a Twilio WhatsApp number and recipients in other countries. [Twilio help](https://help.twilio.com/articles/4402930732059-Does-my-Twilio-WhatsApp-number-need-to-be-in-the-same-country-as-my-recipients-) |
| Returning-caller verification | Supported SMS or WhatsApp verification delivery, mechanism unselected | Challenge reaches saved contact, expires, rejects replay/guessing and cannot be redirected by caller | PENDING | Ordinary booking-message eligibility is insufficient evidence. No silent caller-ID-only fallback; transfer to reception if verification unavailable. |
| Payment | Local mock provider | Authorized operator can simulate success/failure/expiry without money movement | NOT_STARTED | No external account needed. Built in Phase 5, not part of G0. |
| Database/auth | Supabase PostgreSQL/Auth | New project access or owner-run migration workflow confirmed | PENDING | Owner may grant access later or run supplied SQL manually. SQL starts in Phase 1. |
| Hosting | Unselected | WSS duration, secrets, health checks, worker process and region/cost verified | PENDING | No vendor selected or account created. |

## Proposed feasibility sequence

1. Confirm D01–D05 and D09–D11 in the decision log.
2. Confirm whether Twilio, OpenAI, Supabase and WhatsApp access already exists. Do not share credentials in the repository.
3. With authorized credentials/test endpoints, run a narrow audio/telephony spike and capture only non-sensitive evidence: call ID redaction, stage timings, codec, model names, result and error code.
4. Decide whether WhatsApp is in the initial demonstration based on sender readiness.
5. Select a hosting option after the WebSocket/worker requirements and likely geography are known.

## G0 blocking conditions

- No verified India-caller → international Twilio number route and international-Twilio-number → human fallback route.
- No OpenAI account access for at least one STT, text and TTS candidate.
- No decision on using WhatsApp now versus deferring it.
- No verified delivery mechanism for the newly scoped returning-caller verification flow. Deferring appointment WhatsApp messages does not remove this dependency; choose another supported channel or explicitly revise returning-caller scope.
- No selected timezone and first-session configuration.
- Any required provider capability exists only in assumptions, not test evidence.
