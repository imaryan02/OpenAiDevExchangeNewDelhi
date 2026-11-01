# Phase 0 decision log

Status key: `OPEN` · `PROPOSED` · `CONFIRMED` · `SUPERSEDED`.

The D01–D16 identifiers in this local checklist predate the PRD decision-table alignment and are local to this file; use decision titles when comparing with the PRD. The scope additions below reference PRD D19–D21 explicitly.

| ID | Decision | Current value | Status | Owner | Evidence needed before close |
| --- | --- | --- | --- | --- | --- |
| D01 | Demo country and primary organization timezone | India / `Asia/Kolkata` | CONFIRMED | Product owner | Recorded in `DEMO_PROFILE.md` |
| D02 | Demo date and engineering availability | TBD | OPEN | Product owner | Target date and approximate weekly hours |
| D03 | Billable test/demo budget | TBD | OPEN | Product owner | Total and daily limit for Twilio/OpenAI/hosting tests |
| D04 | AI number, caller reachability and reception fallback | No number yet; fallback TBD | FEASIBILITY DEPENDENCY | Product owner + engineer | Account, reachable international/demo number, tester route and fallback destination |
| D05 | WhatsApp delivery route | Required for first demo; sender/account route pending | FEASIBILITY DEPENDENCY | Product owner + engineer | Sender/sandbox readiness and enrolled-recipient policy |
| D06 | Spoken languages | English, Hindi and Hinglish; switching allowed | CONFIRMED | Product owner | Test speakers/fixtures representing all three |
| D07 | Payment behavior | Local simulated success/failure/expiry; no money collection | CONFIRMED | Product owner | Demo-mode authorization design in Phase 5 |
| D08 | Booking behavior | Support exact-time and session/token modes | CONFIRMED | Product owner | Phase 2 invariants and tests |
| D09 | First token-session configuration | Geeta Medicine, 4–6 PM, maximum 30; doctor/location/days/arrival note TBD | PARTIALLY_CONFIRMED | Product owner | Doctor, location, days, arrival note and fee display |
| D10 | Token policy | Allocate only at confirmation; never reuse or renumber; staff queue follows checked-in order | PROPOSED | Product owner | Confirm clinic workflow acceptance |
| D11 | Exact-time configuration | Proposed: separate doctor session with 10-minute slots | PROPOSED | Product owner | Confirm doctor/session days and location |
| D12 | Clinic/hospital onboarding | Create Clinic and Create Hospital use one shared multi-tenant schema | CONFIRMED | Product owner | Phase 4 UI acceptance |
| D13 | Clinical routing and urgent-risk scripts | Administrative routing only; copy must be reviewed before real patient use | OPEN | Product owner + clinic reviewer | Approved synthetic-demo script and future reviewer |
| D14 | Provider model versions | OpenAI account available; select after English/Hindi quality and latency checks | PARTIALLY_CONFIRMED | Engineer | Phase 0 measurement record |
| D15 | Hosting topology/region | Always-on WebSocket-capable API process plus worker; selection pending | OPEN | Product owner + engineer | Chosen vendor/region/cost evidence |
| D16 | Real patient data/use | Out of scope for this prototype | CONFIRMED | Product owner | Synthetic-data seed policy |

## Revision 1.2 scope additions

| PRD decision | Baseline | Status / remaining evidence |
| --- | --- | --- |
| D19 — Contact/patient model | Aryan's contact name and saved phone are separate from mother/father patient names; per-booking permissions | CONFIRMED scope; schema implementation in Phase 2 |
| D20 — Returning-caller verification | Automatic private phone matching; saved-contact challenge before existing details/changes; no OTP for public questions/new-record creation | Policy baseline; actual SMS/WhatsApp code-delivery mechanism OPEN in G0 |
| D21 — Cancel/reschedule | Eligible bookings can be changed by verified permitted caller; explicit confirmation; atomic replacement preserves original on failure | Scope included; proposed 30-minute cutoff/unchanged-fee policy to review in Phase 2 |

## Product-owner inputs needed to complete the decision sheet

Provide these as ordinary text; do not send secrets in chat.

1. The country, city and timezone for Geeta Medicine.
2. The target demo date and a rough budget for external testing.
3. The first exact-time doctor/session and first token-session doctor/session: location, days, duration, fee display, capacity and arrival note.
4. Whether a reachable fallback receptionist/test number and a few consented caller/WhatsApp tester numbers are available.
5. Whether the demo should include WhatsApp now, or show in-dashboard notification status only until a sender is available.
