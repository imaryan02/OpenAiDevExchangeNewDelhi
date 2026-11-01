# Phase 0 provider test protocol

This is a test plan, not a provisioning instruction. Execute only after the owner has access to the relevant account and has approved the associated billable test. Never commit credentials, full caller numbers, raw audio, authentication codes or patient data.

## Evidence format

For each test record: date, environment, tester label, redacted provider/call/message identifier, result, latency, limitation and next action. Add the result to `G0_ACCEPTANCE.md`.

## T01 — India inbound telephone reachability

Goal: prove a consented India tester can call a selected international Twilio number.

1. Choose a Twilio voice-enabled number from a locale available to the account.
2. Configure a temporary signed HTTPS webhook that returns a short non-sensitive greeting.
3. Call it from one consented India mobile number.
4. Record: call connects/does not connect, displayed caller ID format, webhook arrival, audio quality and carrier/provider error code if any.
5. Repeat once from a different India carrier if available.

Pass: both a telephone connection and trusted webhook delivery occur. A number merely being purchasable does not pass.

## T02 — Human fallback transfer

Goal: prove the live caller can reach a configured human destination.

1. Use the T01 number and a consented fallback phone.
2. Invoke an application/provider-controlled transfer to that destination.
3. Exercise answered, busy/rejected and no-answer outcomes.
4. Verify the caller does not remain trapped in the AI stream and that the call outcome is recorded safely.

Pass: answered transfer reaches the fallback; non-answer outcomes have an accurate caller message and no false “transfer completed” status.

## T03 — OpenAI bilingual speech loop

Goal: select a usable STT/TTS configuration for actual India telephone audio.

1. Use synthetic English, Hindi and Hinglish speech with local doctor names, dates, 4–6 PM session and tokens.
2. Test final transcript correctness for patient/doctor names, date, time and token phrases.
3. Generate a short bilingual answer and convert/play it through the selected telephone audio path.
4. Record final-turn latency, pronunciation/clarity and any codec conversion requirement.

Pass: all three language sets are intelligible, the tested phrases are usable for booking flow, and measured latency fits the PRD target. Model selection is deferred if this test fails.

## T04 — WhatsApp delivery and verification challenge

Goal: prove a India recipient can receive both a labelled booking notification and a short-lived verification challenge using the selected Twilio/Meta path.

1. Complete the required sandbox enrollment or approved sender/template configuration for consented test recipients.
2. Send a minimal synthetic booking message.
3. Send a synthetic verification challenge to the saved recipient only.
4. Test successful code, expired code, reused code, incorrect code, resend cooldown and rate limit.
5. Verify that a caller cannot select a different destination and that raw codes do not appear in logs/records.

Pass: the recipient receives both messages, the challenge behavior matches policy, and failed verification routes to reception without revealing appointments.

## T05 — Initial simultaneous-call baseline

Goal: establish only the first tested capacity claim.

Run after T01–T03 with real voice implementation available. Exercise one, then three, then five simultaneous consented calls for 30 minutes. Record stage latency, Twilio/OpenAI errors, CPU/RAM, active WebSockets, database wait/locks, audio queues and state isolation. Publish the highest passing tier only.

Pass: five concurrent calls meet the PRD voice and booking targets with no cross-call data/audio mixing. If only one or three pass, that lower value is the declared current capacity.

