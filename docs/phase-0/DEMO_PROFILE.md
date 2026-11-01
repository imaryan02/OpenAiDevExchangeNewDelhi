# Initial synthetic demo profile

Status: `PARTIALLY_CONFIRMED` · Source: product-owner input, 10 September 2026.

| Setting | Value | Status |
| --- | --- | --- |
| Organization | Geeta Medicine | CONFIRMED |
| Data | Synthetic patient/appointment data only | CONFIRMED |
| Country / city | India | CONFIRMED |
| Organization timezone | `Asia/Kolkata` | CONFIRMED |
| Currency | INR | CONFIRMED |
| Languages | English, Hindi and Hinglish | CONFIRMED |
| Booking modes | Exact time and session/token | CONFIRMED |
| Initial token window | 4:00 PM–6:00 PM | CONFIRMED |
| Initial token capacity | 30 | CONFIRMED |
| Token arrival note | To be supplied | OPEN |
| Token doctor / location / days | To be supplied | OPEN |
| Exact-time doctor / location / days / duration | To be supplied | OPEN |
| Fee display | INR currency selected; amount to be supplied | OPEN |
| Payment | Local simulator only; no money collection | CONFIRMED |
| Supabase execution | Owner runs supplied SQL manually | CONFIRMED |
| OpenAI account | Available | CONFIRMED |
| VoiceLink account / Indian DID | Active for prototype testing | CONFIRMED |
| Fallback reception number | To be supplied | FEASIBILITY DEPENDENCY |
| WhatsApp | Required for first demo; sender/account path pending | FEASIBILITY DEPENDENCY |
| Demo date / test budget | To be supplied | OPEN |

## Time rules

All generated appointment times, conversational dates and queue sessions use `Asia/Kolkata`. Store UTC instants in the database alongside this organization/location timezone. Never use the developer computer's timezone.

## Telephony consequence

The prototype uses the assigned Indian VoiceLink DID and routes bidirectional audio to the backend WebSocket gateway. Production readiness still requires repeatable inbound-call, audio, fallback, and concurrency tests.

## Synthetic starter example

This is a planning fixture only; it is not a database seed yet.

```text
Organization: Geeta Medicine
Timezone: Asia/Kolkata
Token session: 4:00 PM–6:00 PM, capacity 30
Contact: Aryan, saved phone = synthetic test number
Patients: Aryan, Aryan's Mother, Aryan's Father
```
