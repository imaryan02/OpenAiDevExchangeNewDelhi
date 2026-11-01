# Gate G0 acceptance record

Gate status: `OPEN`.

G0 closes only when every required item is verified or intentionally removed from the current prototype with the PRD/decision-log update that documents the change.

| Check | Required evidence | Current status |
| --- | --- | --- |
| Operating contract | India/`Asia/Kolkata`, INR and 4–6 PM/capacity-30 token baseline recorded; remaining doctor/location/days/fee/arrival details supplied or deferred | PARTIAL |
| Language plan | English/Hindi/Hinglish fixture/speaker plan identified | OPEN |
| Synthetic-data rule | No real patient data is planned for seeds/evaluation | READY |
| Inbound voice feasibility | India caller → permitted international Twilio number → signed webhook evidence, or documented block and approved alternative | OPEN |
| Voice loop feasibility | Audio in → STT → safe text response → TTS audio out proven once, after credential authorization | OPEN |
| Human handoff feasibility | Controlled fallback number and a completed answer/busy/no-answer test plan | OPEN |
| Account entitlement | OpenAI confirmed; owner-run Supabase migration workflow confirmed; Twilio account/number and WhatsApp sender remain dependencies | PARTIAL |
| Returning-caller verification feasibility | Supported saved-contact delivery mechanism identified/tested; no caller-selected destination or phone-only access downgrade | OPEN |
| Contact/patient scope | Separate contact name/phone, distinct family patient profiles, per-booking permissions and atomic reschedule specified | READY |
| Cost and limits | Test budget TBD; initial five-call admission test plan exists | PARTIAL |
| Deployment constraints | Hosting/WSS/worker evaluation criteria selected | OPEN |
| Scope integrity | Local payment simulation remains current scope; no real payment provider on critical path | READY |

## Evidence format

For each completed item add a dated entry below with: decision/check ID, tester, environment, non-sensitive result, link/path to test evidence, limitation and next action. Never paste credentials, complete phone numbers, raw audio or patient data.

### Evidence entries

No evidence recorded yet.

The execution procedure for each evidence item is in `PROVIDER_TEST_PROTOCOL.md`.

## Product-owner response template

Copy this template into the chat and fill only the values you know. Use `TBD` for anything unavailable; do not include credentials, full patient phone numbers or private API keys.

```text
Demo country / city / timezone:
Target demo date:
External-services test budget:

Supabase: existing project / I will run SQL manually / access will be granted later
OpenAI account: available / not yet available
Twilio account: available / not yet available
WhatsApp for first demo: required / defer

AI telephone number: available / not yet available
Fallback receptionist number: available / not yet available

Token-session doctor, location and days:
Token-session time window, capacity and arrival note:
Exact-time doctor, location and days:
Exact-time slot duration:
Fee display and currency:
```

## What follows each response

| Input | Immediate Phase 0 work |
| --- | --- |
| Country/timezone and schedule | Finalize synthetic demo settings and date/time test cases |
| Supabase approach | Prepare the Phase 1 migration execution workflow around owner-run SQL or granted access |
| OpenAI/Twilio access | Run only the authorized feasibility check; no credentials are stored in this repository |
| WhatsApp choice | Keep message delivery in G0 or explicitly defer it from the initial demonstration |
| Phone/fallback availability | Test the actual telephone route and human handoff before building the voice layer |
