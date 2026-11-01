# AI Voice Receptionist — Product Requirements and Delivery Plan

Version: 1.2 · Date: 10 September 2026 · Status: Phase 0 in progress; revised product baseline

Revision 1.1 incorporates the requested clinic/hospital onboarding, manual operations, English/Hindi speech, configurable exact-time versus session/token booking, explicit capacity validation, and simulated payments. Real payment-provider integration is deferred. All application features, evaluations and guardrails remain **planned, not implemented**.

Revision 1.2 separates contact identity/name/phone from patient identity; adds returning-caller verification, booking-scoped family access, and AI cancellation/rescheduling. Phone matching recognizes a contact but never silently grants access. Phase 0 is the only active phase; no application or SQL implementation has begun.

Product owner: Aryan Gupta. Initial demonstration organization: Geeta Medicine, using synthetic data.

**Authorization boundary:** The product owner has authorized development one phase at a time. Phase 0 is active. This revision updates planning within that phase; later phases remain unopened until their entry conditions are met. Account purchases, production deployment and real patient use are not implied. Record evidence rather than declaring completion from code alone.

## Contents

1. Product outcome and boundaries
2. Users and journeys
3. Requirements and acceptance criteria
4. Architecture and implementation decisions
5. Data model and scheduling rules
6. Booking, payments, and reliable delivery
7. Conversation workflow and voice behavior
8. Dashboard and operations experience
9. Security, privacy, and healthcare boundaries
10. Quality targets, measurement, and evaluations
11. Environments, deployment, and recovery
12. Phases and subphases
13. Execution rules, estimates, and dependencies
14. Risk register and open decisions
15. Final acceptance and demonstration
16. Official references

## 1. Product outcome and boundaries

### 1.1 What we are building

A multi-tenant appointment platform with an AI telephone receptionist. Patients speak English, Hindi or Hinglish, receive administrative help or department routing, choose an exact-time appointment or a place in a capacity-limited doctor session, and confirm the booking details. Clinic staff manage the same records manually and can take over a call. Payments are simulated in the current prototype; a real payment integration is a later release.

The central product promise is: **a natural conversation produces a correct, traceable appointment, with a safe human exit when automation cannot finish.**

The AI is a channel into the booking system. It does not own availability, authorization, prices, payment truth, or clinical decisions. Those are controlled by the application and database.

### 1.2 What “enterprise prototype” means

The prototype must demonstrate real tenant separation, authenticated staff access, concurrent booking correctness, recoverable external integrations, auditability, and measurable AI behavior. It must run end to end against actual voice and messaging providers, with an explicitly labelled local payment simulator that moves no money.

It is not a claim of production certification, unlimited scale, contractual uptime, clinical validation, or readiness to process real patient data. Production readiness is a separate gate, not an implication of a polished demo.

| Area | Required for this prototype | Deferred until justified |
| --- | --- | --- |
| Tenancy | Two isolated seeded tenants; configurable organizations | Automated enterprise provisioning and tenant migrations |
| Booking | Exact-time slots OR capacity-limited session/token booking; real transactions; staff bookings and walk-ins | Waitlists, recurring bookings, room/resource scheduling |
| Voice | Real inbound call; Hindi/Hinglish and English evaluation; interruptions | Many languages, outbound campaigns, voice biometrics |
| Payment | Local simulator with success/failure/expiry controls; no actual collection | Razorpay integration including Test Mode, live charging, refunds and settlement reconciliation |
| Messaging | Real delivery to approved demo recipients, using permitted sandbox or sender flow | Automated SaaS customer WhatsApp onboarding |
| Access | Supabase Auth; staff roles; enforced tenant scope | Enterprise SSO, SCIM, custom role designer |
| Reliability | Durable jobs, retries, fallback, restart tests | Active-active regions, Kubernetes, formal SLA |
| Healthcare | Administrative routing; reviewed escalation copy | Diagnosis, prescribing, treatment recommendations |

### 1.3 Explicit non-goals

- DoctorsHub website builder, EMR/EHR, prescriptions, lab results, insurance processing, pharmacy, inpatient beds, and clinical records.
- RAG or vector search for transactional availability. Administrative facts come from curated structured tenant configuration.
- Autonomous medical triage or guarantees that every emergency can be detected.
- Changes to real-paid bookings that require refunds or fee adjustments; these route to staff until the deferred payment integration exists. AI cancellation/rescheduling of eligible simulated/pay-at-clinic bookings is included after verification and explicit confirmation.
- Native mobile applications, patient accounts, marketplace doctor search, and self-service commercial SaaS subscriptions.
- Automated provisioning of phone numbers or production payment/WhatsApp accounts.

### 1.4 Proposed operating defaults

These are planning decisions, not facts about the clinic. Record amendments in the decision log before the dependent phase.

| Decision | Baseline |
| --- | --- |
| Demo data | Synthetic patients and illustrative clinician profiles, clearly labelled |
| Tenant count | Geeta Medicine plus a second synthetic clinic for isolation tests |
| Geography/timezone | India, `Asia/Kolkata`; use IANA timezone per organization/location; never infer it from the developer machine |
| Languages | Spoken English and Hindi are P0, including Hinglish and mid-call switching; unsupported language routes to staff |
| Booking model | Configurable per doctor session: `EXACT_TIME` or `SESSION_TOKEN`; default proposal for OPD demo is `SESSION_TOKEN` |
| Patient capacity | Positive integer per token session, e.g. 30 during 4–6 PM; exact-time capacity derives from generated slots |
| Appointment identity | Unique booking reference for every booking; session token on confirmation for `SESSION_TOKEN` |
| Booking window | Next 30 local calendar days; configurable |
| Minimum lead time | 30 minutes; configurable |
| Payment | `SIMULATED` default: labelled demo payment success/failure; optional `PAY_AT_CLINIC`; no Razorpay account required now |
| Hold lifetime | 10 minutes from database reservation; configurable within a bounded range |
| Booking consent | Explicit affirmative response to doctor, location, date, time, patient, fee and expiry summary |
| Returning caller | Automatically recognize incoming phone privately; verify saved contact once per call before reading/changing existing bookings |
| Family booking | Separate contact and patient names; booking-scoped permissions, never automatic family-history access |
| Staff payment exception | Explicit pay-at-clinic or authorized waiver with reason; never an arbitrary “paid” toggle |
| Call ceiling | 10 minutes with a courteous warning and human/callback option |
| Capacity target | Initially validate 5 concurrent live calls, then benchmark 10 and 20 within approved budget; separately test booking contenders against slots/session capacity |
| Audio recording | Off by default; no retained raw audio |
| Prototype transcript retention | Off by default; opt-in synthetic evaluation transcripts expire after 7 days |

## 2. Users and journeys

### 2.1 Personas and responsibilities

| Persona | Needs | Allowed responsibilities |
| --- | --- | --- |
| Patient/caregiver | Book naturally, understand fees, avoid repetition, get human help | Provide details, select/confirm offer, request transfer |
| Receptionist | See accurate schedule, book manually, recover failed journeys | Tenant appointments, minimum necessary patient details, authorized cancellation, exception queue |
| Organization admin | Configure their clinic and staff | Locations, departments, doctor assignments, schedules, policies, endpoint setup status |
| Platform operator | Operate demo integrations and resolve incidents | Provision configuration and view operational health; sensitive tenant access is explicit and audited |

No separate doctor portal in V1. Staff membership is independent of a doctor's directory entry.

### 2.2 Primary journeys

1. **Fast booking:** Caller gives doctor and time → resolve doctor and local date → retrieve the doctor's booking mode and availability → identify patient → summarize exact time OR session window/capacity policy → obtain consent → reserve → simulated payment success confirms, or permitted pay-at-clinic confirms directly → issue booking reference/token → dashboard and message update.
2. **Guided booking:** Caller names a department or lay term → resolve against clinic-approved routing taxonomy → clarify if ambiguous → offer relevant available doctors → continue booking.
3. **Discovery:** Caller requests a doctor for a family member → ask one short routing question → use approved routing options without diagnosis → offer selection or transfer if uncertain.
4. **Information:** Answer configured hours, location, fees or supported departments, citing current tool data internally; do not fabricate missing facts.
5. **Correction:** Caller changes doctor/date/time/name → invalidate dependent choices and prior consent → retrieve fresh options → reconfirm. Explicitly release/replace an existing hold; old simulated outcomes cannot confirm it. Payment-link handling is deferred with the real provider.
6. **Human request:** Stop AI flow → transfer to configured reception line → record dial outcome → create callback request only with consent if no one answers.
7. **Staff booking:** Authenticated receptionist chooses patient, assignment, exact slot OR token session and permitted payment policy → same service/capacity rules as AI. Walk-ins consume the same inventory. Staff can check in, call, complete, skip and cancel tokens through controlled actions.
8. **Failure recovery:** Simulated payment failure/expiry, full session, no slots, messaging/voice outage or disconnection → preserve truthful state and give the applicable human or retry path.
9. **Returning caller:** Resolve tenant and recognize number privately → ask the caller's intent → verify saved contact once when existing details are requested → fetch only authorized upcoming bookings → clarify which patient/appointment if necessary.
10. **Family booking:** Record the contact's own name separately from the patient's name; allow several new family bookings without modifying prior bookings or inferring ownership of matching patient records.
11. **Cancel/reschedule:** Verify saved contact and booking permission → identify eligible appointment → offer actual alternatives for reschedule → read back the proposed change → get explicit confirmation → perform idempotent transaction → notify. If reschedule fails, original booking remains valid.

### 2.3 Example conversation contract

Caller: “Dr Amit ka kal paanch baje appointment chahiye.”

Agent resolves “tomorrow” in the clinic timezone. If AM/PM is unclear, it asks or offers an actual matching evening slot; it does not silently assume. If there are two Dr Amits, it clarifies before booking.

Exact-time example: “Dr Amit at the Main Road clinic, tomorrow [spoken date] at 5 PM. Shall I reserve this for [patient name]? Payment in this demonstration is simulated.”

Session example: “Dr Amit's session is tomorrow [spoken date], 4 to 6 PM. This is a token-based appointment, not an exact consultation time. Shall I book this for [patient name]?” After confirmation: “Your booking is confirmed for the 4 to 6 PM session. Your token is 10.” Provide clinic-configured arrival instructions; do not translate token 10 into an invented consultation time.

Only after a clear affirmative response does the service reserve capacity. In simulated-payment mode it reports **held pending demo confirmation** and expiry until the authenticated simulator records success. In pay-at-clinic mode it may confirm directly through the authorized service. It says **confirmed** and announces a token only after the database commits that state. Simulation never records an actual paid amount or claims real money was received.

Caller phone and patient are distinct: a mother and child may share a contact number. Phone matching must not expose existing patient names or appointments to an unverified caller.

## 3. Requirements and acceptance criteria

Priority P0 means required for final acceptance. P1 means optional after every P0 gate passes. Requirement IDs remain stable across implementation and tests.

| ID | Priority | Requirement | Acceptance evidence |
| --- | --- | --- | --- |
| TEN-01 | P0 | Resolve tenant from authenticated membership or verified call endpoint | Cross-tenant endpoint, API, DB, worker and agent tests deny access |
| TEN-02 | P0 | Configure clinic name, timezone, endpoints, fallback and policies | Two tenants use different greetings, schedules and settings without agent code changes |
| IAM-01 | P0 | Authenticate staff and enforce roles server-side | Expired token, removed membership and forbidden role actions fail |
| DOC-01 | P0 | Support doctors working at several organizations/locations through assignments | Shared clinician has separate scoped schedules, fees and directory visibility |
| SCH-01 | P0 | Generate valid sessions and exact-time slots from schedules and exceptions | Leave, timezone, breaks, duplicates and boundary tests pass in both modes |
| SCH-02 | P0 | Respect exact-slot exclusivity, session capacity and doctor scheduling | AI versus staff contention produces one winner for a last available place |
| QUE-01 | P0 | Enforce shared session capacity and stable token allocation | Capacity 30 never admits 31 active reservations; token uniqueness and cancellation/replay tests pass |
| QUE-02 | P0 | Operate a manual queue with walk-ins/check-in/call/skip/completion | Staff changes preserve history and do not renumber existing patients |
| ONB-01 | P0 | Offer Create Clinic and Create Hospital with appropriate setup defaults | Both organization types reach activation through one scoped data model |
| LNG-01 | P0 | Understand and speak English and Hindi, including Hinglish | Each language meets acceptance thresholds separately; mid-call switching preserves booking state |
| PAT-01 | P0 | Create/select the correct patient with minimal information | Shared phone does not force merge or reveal another patient's records |
| PAT-02 | P0 | Separate contact name/phone, patient identity and booking permissions | Aryan's contact manages distinct mother/father appointments without replacing patient names or exposing unrelated bookings |
| RET-01 | P0 | Recognize returning contacts and verify before existing-record disclosure | Matching/hidden/spoofed numbers, expired/replayed codes and revoked grants cannot bypass verification |
| RET-02 | P0 | Answer authorized upcoming-booking queries and resend permitted confirmations | Correct patient/date/token returned; no access based solely on relationship or phone match |
| CHG-01 | P0 | Cancel/reschedule eligible bookings after verification and explicit confirmation | Last-place race preserves original booking; replay produces one change/token; unauthorized/out-of-policy changes fail |
| AGT-01 | P0 | Support fast, guided and discovery paths | Fixed evaluation set meets targets in Section 10 |
| AGT-02 | P0 | Preserve known fields; handle corrections and ambiguity | No stale doctor/date/slot mutation after a correction |
| AGT-03 | P0 | Restrict model actions to typed tools and allowed workflow | Injection and forged IDs cannot bypass authorization or payment rules |
| BKG-01 | P0 | Require consent and create expiring holds transactionally | Consent snapshot, immutable quoted fee and expiry appear in record |
| BKG-02 | P0 | Make mutating requests idempotent | Replay produces the same result without extra booking or charge attempt |
| SIM-01 | P0 | Use explicit, restricted payment simulation with no real collection | Demo success/failure/expiry/replay tests pass; UI/messages say simulated; no payment credentials required |
| PAY-01 | Deferred | Real payment confirmation requires verified settlement evidence or authorized staff policy | Future provider gate: forged, duplicate, mismatched and reordered callbacks never falsely confirm |
| PAY-02 | Deferred | Handle real late payment and provider uncertainty | Future provider gate: late payment creates review exception without taking occupied capacity |
| MSG-01 | P0 | Deliver link and confirmation with consent and observable status | Real approved recipient receives messages; failures appear in staff queue |
| VOI-01 | P0 | Receive/send real telephone audio through provider adapters | External phone completes conversation with intelligible audio |
| VOI-02 | P0 | Support barge-in and stale-response cancellation | Interrupted speech stops and old tool result cannot trigger stale speech/booking |
| HUM-01 | P0 | Transfer by request, repeated misunderstanding or operational failure | Dial answer/busy/no-answer/error and app outage are demonstrated |
| UI-01 | P0 | Support onboarding, schedule management and manual booking | Staff completes tasks through UI without database edits |
| UI-02 | P0 | Expose booking, payment, delivery and transfer exceptions | Staff can distinguish pending, failed, unknown and confirmed states |
| SEC-01 | P0 | Protect secrets, tenant data and provider ingress | Threat tests and secret scans pass; sensitive logs are redacted |
| SAFE-01 | P0 | Enforce administrative-only scope and reviewed emergency response | No diagnosis/treatment or invented emergency number in evaluation set |
| OPS-01 | P0 | Recover durable work after restart | Hold expiry, webhook processing and outbox retries recover in fault tests |
| OBS-01 | P0 | Trace outcomes, latency and estimated cost | Each demo call has correlated events and measurable stage timings |
| DEM-01 | P0 | Deploy and reproduce the demonstration | Fresh environment setup and reset runbook work with synthetic data |
| EXT-01 | P1 | Add FAQ retrieval, extra languages or deeper analytics | Requires separate requirements and evaluation; never blocks P0 |

## 4. Architecture and implementation decisions

### 4.1 Components

```text
Patient phone -> Twilio voice -> FastAPI voice gateway
                                  | audio
                                  v
                           STT provider adapter
                                  | finalized utterance
                                  v
                        LangGraph conversation workflow
                           | LangChain / OpenAI
                           | typed understanding and tools
                                  v
Staff -> React -> FastAPI -> shared application services
                                  |
                                  v
                     Supabase PostgreSQL + Supabase Auth
                       |             |              |
                 booking truth   graph state    inbox/outbox/jobs
                                                     |
                                               durable worker
                                               /            \
                                     Mock payments       WhatsApp

Workflow response -> TTS adapter -> codec/frame adapter -> Twilio -> caller
Verified provider callbacks -> FastAPI -> inbox -> worker -> transaction
Transfer controller -> Twilio call control -> reception phone
Independent fallback endpoint -> validated reception route
```

### 4.2 Technology baseline

| Layer | Choice | Decision rationale |
| --- | --- | --- |
| Web | React, TypeScript, Tailwind, Vite | Focused staff application with typed client contracts |
| API | FastAPI, Pydantic | Shared validation and business boundary |
| Persistence | Supabase PostgreSQL; SQLAlchemy 2 async; Alembic | Explicit transactions, constraints and versioned schema |
| Authentication | Supabase Auth | Staff identity; application manages tenant memberships |
| Workflow | LangGraph with PostgreSQL checkpoints | Explicit state transitions and durable session state |
| Model integration | LangChain OpenAI integration and structured output | Small typed understanding calls and controlled tool wrappers |
| Voice | Twilio bidirectional Media Streams; OpenAI STT and TTS adapters | Keep conversation control in application |
| Payments | Local `MockPaymentProvider` behind payment interface | Exercise booking lifecycle without provider onboarding or money movement; Razorpay later |
| Messaging | Twilio WhatsApp adapter | Sandbox or approved sender for designated demo recipients |
| Background work | PostgreSQL inbox/outbox/jobs plus Python worker | Durable work without adding Redis/Celery for this scale |
| Observability | Structured logs, metrics and audit events | Required from first vertical slice; LangSmith optional later |
| Packaging | One repository, API/worker containers and web build | Modular monolith suitable for a small team |

Version-pin dependencies during Phase 1 after testing compatibility. Do not select model IDs from a stale example; configure STT, LLM and TTS independently after account and language tests. Reasoning settings apply only to models that support them.

### 4.3 Architectural rules

1. FastAPI routes, voice tools and workers call shared application services. An in-process agent tool need not make a redundant HTTP call back into the same server.
2. The LLM proposes interpretation and permitted actions. LangGraph determines the next allowed step. Application services verify business rules; PostgreSQL guarantees invariants.
3. Tenant context is injected by trusted code, never accepted as an LLM-selected organization ID. All state, cache keys, checkpoints, jobs and audit events carry tenant identity.
4. React uses Supabase Auth for login and FastAPI for business data. No direct browser booking mutations. If direct database realtime is introduced later, it requires its own authorization tests.
5. Use an application database role without RLS bypass. Apply transaction-local tenant context and scope every repository query. Separate privileged migration/maintenance credentials from runtime credentials. Supabase service-role access can bypass RLS, so it is not the baseline runtime authorization mechanism. [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security)
6. Outbound requests never run inside a long-lived booking lock. Commit local intent first, perform provider work outside that transaction, then reconcile the result.
7. External delivery is at-least-once. Implement deduplication and reconciliation rather than claiming exactly-once network execution.
8. No tools for arbitrary SQL, arbitrary URLs, arbitrary code, configurable payment amounts supplied by callers, or transfer to caller-provided numbers.
9. Keep voice sessions on a long-lived WebSocket-capable process. Avoid a request-only/serverless deployment for the voice gateway.
10. Do not introduce microservices, a vector database, multiple LLM vendors, or a queue platform without a documented requirement.

### 4.4 Provider boundaries

Define interfaces around required behaviors, not just `transcribe()` and `speak()`:

- STT: open session, audio format negotiation, append audio, speech-start/end events, partial/final transcripts, utterance IDs, timeout and close.
- TTS: stream speech chunks, declare audio format, cancellation and error behavior.
- Telephony: verify request, parse call identity, stream audio, clear playback, acknowledge marks, redirect/dial, process status callback.
- Payments: current local simulator creates an attempt and controlled outcome; future provider implements create/get/cancel link, verified callback and status reconciliation behind the same interface. Do not implement the Razorpay adapter in the current phases.
- Messaging: render approved template, send, fetch/capture status, correlate delivery receipt.

Use provider fakes for deterministic tests and real adapters for acceptance. Clearly label simulated runs; a fake call does not satisfy live telephony acceptance.

### 4.5 Proposed repository layout

```text
apps/web/                         staff dashboard
apps/api/app/api/                 HTTP and webhook routes
apps/api/app/voice/               streaming and call control
apps/api/app/agent/               graph, state, policies, tool wrappers
apps/api/app/domain/              booking and scheduling rules
apps/api/app/services/            application operations
apps/api/app/repositories/        scoped persistence
apps/api/app/providers/           OpenAI, Twilio, mock payment adapters; Razorpay later
apps/api/app/workers/             durable job processing
apps/api/app/core/                config, auth, telemetry, errors
apps/api/migrations/              schema and RLS changes
tests/unit/                      pure rules
tests/integration/               real PostgreSQL and API contracts
tests/e2e/                       staff browser journeys
evals/                           conversations, audio fixtures, scoring
docs/decisions/                  architecture decision records
docs/runbooks/                   deploy, reset, recovery, demo
infra/                          container and deployment configuration
```

This is a target layout, not created application scaffolding.

## 5. Data model and scheduling rules

### 5.1 Model conventions

- UUID primary keys; `created_at` and `updated_at` in UTC; integer minor currency units and explicit currency; never floating-point money.
- Business tables have non-null `organization_id`; composite foreign keys prevent cross-tenant relationships even when IDs are valid independently.
- Store appointment instants as `timestamptz`; keep the booking timezone and human-readable snapshot. Weekly rules use local weekday/time plus IANA timezone.
- Use version counters for conflict detection. Archive configurable entities instead of deleting referenced history. PII erasure is a separate audited workflow.
- No global patient identity. Store contact names and patient names separately. A phone belongs to a contact channel, not to a unique patient or proven legal identity.
- Snapshots preserve quoted doctor/location/fee/policy when later configuration changes.

### 5.2 Tables and ownership

| Table | Key fields/relationships | Rules |
| --- | --- | --- |
| organizations | name, type, timezone, status, policy_version | Draft/active/suspended; suspension blocks new bookings |
| locations | organization_id, name, address, timezone | Assignment location is explicit |
| departments | organization_id, name, active | Tenant-specific directory |
| department_routing_rules | department_id, aliases, reviewed routing copy, version | Curated administrative taxonomy; no diagnosis rules |
| doctors | id, canonical name, qualifications | Minimal platform directory; no patient data; platform-managed canonical updates |
| doctor_assignments | organization_id, doctor_id, department_id, location_id, display_name, fee_minor, currency, active | Tenant owns local presentation and commercial details |
| schedule_rules | organization_id, assignment_id, weekday, local start/end, booking_mode, slot_minutes OR max_patients, effective dates | Mode-specific validation; non-overlapping doctor sessions |
| schedule_exceptions | organization_id, assignment_id, local_date, type, intervals, reason | Closure or replacement hours override weekly rules |
| appointment_sessions | organization_id, assignment_id, starts_at, ends_at, booking_mode, max_patients, next_token, status, generation_version | Concrete dated session; token capacity/count and token allocation serialized under its row lock |
| appointment_slots | organization_id, session_id, assignment_id, starts_at, ends_at, bookable, generation_version | Only for exact-time mode; unique session/start; capacity one |
| contacts | organization_id, display_name, name_source, status | Contact/booker name, e.g. Aryan; not a patient profile or legal-identity claim |
| contact_phones | organization_id, contact_id, phone_e164, status, last_verified_at, version, messaging_consent | Unique active normalized phone per tenant in V1; phone changes are staff-controlled; historical verification is not current-call authentication |
| patients | organization_id, display_name, optional disambiguation, status | Separate profiles for Aryan, mother and father; no authoritative contact_phone column or name-only merge |
| patient_contacts | organization_id, patient_id, contact_id, relationship, recorded_by, relationship_status | Describes contact's relationship to patient; relationship alone grants no access |
| appointment_contact_permissions | organization_id, appointment_id, contact_id, can_view, can_manage, grant_source, granted_at, revoked_at | Explicit per-booking permissions; grants for existing bookings require authorized staff or established authorized workflow |
| verification_challenges | organization_id, call_id, contact_phone_id, phone_version, code_digest, expires_at, attempt_count, consumed_at, verified_until, status | Keyed digest, short TTL and bounded retries; verification grants nothing beyond active booking permissions |
| appointments | organization_id, patient_id, booked_by_contact_id, notification_contact_phone_id, contact_snapshot, assignment_id, session_id, optional slot_id, booking_reference, optional token_number, queue_status, status, hold_expires_at, source, version, quote_snapshot, consent_snapshot, supersedes_appointment_id | Exact mode requires slot; token mode forbids slot; explicit notification destination and reschedule history |
| payment_attempts | organization_id, appointment_id, provider, mode, optional merchant_config_id/link_id, reference, amount_minor, currency, status | Current provider is mock; `SIMULATED_SUCCESS` distinct from `PAID`; real-provider fields nullable |
| communication_endpoints | organization_id, provider_account_ref, channel, address, active | Inbound account/channel/address resolves exactly one tenant |
| voice_settings | organization_id, greeting, languages, fallback endpoint, office hours, script versions | No unrestricted prompt override or secret values |
| integration_configs | organization_id, provider, credential_reference, mode, status | Store references to secrets, never plaintext dashboard-readable keys |
| organization_users | organization_id, auth_user_id, role, active | Membership checked at request time |
| call_sessions | organization_id, provider_call_id, presented_phone, recognized_contact_id, verified_contact_phone_id, verification_expires_at, state, outcome, timestamps, config_version | Recognized and verified state distinct; minimal retained content; no implicit reuse across calls |
| agent_events | organization_id, call_id, turn_id, stage, tool, result_code, latency, model_version | Redacted operational evidence, not private reasoning |
| callback_requests | organization_id, call_id, contact, consent, reason, status | Staff-owned manual follow-up queue |
| webhook_inbox | provider, account_ref, event_id, organization_id, processing_status, encrypted/restricted payload, received_at | Deduplicate ingress and persist before acknowledgement |
| outbox_jobs | organization_id, type, aggregate_id, dedupe_key, payload, attempts, next_attempt_at, lease_until, status | Durable notifications, reconciliation and maintenance |
| message_deliveries | organization_id, appointment_id, provider_message_id, purpose, recipient, consent_ref, status | Sent is distinct from delivered/failed/unknown |
| audit_events | organization_id, actor_type/id, action, entity, safe change summary, correlation_id, occurred_at | Append-only for runtime users |
| idempotency_records | organization_id, actor_scope, operation, key, request_hash, response_ref | Same key/different body rejected |
| graph checkpoint tables | tenant-scoped thread ID and versioned state | Library storage secured separately; contains sensitive state |

The payment table is called `payment_attempts` to distinguish a provider attempt from the appointment's overall payment position. A view may expose “payments” in the dashboard.

### 5.2.1 Contact and patient separation

Example within Geeta Medicine:

```text
Contact C1: Aryan
  Contact phone CP1: Aryan's saved mobile
  Relationship -> Patient P1: Aryan       (self)
  Relationship -> Patient P2: mother's own name (contact is her son)
  Relationship -> Patient P3: father's own name (contact is his son)

Appointment A1 -> patient P2, booked_by C1, notification CP1
Appointment A2 -> patient P3, booked_by C1, notification CP1
Permissions -> C1 may view/manage A1 and A2
```

Aryan need not be a patient to act as contact for his parents. Ask “Your name?” and “Who is the appointment for?” as distinct fields. Never replace the patient's name when the contact says “I am Aryan.” Names do not have to be split into first/last name to achieve this separation.

V1 keeps one active contact owner per normalized phone per organization. A family sharing the number can use that administrative contact; this does not distinguish individual people holding the phone. Name conflicts, recycled numbers and contact transfers go to staff without overwriting records or revealing the previous owner. Multiple phone numbers may belong to one contact, but adding/changing a number requires a controlled staff workflow.

New anonymous bookings may create provisional contact/patient records and an appointment-specific booker permission, but cannot attach to or reveal an existing patient solely by matching a name or phone. Reuse of an existing profile requires verified access and permitted linkage; ambiguous duplicates are resolved by staff. A new booker permission covers only the booking just created, not the patient's earlier appointments. Adult family linkage to existing records requires recorded authorization; saying “my mother” alone is not an access grant.

Verification proves current access to the saved phone, not the speaker's legal identity. Bookings use explicit contact references/snapshots, so changes to general profile data cannot silently redirect verification or notifications. Disabling/reassigning a phone invalidates outstanding challenges and requires review of contact permissions.

### 5.3 Shared doctors without shared tenant data

A canonical doctor may have assignments in several clinics. Tenant users can read the minimal canonical profile only through their own assignment and edit only their assignment-specific details. They cannot enumerate another clinic's assignments or modify its schedules.

V1 prevents overlapping **doctor sessions** across assignments using a database-backed time-range invariant on `appointment_sessions`. Multiple patients may legitimately share the same token session, so do not apply a per-patient overlap exclusion to that mode. Exact-time appointments additionally enforce one active booking per generated slot. Conflicts reveal only “unavailable,” not another tenant's details. This protects only platform schedules; outside commitments and travel buffers remain unknown.

### 5.4 Scheduling algorithm

1. Resolve assignment and location timezone; apply active date range and configured booking horizon.
2. Read weekly intervals, then apply date exceptions. A closed-day exception wins; replacement-hours exception replaces regular hours.
3. Generate a dated doctor session with the configured mode. In exact-time mode, divide it into full slots and discard trailing fragments. In token mode, store the full window and positive `max_patients`; do not manufacture exact consultation slots.
4. Convert to UTC with explicit timezone handling; reject ambiguous/nonexistent daylight-saving times unless an explicit offset policy resolves them.
5. Upsert sessions/slots idempotently. Never delete or shift held/confirmed appointments, change their mode, or reset their token counter during regeneration.
6. Exact-time availability excludes reserved slots; token availability reports remaining capacity after live holds and non-cancelled confirmed bookings, including served/no-show bookings. Apply booking cutoff, doctor session conflicts, closed sessions and inactive assignments in both modes.
7. Lock and revalidate when reserving. A prior availability response is an offer, not a guarantee.

Schedule edits affecting reservations show the affected bookings and require an explicit staff resolution workflow. For V1, block conflicting edits until staff cancels/rebooks affected appointments; do not silently invalidate patient bookings.

The expiry worker clears expired holds, but reservation transactions also expire stale holds under lock so worker delay cannot strand capacity. Use database time. Default token-session online booking cutoff is 30 minutes before session start; during the session staff may add walk-ins within remaining capacity until the configured cutoff. Both defaults are configurable and visible to the assistant.

### 5.5 Booking modes and capacity policy

| Mode | Patient promise | Capacity | Example |
| --- | --- | --- | --- |
| `EXACT_TIME` | A scheduled time, subject to clinic delays | One reservation per generated slot | 4:10 PM or 4:30 PM |
| `SESSION_TOKEN` | A place within a session window plus token; no exact consultation-time guarantee | Admin-configured maximum patients per dated doctor session | 4–6 PM, maximum 30, token 10 |

Mode belongs to the doctor session, independent of Clinic/Hospital organization type. One hospital may use token OPD and exact-time specialist appointments on different non-overlapping sessions. Select mode explicitly at setup; do not change it after reservations exist without a controlled rebooking workflow.

For a 4–6 PM session, 30 patients is a permitted **configured example**, not a recommended clinical throughput: 120 minutes / 30 is four minutes per patient before breaks. The clinic chooses a realistic maximum; the UI shows that arithmetic to help configuration. Exact-time mode at ten minutes per slot over two uninterrupted hours yields 12 slots, not 30.

Token-mode invariant: `live_holds + confirmed_non_cancelled_bookings <= max_patients`. Completed and no-show bookings remain consumed for that session; seeing a patient does not create a new booking place. Cancelled bookings and expired holds release capacity. No overbooking override in V1. Capacity can increase with admin permission and audit; decrease only to at least the already-consumed count. Mode/time edits with reservations are blocked pending explicit resolution.

### 5.6 Appointment numbers and queue rules

- Every appointment gets a non-sequential public booking reference usable across dates/locations. A token such as 10 is scoped to one doctor session/date/location, not the whole clinic.
- Allocate a token once, **at confirmation**, by atomically incrementing `next_token` while locking the session row. Never compute it as `COUNT(bookings) + 1`, which breaks under cancellations and concurrency.
- Holds consume capacity but do not yet receive a promised token. Delayed confirmations therefore receive later numbers; describe tokens as confirmation order, not call-arrival order.
- Cancelled tokens are not reused, and existing tokens are never renumbered. After cancellations/replacements, the highest token can exceed 30 while the session still has at most 30 counted bookings. Capacity and token sequence are different values.
- AI, staff phone bookings and walk-ins all use the same counter, booking service and capacity. `source` distinguishes `AI_VOICE`, `AI_TEXT`, `STAFF`, and `WALK_IN`.
- Manual queue states: `NOT_ARRIVED -> CHECKED_IN -> CALLED -> IN_CONSULTATION -> SERVED`; `SKIPPED` may return to checked-in under staff action. Only confirmed, non-cancelled bookings enter the queue. Serving atomically records appointment `COMPLETED`; cancellation/no-show removes queue eligibility. Queue actions are role-controlled and audited.
- “Call next” selects the lowest eligible checked-in token by default and is atomic so two staff cannot call different patients for the same doctor simultaneously. Any explicit reorder/recall requires a staff reason; it never changes the original token number.
- Staff marks session open/closed and manages arrivals/delays. No automated clinical priority ranking. No exact wait estimate in V1; optional “patients ahead” comes from current checked-in queue data, never from token subtraction.
- Confirmation shows doctor, location, full date, session window or exact time, booking reference, token where applicable, and approved arrival instructions.

## 6. Booking, payments, and reliable delivery

### 6.1 Appointment state machine

```text
no appointment
   -> PAYMENT_PENDING       explicit consent + atomic slot/session capacity reservation
        -> CONFIRMED        authenticated simulated success in current demo
        -> EXPIRED          database hold deadline reached
        -> CANCELLED        authorized release/cancellation

no appointment
   -> CONFIRMED             staff policy: pay-at-clinic or authorized waiver

CONFIRMED -> CANCELLED       authorized staff or verified permitted caller; explicit confirmation/reason
CONFIRMED -> RESCHEDULED     successful atomic replacement; old record retained
CONFIRMED -> COMPLETED       authorized staff action
CONFIRMED -> NO_SHOW         authorized staff action after scheduled time
```

Current payment state is separate: `SIMULATION_PENDING`, `SIMULATED_SUCCESS`, `SIMULATED_FAILURE`, or `DUE_AT_CLINIC`/`WAIVED` under authorized policy. `PAYMENT_PENDING` is an internal lifecycle state; staff and patient-facing demo copy explicitly says simulated. `CONFIRMED` means capacity is committed, not that real money was received. Future real-provider states include `LINK_PENDING`, `LINK_CREATED`, `UNKNOWN`, `FAILED`, `PAID`, and `REVIEW_REQUIRED`. Delivery failure does not unconfirm a booking.

### 6.2 Atomic hold operation

Inputs: trusted tenant context, patient, offered session and optional exact slot, quote version, explicit consent reference, actor/call, idempotency key. The model cannot supply an authoritative fee or capacity.

Within one transaction:

1. Check idempotency record and reject key reuse with different input.
2. Lock the dated session and optional exact slot in a consistent order; session generation separately enforces canonical-doctor scheduling conflicts.
3. Expire stale holds; validate tenant relationships, active assignment/session, booking cutoff and mode. Exact-time mode checks the selected slot is free; token mode checks the counted occupancy is below `max_patients` under the session lock.
4. Verify consent matches the current offer and quote, including booking mode. If price, session or slot has changed, return a requote response.
5. Insert `PAYMENT_PENDING`, immutable fee/currency snapshot and database expiry.
6. Insert local simulation attempt and audit event; persist idempotent result. Under permitted pay-at-clinic policy, confirm in the same transaction and allocate the token exactly once when applicable.
7. Commit and return actual hold status and expiry.

Use database uniqueness/session-overlap constraints and one locked transactional reservation procedure as the final protection. Direct table writes must not bypass session capacity: grant runtime reservation mutations only through the controlled procedure or enforce equivalent trigger checks for all writers. Re-count after expiring stale holds under the same lock. Test against PostgreSQL, not SQLite.

### 6.3 Current prototype: payment simulation

Build a small local `MockPaymentProvider` and staff/test control panel. It supports explicit “Simulate success,” “Simulate failure,” and expiry/replay scenarios. No Razorpay SDK, account, keys, external checkout or card/UPI details are needed in this release. Keep the payment interface small; future compatibility is not a reason to implement unused provider machinery now.

Simulation controls require an authenticated demo operator with tenant permission and are enabled only by a server-side demo-mode flag. The LLM and anonymous caller cannot trigger success merely by saying “I paid.” Do not expose a public unauthenticated “mark paid” endpoint or put an authorization token in WhatsApp links.

On simulated success, the same transaction validates the pending hold and expiry, records `SIMULATED_SUCCESS`, confirms the booking, allocates a session token if applicable, inserts confirmation-message work, and audits the simulated actor/event. Replays return the original outcome; they cannot increment the token again. Expired/cancelled reservations cannot be revived. Failure leaves the hold eligible for another simulated attempt until expiry or explicit release.

The dashboard and any demo messages explicitly show “Payment simulated — no money collected.” Send an ordinary booking/hold notification over WhatsApp; omit real payment links. During a demonstration the operator can simulate success while the caller is on the phone; the assistant retrieves committed status and announces the confirmed booking/token. Optional future customer-facing mock checkout is not required now.

### 6.4 Deferred: real payment link creation and webhooks

**The rest of this subsection is future integration design, not a current acceptance gate.** Implement it only when real payments are requested, beginning with Razorpay Test Mode and a fresh provider feasibility check.

The worker checks the hold is still eligible, creates an attempt with a deterministic internal reference, then calls Razorpay outside the booking transaction. On success it stores the provider link and queues the message atomically.

If the network times out after the provider may have accepted the request, mark `UNKNOWN` and reconcile using provider lookup/reference capabilities verified in Phase 0. Do not blindly create another link. If a provider cannot deduplicate or look up an uncertain create, put it in staff review. Retry only failures known not to have created an external resource.

Hold expiry remains authoritative even if the provider's minimum link expiry or cancellation behavior differs. Attempt provider cancellation on release, but treat cancellation failure as a possible late-payment case. Tell the caller the actual hold deadline, not just the link's displayed expiry.

#### Future payment webhook processing

Razorpay documents signature verification, duplicate event IDs and possible out-of-order delivery; ingress must tolerate these. [Razorpay webhook validation](https://razorpay.com/docs/webhooks/validate-test/?preferred-country=IN), [webhook best practices](https://razorpay.com/docs/webhooks/best-practices/?preferred-country=IN)

1. Verify signature against raw request bytes using the expected account's secret; do not trust client redirect parameters or parsed-body reserialization.
2. Persist a unique inbox event before successful acknowledgement. Database failure returns a retryable response rather than losing the event.
3. Resolve tenant through the stored account/payment mapping, never solely through caller-supplied metadata.
4. Validate provider account, link/order/payment IDs, amount, currency, test/live mode and a qualifying paid/captured state. Authorization alone is insufficient.
5. In a transaction, lock the appointment/slot using the same lock order as expiry/reservation. Apply monotonic payment transitions and deduplicate by event and payment identity.
6. Confirm only if the appointment is still `PAYMENT_PENDING`, its hold is unexpired at processing time and the reservation still belongs to it. Allocate a token once for token mode; insert audit and confirmation message job in the same commit.
7. Otherwise record the received payment and create `REVIEW_REQUIRED`. Do not resurrect expired bookings or steal a reallocated slot.

The conservative late-payment rule also applies when the provider says payment occurred before expiry but the webhook arrived after release. Staff resolves rebooking/refund in test mode. Automated refunds are out of scope; the review queue and resolution history are mandatory.

### 6.5 Reliable jobs and reconciliation

- Workers claim due jobs using row locks/leases; expired leases become eligible after crash recovery.
- Every handler is idempotent. Use bounded exponential backoff with jitter and attempt caps; then surface a dead-letter/staff-review state.
- Current periodic jobs: expire holds, retry eligible notifications, recover voice/message inbox events, prune expired evaluation content and release job leases. Real payment-provider reconciliation is deferred with that adapter.
- Dashboard actions can request a safe retry; they cannot bypass state validation.
- Future real-payment adapter: poll status for outstanding known attempts on a bounded schedule to recover missed webhooks. In the current release read local simulation status. Never infer success from a message click or caller assertion.
- Track outbox age and worker heartbeat. A healthy HTTP process with a dead worker is degraded.
- Duplicate external messages remain possible after an ambiguous send timeout unless the provider offers reliable deduplication. Reconcile by message ID when known; flag unknown sends rather than promise exactly-once delivery.

### 6.6 Cancellation, correction and disconnect rules

Current simulation: release or expire capacity through the shared booking service; an old simulator control cannot confirm a released hold. Confirmed cancellations never reuse a token. Keep simulated history without creating a real refund task. The payment-link/refund-specific rules below apply only to the deferred provider integration.

- Before payment link creation: a caller may release a current-session hold and choose another offer.
- After a link is created: explicitly explain replacement; release old hold, request link cancellation, then reserve the new slot with fresh consent. If the new slot loses the race, offer alternatives. Never silently promise an atomic swap across provider systems.
- If payment is already confirmed or uncertain: route changes to staff; do not guess whether it is safe to cancel.
- If a call disconnects before consent: no hold. After consent and reservation: keep the hold until expiry; send only to a consented recipient. Record the disconnect outcome.
- A staff cancellation of a paid appointment releases capacity and creates a payment-review item. It does not imply a refund was issued.

### 6.6.1 Existing-booking cancellation and atomic rescheduling

Applies to both AI and staff via the same service. AI access requires current-call verification plus an active booking permission; patient ID, booking reference, phone match and token are never sufficient authorization.

- Default self-service cutoff: 30 minutes before original session/slot start. Restrict to future confirmed appointments not already checked in/served/cancelled; clinic policy can tighten this. After cutoff or for fee differences/real-payment complications, route to staff. These defaults are proposed business rules.
- Cancellation: read back patient, doctor, date and time/window, obtain explicit confirmation tied to current appointment version, then atomically cancel, release capacity, invalidate queue eligibility, audit and enqueue notification. Never reuse the token. Replays return the original outcome.
- Rescheduling: find a new actual offer; quote new doctor/date/time/window and any mode change; obtain fresh consent. Same target is a no-op. Any fee difference or unresolved payment goes to staff in V1.
- In one transaction, lock old/new sessions in sorted ID order, then affected slots/appointments consistently. Recheck permission, verification expiry, policy, old version, target availability and consent. Create a confirmed replacement, allocate its token if required, set old booking `RESCHEDULED`, release old capacity, copy only authorized booking permissions and notification contact, and insert audit/outbox/idempotency records together.
- Count `RESCHEDULED` as released capacity and no longer queue-eligible. Failed target allocation rolls the entire transaction back; never cancel the original first. Only one of concurrent cancel/reschedule requests may succeed for an appointment version.
- Preserve old/new booking references, session/token snapshots and `supersedes_appointment_id`. A new token belongs to the new session; the old token is never recycled. Carry forward the simulation/pay-at-clinic policy truthfully without inventing another successful real payment.
- Checkpoint or audio interruption does not undo a committed change: retrieve its actual result before responding to the caller.

### 6.7 API contract outline

| Group | Proposed routes | Key rules |
| --- | --- | --- |
| Tenant/config | `/v1/organizations/current`, `/locations`, `/departments`, `/voice-settings` | Membership scoped; configuration writes admin only |
| Directory | `/v1/doctor-assignments`, `/schedule-rules`, `/schedule-exceptions`, `/appointment-sessions` | Mode/capacity validation; no cross-tenant canonical directory enumeration |
| Availability | `/v1/availability` | Assignment/location, date window and timezone explicit |
| Patients | `/v1/patients` | Staff search versus restricted agent lookup contracts |
| Contact/verification | `/v1/contacts`, `/v1/call-verifications/start`, `/verify` | Trusted call binding, saved destination, throttling and generic responses; browser/agent cannot choose another tenant or destination |
| Returning caller | `/v1/caller/appointments`, `/appointments/{id}/reschedule`, `/cancel`, `/resend` | Current verification and per-booking permission required for caller operations; explicit consent for changes |
| Booking | `/v1/appointments/holds`, `/appointments/{id}/release`, `/appointments` | Idempotency required for mutations; server price and consent checks |
| Staff actions | `/v1/appointments/{id}/cancel`, `/complete`, `/no-show` | Role, reason and optimistic version check |
| Queue actions | `/v1/appointments/{id}/check-in`, `/skip`, `/v1/appointment-sessions/{id}/call-next` | Staff authorization, session lock, state transition and reason rules |
| Payment simulation | `/v1/demo/payment-attempts/{id}/simulate` | Authenticated tenant-scoped demo operator; server demo flag; no public or agent success command |
| Exceptions | `/v1/operations/exceptions`, `/callback-requests` | Audited resolution and retry commands |
| Agent harness | `/v1/test-sessions`, `/test-sessions/{id}/turns` | Authenticated demo-only text workflow |
| Provider ingress | `/webhooks/twilio/voice`, `/status`, `/messages` | Provider-specific authentication, size limits, durable handling; Razorpay endpoint deferred |
| Voice stream | `/ws/twilio/media` | Verified signed upgrade and server-bound call context |
| Health | `/health/live`, `/health/ready` | No secrets or tenant details exposed |

Use Pydantic request/response schemas and generate a typed web client from OpenAPI. Errors carry stable codes such as `SLOT_UNAVAILABLE`, `OFFER_CHANGED`, `HOLD_EXPIRED`, `PAYMENT_UNCERTAIN`, `TENANT_FORBIDDEN`, and `PROVIDER_UNAVAILABLE`, plus correlation ID and safe retry guidance. Paginate listings and bound date ranges.

## 7. Conversation workflow and voice behavior

### 7.1 Workflow structure

Use one explicit graph with adaptive transitions, not three disconnected scripts. Fast/guided/discovery are observable paths through the same state and services.

```text
receive finalized utterance
 -> urgent-safety / explicit-human / scope checks
 -> extract typed state patch
 -> validate references and apply corrections
 -> determine next permitted action
    -> ask shortest useful clarification
    -> fetch administrative facts / doctors / availability
    -> collect minimum patient and recipient information
    -> summarize current offer and request consent
    -> reserve through booking service
    -> report actual hold/payment/delivery state
    -> transfer or close
 -> checkpoint and emit safe response
```

Urgent-safety and explicit-human intents take precedence over booking. LLM-generated classification is one signal; deterministic validations, bounded retries and human escalation remain necessary.

LangGraph supports checkpoint-based persistence. Use that for conversation continuity, while keeping idempotency and booking truth in domain tables; a graph checkpoint is not proof that an external side effect did or did not happen. [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

### 7.2 State contract

| State group | Required values |
| --- | --- |
| Trusted identity | organization_id, call/session ID, channel, authenticated actor context |
| Turn ordering | turn_id, utterance_id, state_version, active response generation ID |
| Understanding | intent, requested language, routing category, unresolved ambiguity |
| Selection | department_id, assignment_id, booking_mode, session_id, local date/preference, offered sessions/slots and offer version, optional selected_slot_id |
| Patient/contact | separate contact_id/contact_name and patient_id/patient_name, relationship, presented phone, saved contact phone, permission scope and consented recipient |
| Verification | recognized contact, verified contact phone/version, verified_until, remaining attempts and permitted booking IDs/actions; no raw codes |
| Booking | current appointment ID, booking reference, optional confirmed token, hold expiry, quote snapshot, consent snapshot/version |
| Control | last question, short recent dialogue, clarification count, tool budget, transfer state |
| Voice | listening/speaking/interrupted, pending playback marks, speech generation ID |
| Trace | policy/model/config versions, last safe outcome, timestamps |

Track field provenance: caller-provided, tool-resolved, inferred, or confirmed. An inferred field cannot authorize an irreversible transition. Use typed patches to distinguish “unchanged” from “explicitly clear.”

Dependency invalidation rules:

- Changing department clears incompatible doctor, offers, selected slot and consent.
- Changing doctor/location/date clears offers, selected slot and consent.
- Changing patient, price or slot clears booking consent.
- Correcting the message recipient clears recipient consent.
- Existing holds are not forgotten by clearing conversation fields; an explicit service operation releases or flags them.

### 7.3 Tool catalog

| Tool | Preconditions | Allowed result/action |
| --- | --- | --- |
| `get_clinic_information` | Trusted tenant | Curated hours, fees, location and policies |
| `find_doctors` | Supported directory/routing query | Tenant-scoped candidates with ambiguity preserved |
| `get_doctor_schedule` | Valid assignment | Configured schedule facts, not booking guarantee |
| `check_availability` | Valid assignment/date range | Typed offers with booking mode: exact slots OR session window/remaining capacity, never a predicted token |
| `find_patient` | Restricted context and caller-supplied details | Safe match decision; no enumerable names/history |
| `create_patient` | Minimum provided identity/contact | Tenant patient or explicit possible-duplicate response |
| `start_contact_verification` | Trusted current call and resolved saved contact | Generic challenge-start result; never lets LLM redirect destination |
| `list_authorized_appointments` | Current-call verification and active permissions | Minimum necessary upcoming bookings; no blanket patient history |
| `cancel_appointment` | Verified permission, eligible booking and explicit change consent | Idempotent cancellation or safe refusal |
| `reschedule_appointment` | Verified permission, new offer and explicit change consent | Atomic replacement or unchanged original booking |
| `resend_confirmation` | Verified view permission and existing consented destination | Rate-limited durable resend; no arbitrary recipient change |
| `hold_appointment` | Current offer + explicit consent | Actual hold, conflict or requote |
| `create_payment_link` (deferred) | Existing eligible current-session hold | Not exposed in current demo; future idempotent provider operation |
| `get_current_booking_status` | Current-session booking reference | Actual hold/payment/message status |
| `cancel_hold` | Eligible current-session pending hold | Release or safe escalation when payment uncertain |
| `transfer_to_human` | Trusted configured target | Transfer attempt and outcome |
| `request_callback` | Contact and explicit consent | Staff queue item |

The graph exposes only tools valid for the current step. Model output receives schema validation, reference resolution and server authorization before execution. Tool results use stable typed codes and bounded payloads.

### 7.4 Understanding and response policy

Returning-caller verification follows Section 7.9 before private tool results reach the model. Code submission/validation is handled by trusted input processing, not by an LLM decision that a code “looks right.”

- Resolve relative dates using an injected current instant and tenant timezone. Speak the explicit date before reservation.
- Fetch booking mode from the session. In token mode offer a window and announce only the committed token, never an invented exact time or token. If an exact-time request meets a token-only session, explain the available booking type and obtain consent before reserving.
- Detect English/Hindi from speech, honor explicit language preference and allow switching mid-call without clearing patient/booking state. Use reviewed bilingual phrasing for dates, times, fees, tokens, simulation disclosure, consent and fallback. Hindi STT must handle both Devanagari and Romanized intermediate text; speech generation must pronounce local names/numbers intelligibly.
- Preserve ambiguity in “kal,” “paanch,” similarly named doctors, pronouns and family-member references. Clarify when different interpretations lead to different bookings.
- Use clinic-reviewed aliases for lay terms. Do not equate every stomach complaint with one specialty or infer a diagnosis from joint pain.
- Present two or three useful slot choices, not an entire calendar. If unavailable, ask before changing doctor/location/date.
- Ask one question at a time where practical; skip already known information. Allow complete information in one utterance.
- Keep responses brief; avoid repeated greetings and filler. Announce tool delays only when useful and truthful.
- Do not ask for payment card details, medical reports or detailed symptom histories.
- Never treat the LLM's numerical confidence as calibrated certainty. Combine unresolved entities, explicit ambiguity, validation failures and clarification history. After two unsuccessful clarifications on the same issue, offer/attempt human assistance.
- On model/schema failure: one bounded repair attempt, then safe fallback. Set per-turn model/tool limits and a graph recursion ceiling.

### 7.5 Context and token budget

Send a short immutable policy, minimal tenant facts, compact structured state, latest utterance, a short recent dialogue window and relevant tool result. Preserve the last offered options and question so “the second one” can be resolved. Do not strip all conversational context solely to save tokens.

Default budgets: one extraction/planning model call per ordinary turn, at most one response-generation call when needed; at most three tool operations per turn before a controlled continuation. Set explicit output-token limits. Cache static configuration by tenant and configuration version; never use cached availability as reservation truth. Record actual usage and benchmark before changing models.

### 7.6 Voice gateway

OpenAI provides a transcription-only realtime path, so using realtime transcription does not require delegating the conversation to a speech-to-speech agent. Confirm the selected model's event and audio contract in the Phase 0 spike. [OpenAI realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription)

Twilio Media Streams use protocol-specific audio framing; outbound media requires base64-encoded raw μ-law audio at 8 kHz. Playback `mark` and `clear` messages support tracking and clearing buffered audio. Build a tested codec boundary rather than assuming TTS bytes can be forwarded unchanged. [Twilio WebSocket messages](https://www.twilio.com/docs/voice/media-streams/websocket-messages)

Voice implementation must:

1. Verify the inbound webhook and bind account, called number, call ID and tenant before opening a session.
2. Verify the WebSocket upgrade using the provider-supported signature flow and compare stream start identity against the server session. Do not trust arbitrary stream parameters as authorization.
3. Stream caller audio continuously; use speech activity and finalized transcripts to drive turns. Partial transcripts may inform UI/latency instrumentation but cannot authorize booking.
4. Reassemble/order transcription events by utterance IDs; discard duplicates. Serially apply state updates per call.
5. Convert TTS chunks to the correct raw audio codec/rate, preserve boundaries and pace output to avoid large buffers.
6. Bound queues and apply backpressure; cap audio/session duration and close leaked sessions.
7. Separate audio handling, graph work and playback tasks so database/model waits do not block listening.
8. Include a clear AI-voice disclosure in the greeting. OpenAI's speech guidance calls for disclosing that the voice is generated. [OpenAI text to speech](https://developers.openai.com/api/docs/guides/text-to-speech)

### 7.7 Barge-in and stale work

On detected caller speech during AI output:

1. Send Twilio `clear`, cancel local queued playback and best-effort cancel TTS generation.
2. Increment the response generation ID. Discard later audio from the old generation.
3. Track playback marks so the dialogue does not assume the caller heard an entire interrupted offer.
4. Process the new finalized utterance against the current state version.
5. Ignore stale read results for planning. For an already committed mutation, retrieve its actual outcome and explicitly reconcile it; cancellation of an async task does not roll back a database commit or provider request.
6. Reconfirm any interrupted booking summary. “Yes” to an unheard or superseded summary is not valid consent.

Test speech overlap, echo, background speech, false starts, corrections during a slow tool call, and interruptions immediately before/after hold commit.

### 7.8 Transfer and unavailable-service behavior

There are two separate fallback mechanisms:

- **Application-level handoff:** Stop graph/playback, checkpoint a minimal handoff summary, then redirect the live call to controlled dial instructions. Record answer/busy/no-answer/error and return a courteous next step if possible. Confirm that changing the live call actually exits the active media stream; merely placing dial instructions after a blocking stream is insufficient. [Twilio Connect](https://www.twilio.com/docs/voice/twiml/connect)
- **Infrastructure fallback:** Provider-hosted TwiML or an independently hosted minimal endpoint routes a known endpoint to its configured reception line when the primary webhook is unavailable. It must not depend on the failed application/database. Test initial webhook failure separately from a mid-call WebSocket/process failure.

For mid-call failure, use tested stream-close continuation/call redirection and a liveness supervisor where needed. Do not assume the initial webhook fallback automatically catches every streaming error. Track this as an explicit feasibility and final acceptance test.

Transfer targets are admin-configured and validated; reject loops to the same AI number and arbitrary premium/international destinations outside approved configuration. Caller ID is not proof of identity. A transfer succeeds only when a destination answers; initiating a dial is not success.

Reception closed/no answer: offer a consented callback request with accurate operating hours. Do not invent an expected response time. For urgent-risk language, use reviewed local emergency guidance rather than treating a routine reception transfer as emergency assistance.

### 7.9 Returning callers and verification policy

1. Incoming number privately locates possible contacts within the called organization. Greet naturally without announcing names, appointment counts or previous visits before verification.
2. General clinic questions and creation of a new booking do not require prior-record access or an OTP. New bookings never unlock existing patient records.
3. For existing-booking details, listing, resends or changes, send a short-lived challenge to the saved contact via the configured supported SMS/WhatsApp mechanism. A different/hidden caller number may supply a booking reference to locate it privately, but cannot replace its saved verification destination.
4. Proposed challenge controls: six random digits, five-minute expiry, five failed attempts maximum, 60-second resend cooldown and at most three sends per contact in 15 minutes; also throttle by tenant/call/source to prevent enumeration and message abuse. Store a keyed digest using a server secret, never plaintext or an unkeyed low-entropy code hash. Resend invalidates the prior code. Use generic unknown-contact/error responses.
5. Validate input in trusted code; redact codes before logs, graph checkpoints or LLM prompts. Successful challenge is single-use and authorizes the bound call/contact phone version for up to 10 minutes or call end, whichever comes first. Persistent `last_verified_at` does not authorize the next call. Staff revocation/phone changes invalidate access immediately.
6. After verification, load only appointments allowed by active `appointment_contact_permissions`. Clarify patient/appointment when multiple permitted results exist. Contact verification is not permission for all appointments sharing a surname, number or patient ID.
7. Read-only answers use current database data. Cancellation/rescheduling additionally require current policy eligibility and explicit read-back confirmation. Adding another family booking keeps existing appointments unchanged.
8. Verification delivery failure, unknown/reassigned contact, ambiguous existing-patient linkage or lack of permission leads to reception. Never downgrade to caller-ID-only access silently. Synthetic verification fakes can test local logic; real returning-caller acceptance requires real supported delivery or an explicitly documented scope change.

## 8. Dashboard and operations experience

### 8.1 Screens and acceptance behavior

| Screen | Must support |
| --- | --- |
| Login/organization switch | Authenticated session, permitted memberships only, current clinic always visible |
| Today/appointments | Day/date filters, doctor/location, patient, source, hold expiry, booking/payment/delivery state |
| New appointment | Patient details, assignment, available slot OR session capacity, quote, explicit payment policy, conflict recovery |
| Doctor session/queue | Booking mode, maximum/count/remaining places, token, arrival status, call-next/skip/complete, walk-in booking |
| Appointment details | Booking timeline, safe patient/contact info, payment attempts, messages, staff actions and audit summary |
| Contacts/patients | Separate contact name/phone and patient name, relationship metadata, booking permissions, verification status and staff-controlled contact correction |
| Doctors/assignments | Local clinician details, department/location links, fee and active status |
| Schedule editor | Weekly intervals, effective dates, exceptions, generated preview and affected-booking warnings |
| Organization setup | Clinic/location/timezone, departments, doctors, schedules, language and greeting |
| Integration setup | Endpoint status, credential-reference status, fallback, sender/test mode and test-call checklist |
| Calls | Outcome, durations, transfer state, minimal routing summary and redacted event timeline |
| Exceptions | Simulation/hold conflict, message/transfer failure, worker issues and callbacks; real late/uncertain payment review deferred |
| Staff/settings | Memberships/roles, approved policy controls, activation state |

### 8.2 Onboarding sequence

**Choose Create Clinic or Create Hospital** → create draft organization → location/timezone → departments → doctors/assignments → session booking mode → slot duration OR patient capacity → fee/payment policy → preview sessions/slots → English/Hindi greeting and language settings → manual endpoint mapping → verified fallback route → sender and local simulation setup → test call and booking → admin activation.

Clinic defaults: one initial location, simple doctor list and an optional department step; use a configurable General department when skipped. Hospital defaults: explicit department setup, assignment by department/location and a departmental directory. Both support multiple doctors/locations through the same schema; organization type is a setup preset, not a separate application or an inpatient-management feature.

Manual operation is a first-class P0 journey: staff can create clinics/hospitals, configure doctors/schedules/capacity, search/register patients, book appointments and walk-ins, check in/call/skip/complete patients, cancel bookings and view history without an LLM, STT or TTS call. The dashboard and shared booking API remain operational if AI providers are unavailable. If the primary API/database itself is down, manual software booking is unavailable too; reception phone fallback does not imply offline dashboard support.

Activation requires valid settings, available slots, approved fallback, tested provider configuration and no unresolved blocking checks. Phone provisioning and credential entry are operator-assisted in V1. A second organization can be configured through the same application without code changes.

### 8.3 Interaction quality

- Use distinct, textual labels for held, confirmed, expired, cancelled and review required. Do not communicate payment truth through color alone.
- Show the clinic timezone alongside times and a live hold countdown based on server expiry; refresh state after actions.
- Default to bounded polling, approximately every five seconds on active operational views; target webhook-to-dashboard visibility within ten seconds. Realtime subscriptions are optional.
- Disable duplicate submissions in UI, but rely on backend idempotency for correctness.
- Handle loading, empty, forbidden, stale/conflict and provider-degraded states explicitly.
- Destructive staff actions show the exact appointment and consequences and require a reason where specified.
- Support keyboard operation, clear focus, labels, readable contrast and desktop/tablet layouts. Target WCAG 2.2 AA design practices; do not claim certification without audit.
- No fake success toasts for queued or unknown provider actions. “Link queued,” “sent,” “delivered” and “failed” are distinct.

## 9. Security, privacy, and healthcare boundaries

### 9.1 Threat model and mandatory controls

| Threat | Required control/test |
| --- | --- |
| Cross-tenant object access | Scoped queries, RLS, composite foreign keys, forged-ID tests in every entrypoint |
| Forged provider ingress | Raw signature verification, expected account binding, body limits, event deduplication |
| Prompt injection | Treat speech/tool content as data; enforce immutable policy and server permissions |
| Caller impersonation | Caller-ID matching is private recognition only; bind verification to saved contact/current call and check booking-scoped permission on every existing-record operation |
| Payment tampering | Restricted demo simulator, distinct simulated outcome and no caller-controlled confirmation; future provider signature/mapping validation |
| Credential leakage | Secret manager/environment references; server-only keys; redaction and secret scan |
| Staff privilege escalation | Server membership/role checks; removal effective on subsequent requests; audit role changes |
| Cost/denial-of-service abuse | Concurrent-call limits, bounded requests/audio/tool loops, provider timeouts and spend alerts |
| Transfer fraud | Allowlisted tenant fallback destination; no caller-selected dial target; loop prevention |
| State/job replay | Idempotency keys, version checks, unique events, leased workers and invariant tests |

Use HTTPS/WSS; strict CORS origins; standard secure authentication handling. If cookies carry sessions, add CSRF protection and secure cookie attributes. Verify JWT issuer, audience, expiry and signature against configured keys. Tokens authenticate users; tenant membership still needs an active authorization check.

### 9.2 Privacy baseline

- Demo uses synthetic data and consented testers. Do not import real clinic patient lists for convenience.
- Collect name and required contact only. Optional identity disambiguation must have a specific purpose; avoid collecting date of birth by default.
- Keep contact name and patient name distinct. Relationship labels do not authorize access. Rate-limit verification delivery; never persist raw codes in traces, conversation state or audit data.
- Record WhatsApp opt-in, recipient confirmation and purpose. A voice call alone does not establish an open WhatsApp messaging window.
- Prefer minimal booking content in messages; no complaint/symptom text in payment links, provider metadata or notifications.
- No raw audio retention by default. Redacted operational logs omit names, full phones, credentials, complete transcripts and sensitive free text.
- Graph checkpoints are sensitive records too. Delete terminal-session conversational state after a proposed 24-hour recovery window; retain minimal booking/audit references separately.
- Proposed synthetic-demo retention: evaluation transcripts 7 days when enabled; operational events 30 days; test booking/audit records 90 days or deliberate environment reset. These are prototype defaults, not legal retention advice.
- Backups, provider retention and optional tracing must be included in the data inventory. Local deletion alone does not prove all copies were deleted.
- Before real patient use: clinic-approved consent/retention policies, vendor/data-region review, access review, incident handling and applicable jurisdiction review are separate release prerequisites. No HIPAA/GDPR/local-law compliance claim is made here.

### 9.3 Medical boundary

Allowed: administrative facts, appointment scheduling and clinic-approved department navigation. Disallowed: diagnosis, treatment, dosage advice, interpretation of reports and recommendations that delay urgent care.

Use a clinic-reviewed urgent-risk response policy, configured to the actual service geography. Do not generate emergency contact numbers from the LLM. The system must not claim comprehensive emergency detection. Clinical sign-off is required before real patient use; synthetic demonstration scripts can be evaluated without presenting them as clinical advice.

On uncertainty, do not force a specialty choice. Offer staff assistance. For unsupported medical requests, briefly explain the administrative role and route appropriately.

### 9.4 Roles

| Action | Receptionist | Organization admin | Platform operator |
| --- | --- | --- | --- |
| View/book tenant appointments | Yes | Yes | Only explicitly authorized tenant support session |
| Pay-at-clinic booking | If tenant policy permits | Yes | No implicit permission |
| Fee waiver | No by default | Yes, reason required | No implicit permission |
| Simulate payment outcome | Explicit demo permission only | Yes in demo mode | Explicit tenant demo permission only |
| Cancel/complete/no-show | Yes, per policy | Yes | No implicit permission |
| Configure doctors/schedules | Read by default | Yes | Provisioning assistance when authorized |
| Manage membership/integrations | No | Tenant configuration | Platform provisioning and secrets |
| View aggregate service health | Tenant scope | Tenant scope | Yes, minimized operational data |

## 10. Quality targets, measurement, and evaluations

### 10.1 Target service envelope

These are proposed acceptance targets, not measured promises. Establish a baseline early and document any approved change; never silently lower a gate to pass.

| Metric | Prototype target | Measurement |
| --- | --- | --- |
| Double booking | Zero | 20 simultaneous requests for one slot, repeated 100 times; AI/staff mixed |
| Token session capacity/numbering | Zero over-capacity or duplicate tokens | 50 contenders for capacity 30; last-place race; cancellation, expiry, confirmation replay and walk-ins |
| Cross-tenant leakage | Zero in security suite | API, RLS, tools, jobs, checkpoints and dashboard tests |
| False confirmation | Zero | Unauthorized/replayed/expired simulated outcome and interrupted-consent tests; real provider variants deferred |
| Deterministic text journey success | 100% expected outcomes | Provider-fake scenario suite |
| Live-model supported journey success | At least 90% overall and separately in English/Hindi | At least 60 labelled scenarios, each run three times, balanced by language and booking mode |
| Re-asking already known fields | At most 5% eligible turns | Annotated conversation review |
| Safety/injection critical cases | 100% expected safe outcome in fixed suite | No unauthorized action or medical advice; finite suite is not universal assurance |
| Availability API latency | p95 below 500 ms | Warm deployment, seeded 30-day horizon, representative concurrency |
| End of speech to first useful audible response | p50 at most 1.5 s, p95 at most 3 s on ordinary turns | At least 100 measured turns; tool turns reported separately with p95 target 4 s |
| Barge-in stop latency | p95 at most 300 ms after speech-start detection | Audio/playback instrumentation and real-call review |
| Hold release | Correct at transaction boundary; worker cleanup within 60 s | Controlled clock/race tests and worker metrics |
| Simulated confirmation to dashboard | p95 within 10 s | Authorized simulation action → commit/token allocation → UI refresh; real payment benchmark deferred |
| Message dispatch | p95 within 15 s of eligible job | Excludes carrier delivery; delivery measured separately |
| Live capacity | Initial gate: five concurrent calls for 30 minutes; higher capacity uinroven | Stepwise 1/3/5 then optional 10/20; no mixing, overload or voice SLO violation |
| Recovery | Durable jobs resume within 2 minutes of worker restart | Kill/restart with work in progress |

Measure latency from actual end of caller speech, so VAD delay is included. First useful audio excludes filler that merely masks waiting. Report sample size, environment, region, model versions and p50/p95. Word error rate can diagnose transcription quality, but correct doctor/date/time extraction and task outcome are the product metrics.

### 10.2 Evaluation set

Create a versioned set with expected extracted fields, allowed actions, prohibited actions and final states:

- Fast requests, department requests and vague caregiver bookings.
- Both exact-time and session/token bookings; full sessions; stable token on replay; unsupported exact-time promises; walk-in versus AI last-place contention.
- Hindi, English and code-switching; local names; noisy 8 kHz audio; slow and fast speakers.
- Ambiguous time/date/name, invalid/past date, unknown doctor, no slots and unsupported language.
- Corrections after offers, after consent and during in-flight hold/link creation.
- Shared phones, anonymous caller, alternate WhatsApp recipient and refusal to provide details.
- Aryan as non-patient contact booking for mother/father, returning caller with two permitted appointments, unrelated appointment on the same patient, denied/revoked family permission, different caller number, name collision and recycled-number handling.
- Wrong/expired/replayed verification codes, delivery failure, resend/guess throttles and attempted destination override; code redaction from model context/logs.
- Verified cancellation/reschedule, stale appointment version, simultaneous changes, unavailable replacement, original booking retained on failure, correct replacement token and same-target no-op.
- Explicit human request, repeated misunderstanding, medical advice requests and urgent-risk examples with reviewed expected responses.
- Prompt injection to switch tenants, override fees, execute SQL, claim payment or dial arbitrary numbers.
- Duplicate events, delayed final transcripts, silence, hangup, repeated “yes,” and incomplete/interrupted summary.

Use at least 60 text scenarios (20 English, 20 Hindi, 20 Hinglish/mixed) and 30 synthetic/consented audio fixtures (10 per group), covering both booking modes. Include at least six mid-call language-switch cases. Do not tune on the entire acceptance set; reserve a held-out subset. Review all critical failures manually. Log expected actions and results, not hidden model reasoning.

### 10.3 Test layers

1. Unit tests for date resolution, state invalidation, authorization rules, policy decisions and codec conversion.
2. PostgreSQL integration tests for tenancy, locks, uniqueness, doctor overlap, expiry and payment races.
3. Provider contract tests for payloads, signatures, callback variants, streaming events and retry behavior.
4. API/browser tests for staff onboarding, schedule changes, manual booking, exceptions and forbidden actions.
5. Graph evaluations with deterministic providers, then bounded live-model evaluations.
6. Real phone and WhatsApp acceptance with designated testers and local simulated payments; no Razorpay gate yet.
7. Fault tests: process death, database failure, model/STT/TTS timeout, Twilio disconnect, worker death and message failure.

Prioritize invariant and journey tests over tests that only mirror code structure. CI should not depend on paid providers for every commit; live-provider checks are controlled release gates.

### 10.4 Observability and cost

Correlate request, organization, call, turn, appointment, payment attempt and provider event IDs. Record stage durations, tool result codes, retries, final outcome, model/config version, input/output usage and audio duration. Mask contact values in operational views.

Show call outcomes separately: held pending payment, confirmed, information answered, transferred and answered, transfer failed, abandoned, blocked or provider failure. A transfer is not automatically an AI failure; a pending hold is not a confirmed booking.

Estimate per-call cost from measured telephony minutes and transfer legs, STT audio usage, LLM tokens, TTS usage, messages and allocated hosting. Record pricing date and source during Phase 0; do not hard-code a forecast into the product. Owner sets per-day/per-demo budget before billable testing. Warn at 80%; at the agreed cap stop admitting new AI work or use the configured human path, while allowing webhook/booking recovery to continue.

### 10.5 Determine actual simultaneous-call capacity

Do not confuse the clinic's **patient capacity** (e.g. 30 in one doctor session), **simultaneous active calls**, and **call arrival rate**. A call arriving every second is a different load from one call held open for a minute. Outbound initiation-rate limits are not a measurement of active inbound call capacity.

Twilio documents one bidirectional stream per call; each stream has its own WebSocket. That is a per-call protocol constraint, not a one-call limit for our application. [Twilio Media Streams overview](https://www.twilio.com/docs/voice/media-streams)

OpenAI rate limits vary by model and project/organization settings. Verify the actual STT, LLM and TTS entitlements before capacity testing rather than assuming one shared universal limit. [OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits)

Capacity test procedure:

1. Record account quotas, model IDs, host CPU/RAM, worker count, DB pool, regions and budget. Count transfer legs separately from AI streaming sessions.
2. Measure one call, then 3 and 5 simultaneous calls. Use a representative mix of both languages/modes, speech overlap, long calls, tools, staff booking and interruptions.
3. Hold each tier long enough for repeated turns; required G6/G8 soak is 30 minutes at five. Test 10 and 20 only within account/budget approval; record unsupported tiers explicitly.
4. Capture p50/p95 response and barge-in latency, provider 429/timeouts, CPU/RAM, event-loop lag, active sockets, audio queue size, DB wait/locks and call success.
5. Exercise a sudden arrival burst and a slow dependency, not just steady open sockets. Synthetic socket tests establish infrastructure behavior; they do not replace full real-provider calls.
6. Publish the highest sustained tested tier that meets the voice/booking targets, the first failing tier if tested, its bottleneck and recommended admission limit with headroom. If no tier above five was tested, do not call five the maximum.
7. Enforce global and per-tenant call admission limits in a shared atomic lease/counter so extra replicas cannot exceed the quota. Recover leases on disconnect/crash. Above limit, follow the preconfigured busy/reception path; do not accumulate an unbounded AI queue or assume one reception line can answer unlimited overflow.

Each call owns isolated graph/audio state and cancellable tasks. Horizontal scaling requires shared durable state/admission counters, sticky ownership of each live WebSocket, graceful draining and tested DB/provider headroom. Adding instances cannot overcome provider quotas. The release report states **tested capacity**, not a speculative “100 calls” claim.

## 11. Environments, deployment, and recovery

### 11.1 Environments

- Local: synthetic seeds, local/test PostgreSQL, provider fakes and text harness; optional temporary webhook tunnel for development.
- Demo/staging: dedicated Supabase project, server-enabled mock payment mode with no Razorpay credentials, explicit phone/sender mappings, approved test recipients, HTTPS/WSS hosting.
- Future production: separate accounts/secrets/data and a separate go-live review. Never switch test/live mode through an ordinary receptionist control.

Recommended topology: static web host; always-on container hosting for FastAPI voice/API; separate worker process from the same codebase; Supabase database/Auth; provider-hosted independent fallback. Choose the hosting vendor in Phase 0 based on region, WebSocket duration, health checks, graceful shutdown, secrets and cost. No cloud account creation is authorized by this document.

### 11.2 Delivery controls

- CI runs lint/type checks, relevant tests, migration validation, secret scan and web build.
- Migrations are the only schema authority. Seed scripts are idempotent and explicitly synthetic.
- Deploy additive compatible schema changes before application changes; avoid destructive migration rollback on live data.
- Readiness checks verify essential local dependencies. Provider health can mark service degraded without repeatedly restarting healthy processes.
- On deployment, stop admitting new calls to the retiring process, drain active sessions for a bounded period and use tested fallback for the remainder.
- Use runtime secret injection, documented environment variables and `.env.example` with placeholders only.
- Observe connection pool limits; use an appropriate PostgreSQL connection mode for transactions, workers and graph checkpoint storage, verified under the chosen Supabase setup.

### 11.3 Runbooks required before final acceptance

| Runbook | Required instructions/evidence |
| --- | --- |
| Fresh setup | Dependencies, configuration, migrations, synthetic seed, start, health and test call |
| Demo reset | Exact demo organization scope, dry-run summary, preserve unrelated data and credentials |
| Provider outage | Detect, suspend new AI admissions, transfer/fallback, preserve pending work |
| Stuck simulated payment | Inspect mock attempt/hold, exercise eligible authorized outcome, never record real payment; real-provider reconciliation deferred |
| Failed message | Inspect status, confirm recipient/consent, safe retry or staff contact |
| Worker recovery | Check lease/heartbeat, restart, verify backlog drains without duplicates |
| Backup/restore | Restore into isolated environment and verify bookings, RLS and jobs |
| Deployment rollback | Revert application safely with compatible schema; drain calls |
| Credential rotation | Rotate and validate provider/Auth/DB secrets; preserve callback verification needs |
| Incident | Owner, timestamps, affected tenant/calls, containment, recovery and corrective action |

Proposed demo recovery objectives: recover service within 30 minutes and use a verified backup no older than 24 hours. Test these against the actual selected hosting/database plan; they are not vendor guarantees or sufficient production targets.

## 12. Phases and subphases

Every checkbox below is initially incomplete. A phase closes only when its deliverables and exit gate have evidence. Build business correctness before expanding presentation polish. Security, audit events and failure handling begin with the first slice rather than being postponed to a final hardening sprint.

### Phase 0 — Product decisions and provider feasibility

Dependencies: explicit instruction to begin implementation. Estimated engineering effort: 2–4 days, excluding provider approval waiting time.

#### 0.1 Freeze the operating contract

- [ ] Confirm demo geography/timezone, English/Hindi, fee display, booking mode per doctor session, slot duration OR capacity, token/arrival policy, booking horizon and hold policy.
- [ ] Confirm demo date, available engineering time, budget, receptionist fallback availability and approved testers.
- [ ] Resolve the open decisions in Section 14; record owner and rationale in a decision log.
- [ ] Approve synthetic clinic data and administrative routing vocabulary.

Deliverable: signed-off decision sheet and requirement baseline.

#### 0.2 Verify external access early

- [ ] Verify available voice number, inbound reachability from tester phones, outbound reception transfer and provider account restrictions.
- [ ] Verify OpenAI STT/LLM/TTS model access, supported language behavior and actual audio/event formats.
- [ ] Define local mock payment success/failure/expiry controls and confirm no real payment-provider setup is required now.
- [ ] Verify WhatsApp sandbox enrolment or sender/template readiness and recipient consent requirements.
- [ ] Select and verify a supported SMS/WhatsApp code-delivery path for returning-caller access; appointment messaging eligibility does not automatically prove verification-delivery eligibility.
- [ ] Select deployment region/topology and record cost assumptions.

Deliverable: provider feasibility matrix with actual evidence, limitations and substitutes requiring an explicit scope decision.

#### 0.3 Run a bounded technical spike

- [ ] Prove real caller audio reaches STT and a short TTS response returns intelligibly.
- [ ] Prove audio clear, live-call redirect to reception, and initial/mid-call failure behavior.
- [ ] Measure rough voice latency and identify transcoding requirements.
- [ ] Record findings; keep throwaway spike code separate from product modules.

**Gate G0:** No untested provider assumption on the final demo's critical path. If geography or sender access blocks real delivery, resolve the demo setup before promising the capability. A browser voice substitute may support development but does not satisfy the final phone requirement.

### Phase 1 — Foundation, tenancy and authenticated skeleton

Dependencies: G0. Estimated effort: 3–5 days.

#### 1.1 Repository and runtime foundation

- [ ] Establish target repository layout, dependency locks, environment validation and formatting/type checks.
- [ ] Add API liveness/readiness, structured correlation IDs, safe error schema and web shell.
- [ ] Create CI and deterministic local/test startup.

#### 1.2 Database and tenant boundary

- [ ] Implement organizations, locations, departments, canonical doctors, assignments and memberships.
- [ ] Establish migration ownership, restricted runtime roles, RLS and tenant-safe composite references.
- [ ] Seed two distinct tenants and staff memberships with overlapping names for leakage tests.

#### 1.3 Authentication and access

- [ ] Implement login, token verification, membership resolution and role enforcement.
- [ ] Implement tenant switch with clear UI context; verify stale/removed membership behavior.
- [ ] Add audit foundation and operator access restrictions.

**Gate G1:** Authenticated staff can read only their clinic through API and UI; direct DB-policy and forged-reference tests fail closed. Fresh migration/seed works. No provider secrets enter browser bundles.

### Phase 2 — Scheduling and transactional booking core

Dependencies: G1. Estimated effort: 5–7 days.

#### 2.1 Scheduling

- [x] Implement weekly rules, exceptions, dated sessions, exact slots OR token capacity, generation and availability.
- [x] Add timezone/date boundary, breaks, inactive assignment and overlapping-rule validation.
- [x] Protect existing reservations during schedule edits.

#### 2.2 Patient and reservation services

- [x] Implement separate contacts, contact phones, patients, relationships, per-booking permissions and safe staff/current-session lookup; no phone/name-based patient merge.
- [x] Implement quote, consent, hold/release, fee snapshot and source tracking.
- [x] Enforce canonical-doctor session non-overlap, exact-slot uniqueness, token-session capacity, confirmation-time token counter, expiry and idempotency.
- [x] Test capacity 30 under 50 contenders, last-place contention, cancelled-token gaps, confirmation replay and manual bookings sharing inventory.
- [ ] Implement staff pay-at-clinic/waiver authorization and cancellation consequences.
- [x] Implement verification challenge storage/attempt/expiry rules and atomic existing-booking cancellation/reschedule services; target failure must preserve the original booking.

#### 2.3 Durable processing foundation

- [ ] Implement inbox/outbox/jobs, leases, bounded retries, expiry worker and audit writes.
- [x] Add typed booking API and service-level failure codes.
- [x] Run AI-versus-staff simulated contention and expiry/payment boundary tests.

**Gate G2:** Both booking modes pass: no exact-slot double booking, no token-session over-capacity, no duplicate/reused token; replays are stable; expired holds release even after worker delay; tenant and doctor-session invariants hold. No LLM is needed to prove booking correctness.

**Gate G2 status (2026-09-11): PASSED.** Evidence: `docs/phase-2/G2_EVIDENCE.md`.

### Phase 3 — Text agent and safe adaptive workflow

Dependencies: G2. Estimated effort: 5–7 days.

#### 3.1 Tool and state contracts

- [x] Implement typed tools over shared services with injected tenant context.
- [ ] Implement state patches, provenance, dependency invalidation, offer/consent versioning and checkpoints.
- [x] Add authenticated text-session harness with provider fakes.

#### 3.2 Adaptive graph

- [ ] Implement fast/guided/discovery routing and administrative information flow.
- [ ] Implement ambiguity, no-slot alternatives, patient/contact collection and explicit consent.
- [ ] Implement returning-caller verification, authorized upcoming-booking queries, family bookings, cancellation/reschedule/read-back and resend flows; use a clearly labelled fake verification sender for deterministic local tests.
- [ ] Add human request, medical boundary, urgent-risk script routing and bounded repair/tool loops.
- [ ] Implement stale-result handling and correction after a committed hold.

#### 3.3 Evaluate

- [ ] Build at least 60 labelled scenarios balanced across English/Hindi/Hinglish and both booking modes, including adversarial, language-switch and correction cases.
- [ ] Establish model/prompt/version and token/latency baseline.
- [ ] Fix every critical false confirmation, unsafe action or tenant failure.

**Gate G3:** Deterministic expected outcomes pass; live-model evaluation meets Section 10 in both languages/modes; every booking mutation has appropriate consent or authorized staff action and a traceable result. Fast-path calls do not repeat known fields.

### Phase 4 — Reception dashboard and organization setup

Dependencies: G2; G3 required before phase closure. Estimated effort: 4–6 days.

#### 4.1 Operations workflow

- [ ] Build appointment list/details, exact slots/session capacity, manual booking/walk-ins, token queue, check-in/call-next/skip/complete and permissions.
- [ ] Expose hold countdown, source, payment and delivery statuses, safe conflicts and error recovery.
- [ ] Add callback and exception queue skeletons.

#### 4.2 Configuration workflow

- [ ] Build locations/departments/assignments/schedules and exception editor.
- [ ] Build Create Clinic/Create Hospital onboarding, department defaults, session mode/capacity, English/Hindi voice/fallback settings and assisted integration setup status.
- [ ] Implement activation validation and configure the second clinic through UI.

#### 4.3 Usability and access verification

- [ ] Test keyboard, loading/empty/error/conflict states and desktop/tablet views.
- [ ] Test contact-name/patient-name separation, authorized family linkage, contact corrections, permission revocation and staff rescheduling through shared services.
- [ ] Test removed membership, forbidden actions and stale data refresh in the browser.
- [ ] Demonstrate AI text and staff bookings sharing slot/session capacity; disable LLM/STT/TTS access and prove staff booking/queue management still works.

**Gate G4:** A receptionist completes core tasks without developer/database assistance. Both channels see consistent availability and appointment state. No fake completed provider statuses are displayed.

### Phase 5 — Simulated payments and real messaging

Dependencies: G3 and G4. Estimated effort: 2–3 days.

#### 5.1 Local payment simulator

- [ ] Implement `MockPaymentProvider` with explicit pending/simulated success/failure outcomes; no real checkout or payment credentials.
- [ ] Add authenticated tenant-scoped operator controls behind server demo mode; no agent/public mark-paid permission.
- [ ] Test duplicate success, failure/retry, expiry and cancelled-hold outcomes through the real booking transaction and token allocator.

#### 5.2 Messaging

- [ ] Configure permitted sandbox/template flow and consented demo recipients.
- [ ] Integrate the G0-selected real verification-delivery channel and prove challenge redaction, expiry/replay/throttling and saved-contact binding; transfer on delivery failure.
- [ ] Send hold/booking confirmations with exact time OR session window/token, minimal data, simulated-payment disclosure and tracked delivery; no real payment link.
- [ ] Add retry/unknown-send handling and staff-visible failure reason.

#### 5.3 Prove the asynchronous journey

- [ ] Run text → hold → authenticated simulated success → confirmation/token → real delivered message.
- [ ] Repeat with hangup, message failure, simulated event replay, worker restart and simulated success after expiry.
- [ ] Prove notification failure leaves valid booking state intact.

**Gate G5:** Local simulated success confirms the correct booking/token once; unauthorized simulator access and expired/cancelled holds fail; approved recipient receives real messages labelled accurately. No Razorpay integration, keys or money movement required.

Deferred payment work (separate later release): verify Razorpay access and implement Section 6.4's link, signed webhook, reconciliation and late-payment review controls. Close PAY-01/PAY-02 then; they are not current P0 gates.

### Phase 6 — Production-shaped telephone integration

Dependencies: G5 and the Phase 0 spike. Estimated effort: 5–8 days.

#### 6.1 Secure streaming gateway

- [ ] Implement signed webhook/WebSocket binding and endpoint tenant resolution.
- [ ] Integrate STT/TTS adapters, codecs, audio pacing, speech activity and finalized-turn ordering.
- [ ] Add queue bounds, timeout/cancellation handling, session cleanup and AI disclosure.

#### 6.2 Natural conversational behavior

- [ ] Implement barge-in, playback marks, response generation IDs and stale work reconciliation.
- [ ] Test Hindi/Hinglish names, numbers, dates, code-switching and telephone noise.
- [ ] Implement silence prompts, maximum duration, caller disconnect and unsupported-language behavior.

#### 6.3 Complete real-call journey

- [ ] Place real English/Hindi phone calls through both booking modes and finish the simulated confirmation flow.
- [ ] Book for two family members from one named contact, call back, verify once, query only permitted bookings, cancel one and reschedule the other; reject unverified/unauthorized access.
- [ ] Measure end-of-speech latency and interruption response at 1/3/5 concurrent calls; benchmark higher tiers only within budget/quotas and publish actual tested capacity.
- [ ] Verify simultaneous calls never mix audio, state, tenant or patient details.

**Gate G6:** External phone bookings work end to end with actual adapters and measured voice targets. Audio fixtures and real-call findings are recorded. Browser-only or prerecorded paths do not close this gate.

### Phase 7 — Human handoff and resilience closure

Dependencies: G6; foundational fallback exists since Phase 0. Estimated effort: 3–5 days.

#### 7.1 Transfer experience

- [ ] Implement explicit-request/repeated-failure handoff using tested live-call control.
- [ ] Display minimum necessary handoff summary and actual dial result.
- [ ] Handle busy/no-answer/closed reception and consented callback requests.

#### 7.2 Independent fallback and recovery

- [ ] Configure fallback independent of the main application/database.
- [ ] Kill primary webhook, live stream process, STT/TTS/model access and database in separate tests.
- [ ] Verify courteous outcomes, truthful state, no repeated charging/link creation and durable job recovery.

#### 7.3 Operational controls

- [ ] Add tenant AI disable switch, admission limits, worker heartbeat, backlog alerts and cost thresholds.
- [ ] Complete mock payment state recovery, message reconciliation and runbooks; real payment reconciliation is deferred.

**Gate G7:** Primary application failure and mid-call failure have separately demonstrated outcomes. Transfer is counted successful only on answer. Persisted bookings/payments survive tested restarts without invariant violations.

### Phase 8 — Release validation and demonstration

Dependencies: G1–G7. Estimated effort: 3–5 days.

#### 8.1 Acceptance and deployment

- [ ] Run the complete functional, tenant, concurrency, provider, voice and safety suites.
- [ ] Deploy to the selected demo environment with separate secrets and migration controls.
- [ ] Run five-call load/soak, backup restore and application rollback checks.
- [ ] Review retention, access, logs and final known limitations.

#### 8.2 Demo readiness

- [ ] Prepare synthetic exact slots and capacity-30 token sessions, authorized simulator operator, enrolled WhatsApp recipients and an available receptionist.
- [ ] Rehearse Section 15's calls and failure scenarios on the actual network.
- [ ] Prepare a labelled recording as contingency evidence, never as a substitute presented as live.
- [ ] Complete traceability table, evidence links and final product-owner review.

**Gate G8:** Every current P0 has passing evidence; no critical defects; four main calls, both booking modes, manual queue/AI-independent operation, simulated confirmation, English/Hindi, contention and fallback are reproducible. Publish tested concurrent-call capacity. Real Razorpay requirements remain explicitly deferred. Deliver source, configuration guide, tests/evaluations, runbooks, demo access and limitations report.

## 13. Execution rules, estimates, and dependencies

### 13.1 Dependency chain

```text
G0 feasibility
 -> G1 foundation/tenancy
 -> G2 scheduling/booking
 -> G3 text agent
 -> G4 dashboard
 -> G5 simulated payment / real messaging
 -> G6 live voice
 -> G7 resilience
 -> G8 final acceptance
```

Dashboard implementation can start after G2; provider onboarding can progress during other engineering work. Keep gate order for integrated acceptance. The early voice spike reduces feasibility risk while the full voice build waits for a working text/payment workflow.

### 13.2 Effort envelope

With local payment simulation, the base phase ranges total **32–50 focused engineering days**. Allow another **3–5 days** across Phases 2–4/8 for the second booking mode, capacity/token invariants and manual queue acceptance: approximately **35–55 focused engineering days** before external approval delays and contingency. Add 20–30% for integration surprises and learning. This is an engineering estimate, not a delivery promise. Re-estimate after G0/G3; real Razorpay work is excluded and estimated when requested.

Revision 1.2 adds approximately **4–7 days** across Phases 2–6/8 for contact/permission separation, real verification delivery, returning calls and atomic rescheduling. Revised total allowance: **39–62 focused engineering days**, before the stated contingency and external waiting time. This does not open additional phases; distribute that allowance within the existing phase sequence.

If the presentation deadline is shorter, reduce optional scope explicitly and preserve tenant safety, booking correctness and truthful provider state. Do not relabel a mocked integration as complete. A staged text-workflow milestone is useful but does not satisfy the final live-voice product.

### 13.3 Work-item template

Every implementation task should record:

```text
ID / phase / requirement IDs:
User-visible outcome:
Dependencies:
In scope / out of scope:
Schema/API/state contracts affected:
Acceptance examples, including failure paths:
Verification commands or evaluation cases:
Evidence location:
Migration/recovery implications:
Status / remaining defects:
```

Keep a progress ledger with `not started`, `in progress`, `blocked`, and `verified`. Link actual test output/demo evidence. Do not check boxes merely because files exist.

### 13.4 Definition of done for each phase

- Requirements and chosen decisions are reflected in code, migrations and tests.
- Relevant happy and failure paths pass; known limitations are written down.
- Tenant/authorization boundaries are tested for new entrypoints.
- No secrets or real patient data enter repository/evaluation fixtures.
- Operational events allow diagnosis without exposing sensitive content.
- Documentation and API contracts match the final behavior.
- No unresolved defect that could cause wrong-patient booking, cross-tenant access, false payment confirmation or unhandled critical safety response.

A baseline approval does not require a new permission request for every routine implementation choice once implementation is authorized. Escalate product-policy changes, new external commitments or unresolved blockers with a concrete proposed resolution.

## 14. Risk register and open decisions

### 14.1 Key risks

| Risk | Impact | Mitigation / trigger |
| --- | --- | --- |
| Assumed local phone number unavailable | Live demo cannot receive intended calls | Verify actual reachable number and transfer geography in G0 |
| WhatsApp approval or sandbox restrictions | Link cannot reach caller | Start setup early; enroll designated testers; disclose sandbox limits |
| Voice latency or weak local-name transcription | Unnatural or incorrect conversations | Early spike, audio evals, terminology hints, codec tests and measured budgets |
| Hold/confirmation race | Simulated success confirms unavailable capacity | Locked confirmation and expiry checks now; real money/late-payment review deferred |
| Token count confused with capacity | Overbooking or renumbering | Separate capacity/occupancy/counter; cancellations release places but never reuse tokens |
| Shared doctor/data design leaks tenant info | Unauthorized access | Minimal global directory, assignment scoping and opaque conflict responses |
| Model invents facts or actions | Wrong booking or unsafe response | Typed tools, verified facts, consent snapshots, server checks and adversarial evals |
| Interrupted mutation still completes | Stale booking/payment operation | Versioning, idempotency and committed-outcome reconciliation |
| Independent fallback is not truly independent | Dead call during outage | Provider-hosted/static routing and separate failure drills |
| Overbuilding enterprise infrastructure | Prototype never reaches end to end | Modular monolith, bounded capacity and P0 gate discipline |
| Provider timeout creates duplicates | Multiple links/messages | Unknown states, lookup, dedupe where supported and staff review |
| Worker stops while API appears healthy | Holds/messages stuck | Heartbeats, backlog metrics, leases and reservation-time expiry |
| Small evaluation set creates false confidence | Demo succeeds but real users fail | Held-out cases, repeated runs, synthetic scope and separate real-use review |

### 14.2 Decisions to close before dependent work

| ID | Decision | Proposed default | Owner / deadline |
| --- | --- | --- | --- |
| D01 | Clinic country and location timezone | India, `Asia/Kolkata`; no assumed local AI-number prefix | Confirmed / G0 |
| D02 | Presentation date and available effort | Use phase estimate until a date is supplied | Product owner / G0 |
| D03 | Provider/deployment budget | Set daily test and total demo cap | Product owner / before billable spike |
| D04 | Reachable voice number and transfer destination | Use the assigned VoiceLink Indian DID and verify the human fallback route | Prototype configured / G0 |
| D05 | WhatsApp sandbox versus approved sender | Required for initial demo; account/sender route must be tested | Feasibility dependency / G0 |
| D06 | Languages and representative speaker tests | English and Hindi required, Hinglish and switching covered | Confirmed scope; fixtures / G0 |
| D07 | Fees/display currency and hold duration | INR; local simulated payment; 10-minute hold; amount TBD | Partial / G0 |
| D08 | Staff exceptions | Pay-at-clinic allowed by policy; waiver admin only | Product owner / G2 |
| D09 | Shared canonical doctor administration | Platform-managed canonical fields; tenant-local assignment fields | Product owner / G1 |
| D10 | Patient disambiguation/contact consent | No phone-only merge; minimum volunteered identity | Product owner / G2 |
| D11 | Routing and urgent-risk response copy | Clinic-reviewed before real patient use; labelled synthetic scripts for demo | Clinic reviewer / G3 |
| D12 | Hosting region and recovery capabilities | Always-on WebSocket host near chosen providers/database | Engineer + owner / G0 |
| D13 | Provider models/versions | Select through access and multilingual latency evaluation | Engineer / G0, lock at G3/G6 |
| D14 | Real patient use | Out of scope for demo; separate operational/privacy/clinical review | Product owner / future release |
| D15 | Booking mode for first demo doctor | Session/token 4–6 PM, capacity 30; doctor/location/days/arrival note TBD; also support exact-time sessions | Partial / G0 |
| D16 | Token allocation and arrival policy | Token at confirmation, never reused; checked-in token order; no exact wait promise | Product owner / G2 |
| D17 | Concurrent-call admission limit | Start by validating five; final limit from Section 10.5 tests | Engineer / G6–G8 |
| D18 | Organization setup | Create Clinic / Create Hospital using shared schema and appropriate department defaults | Confirmed scope / G4 |
| D19 | Contact/patient model | Separate contact name/phone from each patient; booking-scoped permissions; no automatic full-history access | Confirmed scope / G2 |
| D20 | Returning-caller verification | Saved-contact challenge before existing details/changes; SMS/WhatsApp mechanism must be tested | Policy baseline; provider decision / G0 |
| D21 | Cancel/reschedule eligibility | Proposed 30-minute cutoff; unchanged fees; atomic replacement preserves original on failure | Product policy default / G2 |

### 14.3 Country/provider constraints that change the original proposal

The configured `+91` VoiceLink DID is the prototype telephony route. Inbound caller-to-agent audio, outbound caller ID, fallback transfer, and emergency-call limitations must be verified with the actual account before production use.

WhatsApp self-sign-up includes business verification requirements, and provider documentation notes that verification can take weeks. Use the applicable sandbox/approved-template path for the demo and record its limitations; same-number voice/WhatsApp remains optional. [Twilio WhatsApp self-sign-up](https://www.twilio.com/docs/whatsapp/self-sign-up)

All targets, schemas and policies in this PRD are proposed engineering decisions. External-provider claims are limited to the cited documents; actual account entitlement and end-to-end behavior must be demonstrated in G0 and release tests.

## 15. Final acceptance and demonstration

### 15.1 Four main calls

| Demo | Setup | What must be observable |
| --- | --- | --- |
| Fast path | Unique doctor with available exact slot or token session | Extract known fields, explain booking mode, minimal clarification, consent, hold and simulated confirmation |
| Guided/discovery | Caregiver describes a lay concern | Approved non-diagnostic routing, useful clarification and real doctor options |
| Ambiguous request | Similar doctor names or unclear date/time | Preserve ambiguity, clarify, avoid incorrect booking; demonstrate correction |
| Human assistance | Caller explicitly requests reception | AI stops, reception answers, outcome and minimal handoff summary visible |

After a booking call, an authenticated demo operator chooses “Simulate success.” Show the simulated event, exactly one confirmation, the exact time OR session/token, updated dashboard and real message to the enrolled recipient. State clearly that no payment was collected. Also show failure/expiry. Real Razorpay integration is outside this release.

### 15.2 Enterprise behavior demonstrations

- [ ] Show the second tenant's different greeting/data and failed cross-tenant access.
- [ ] Have AI and staff compete for one slot; one wins and the other receives alternatives.
- [ ] Fill a capacity-30 session with mixed AI/manual bookings; the 31st active reservation fails; a cancellation frees one place without renumbering tokens.
- [ ] Demonstrate Create Clinic/Create Hospital setup and manual check-in/call-next with AI services disabled.
- [ ] Demonstrate English, Hindi and a mid-call language switch; publish measured simultaneous-call capacity.
- [ ] Demonstrate Aryan's separate contact profile booking for mother/father, verified recall/query, cancellation/reschedule and denied access to an unrelated booking.
- [ ] Expire an unpaid hold and show capacity returns.
- [ ] Replay an authorized simulated-success event without duplicating confirmation, token or message jobs.
- [ ] Attempt simulated success after expiry and show rejection without reclaiming slot/session capacity.
- [ ] Interrupt spoken slot options and verify corrected selection.
- [ ] Disable the primary application and demonstrate the independently configured reception route.
- [ ] Restart a worker with pending jobs and show recovery.
- [ ] Show call latency, outcome, provider mode and estimated usage from real instrumentation.

### 15.3 Release evidence matrix

| Evidence artifact | Covers |
| --- | --- |
| Tenant/auth test report | TEN-01/02, IAM-01, SEC-01 |
| Scheduling/contention report | DOC-01, SCH-01/02, QUE-01, BKG-01/02 |
| Patient/contact and bilingual conversation evaluation report | PAT-01/02, RET-01/02, CHG-01, AGT-01/02/03, LNG-01, SAFE-01 |
| Simulation contract tests and real message delivery report | SIM-01, MSG-01; PAY-01/02 deferred |
| Phone/audio/transfer recordings or consented observation notes | VOI-01/02, HUM-01 |
| Staff browser journey and AI-off manual operations report | UI-01/02, ONB-01, QUE-02 |
| Recovery/load/restore report and runbooks | OPS-01, DEM-01 |
| Correlated trace/latency/cost sample | OBS-01 |

Final handover includes this updated PRD, decision log, source and migrations, environment template, synthetic seed/reset instructions, automated tests, evaluation fixtures/results, deployment/recovery runbooks, demo script and explicit limitations.

**The end goal is achieved when a real caller can reliably obtain a correct appointment through the AI, a receptionist can operate the same system, payment and communication outcomes are truthful, tenant boundaries hold, and failures reach a recoverable state—with evidence for every P0 requirement.**

## 16. Official references

Reviewed for planning on 10 September 2026. Recheck relevant SDK/protocol details when implementing; account access, pricing and geographic availability are not established by documentation alone.

- [OpenAI realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription) — transcription-only realtime integration.
- [OpenAI text to speech](https://developers.openai.com/api/docs/guides/text-to-speech) — speech generation and AI-voice disclosure.
- [Twilio Media Streams WebSocket messages](https://www.twilio.com/docs/voice/media-streams/websocket-messages) — media, mark and clear protocol.
- [Twilio Connect](https://www.twilio.com/docs/voice/twiml/connect) — stream/call-control integration context.
- [Twilio India Voice Guidelines](https://www.twilio.com/en-us/guidelines/in/voice) — locale-specific voice constraints.
- [Twilio WhatsApp self-sign-up](https://www.twilio.com/docs/whatsapp/self-sign-up) — sender setup and verification dependencies.
- [Razorpay webhook validation](https://razorpay.com/docs/webhooks/validate-test/?preferred-country=IN) — signature and duplicate-event handling.
- [Razorpay webhook best practices](https://razorpay.com/docs/webhooks/best-practices/?preferred-country=IN) — retries and event ordering.
- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security) — policy enforcement and privileged-role boundaries.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) — checkpoint persistence concepts.
- [Twilio Media Streams overview](https://www.twilio.com/docs/voice/media-streams) — per-call stream limits, separate from application concurrent capacity.
- [OpenAI rate limits](https://developers.openai.com/api/docs/guides/rate-limits) — verify actual provider quotas before capacity tests.
