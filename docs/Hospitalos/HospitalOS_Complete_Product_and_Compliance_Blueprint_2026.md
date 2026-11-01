**HOSPITALOS**

**Complete Product, Workflow, Agent Architecture & Compliance Blueprint**

Emergency hospital discovery • Verified resource matching • Receiving-hospital acceptance • AI operations task force

VERSION 1.0 \| 01 NOVEMBER 2026 \| INDIA-FIRST HACKATHON / PRODUCT DESIGN

> **EXECUTIVE POSITION**
> HospitalOS is an operational coordination layer. It assists patients/families and receiving hospitals with verified capabilities, capacity information, request/response workflows, and administrative preparation. It is not an emergency dispatch authority, a triage system, or an autonomous clinical decision-maker.

## What is already built

A functioning multi-tenant, multi-doctor, multi-department appointment system and AI voice receptionist. People can call, retrieve appointment information, find a doctor/department, and book an appointment. This must be preserved and shown as one specialist capability of the larger platform.

## What this version adds

A hospital resource manager; a public emergency hospital finder with affordability preferences; explainable resource-aware matching; a request-to-receive workflow with a response timer and human hospital acceptance; real-time case tracking; a narrowly scoped supervisor and agent-task display.

## Delivery boundary

This version ends when the receiving hospital has confirmed its willingness and capacity to prepare for arrival and the requester receives the reference ID, contact, and navigation information. Registration, triage, treatment, formal admission, discharge, hospital-to-hospital transfers, and general-purpose autonomous administration are later phases.

Scope note: This is an engineering and regulatory-readiness blueprint, not a legal opinion, emergency-care protocol, product certification, or proof that live hospital feeds are available. Hospital-specific policies and state law must be validated before deployment.

# Contents

01 Executive decisions and non-negotiable rules

02 Personas, tenants and responsibility boundaries

03 Real patient journey: ambulance to hospital

04 User-facing emergency workflow

05 Hospital acceptance, timer and fallback

06 Resource manager and hospital data dictionary

07 Eligibility, recommendation and affordability logic

08 Resource holds, concurrency and lifecycle

09 AI task force and operational workflows

10 Platform architecture and integration plan

11 Data model, API contracts and event taxonomy

12 User experience and screen specifications

13 India regulatory and policy mapping

14 Security, privacy and incident management

15 Failure handling and acceptance-test matrix

16 Hackathon build plan and demo script

17 Roadmap, KPIs, risks and open decisions

18 Official source register

> **HOW TO READ**
> [LAW] is a cited legal requirement within its stated applicability; [STANDARD] is voluntary/guidance unless adopted into policy or contract; [PRODUCT RULE] is a design requirement proposed here; [ASSUMPTION] needs validation; [DEMO] uses synthetic hospital/patient data.

# 01 Executive decisions and non-negotiable rules

> **PRODUCT THESIS**
> Existing hospital command centers make operational state visible; HospitalOS makes that state actionable through verified resource requests, controlled acceptance, deterministic reservations, and an AI coordination layer.

- P01. No clinical diagnosis, acuity classification, or medical routing decision by the AI. Known clinical requirements may be entered by qualified personnel only.

- P02. Never delay emergency care to complete registration, payment, price selection, app confirmation, or optional forms. Display call-emergency-services guidance visibly.

- P03. Hospital acceptance is ALWAYS by an authorized receiving person in the hackathon MVP. No automatic acceptance or default acceptance on timeout.

- P04. A pre-arrival acceptance, a resource hold, an EMS destination decision, and a clinician-issued admission order are four distinct states.

- P05. Resource matching must use verified operational inputs. Unknown or stale capacity is not “available.”

- P06. Resource reservations, authorization checks, scoring eligibility, and case state changes are deterministic backend responsibilities, not LLM decisions.

- P07. Affordability may influence the order of otherwise clinically/operationally appropriate options, but must not obscure essential emergency-care options.

- P08. A public or private ambulance/family user can use the app without a dispatch integration. EMS clinical routing protocols remain authoritative.

- P09. No live claimed capacity for unconnected hospitals; clearly label unverified listings, last update, and simulations.

- P10. All demo cases and names are synthetic; no real patient or ambulance data is used.

## In scope / not in scope

| **Build for event**                                 | **Explicitly defer**                                   |
|-----------------------------------------------------|--------------------------------------------------------|
| Synthetic three-hospital network + branch resources | Actual 102/108/112 dispatch integration                |
| Emergency matching and explainable availability     | AI triage/diagnosis or autonomous EMS routing          |
| Admin request acceptance/decline/timeout/fallback   | Guaranteed admission or emergency treatment outcome    |
| Live state, updates, conflict handling              | Complete hospital HMS/ERP or insurance workflow        |
| Supervisor + focused agent activity                 | Free-form creation of unlimited autonomous agent teams |
| Existing voice receptionist demo                    | Rebuilding the appointment system                      |

# 02 Personas, tenants and responsibility boundaries

Tenancy: a healthcare network/organization owns several hospital branches. Each branch owns its resource feed, emergency receiving rules, and administrators. Public discoverability is a separate listing permission; data isolation is mandatory.

| **Role**                  | **Can do**                                                                               | **Cannot do**                                                     |
|---------------------------|------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| Patient / family          | View relevant hospitals; supply location/preferences; submit and track receiving request | Self-assign acuity; override triage or reserve resources directly |
| Ambulance / helper        | Supply ETA and information when appropriate; use receiving coordination                  | Override EMS protocols or claim the app is dispatch               |
| Hospital emergency admin  | Review capacity; accept/decline; confirm resource state; send receiving instructions     | Make clinical decisions without authorized role                   |
| Hospital resource manager | Update equipment/bed/readiness states and validate holds                                 | Accept hospital receiving cases unless separately authorized      |
| Hospital clinician/EMS    | Set medical capability requirements and clinical decisions per institution/protocol      | Bypass audit or resource state consistency                        |
| Network operations lead   | See authorized cross-branch aggregate data, escalate issues                              | View patient details beyond explicit authorization                |
| AI supervisor             | Delegate approved tasks and explain verified results                                     | Diagnose, admit, accept, route, override locks                    |
| Platform admin            | Manage accounts, synthetic demo settings, operational availability                       | Read unrelated tenant patient information by default              |

> **CRITICAL SEPARATION**
> Use tenant_id + hospital_id + explicit scopes everywhere. Hospital staff should see only cases directed to their facility or explicitly delegated within their network. Public users never receive patient data about other users.

# 03 Real patient journey: ambulance to hospital

Typical clinical pathway: emergency entrance/ambulance bay -\> ambulance or accompanying-person handover -\> qualified triage -\> emergency evaluation, stabilization and investigations -\> observation, discharge, clinical admission to ward/ICU/OT, or appropriate transfer. Registration/documentation may run in parallel; there is no universal paperwork-first sequence. \[R4\] \[R5\] \[R11\]

| **Clinical stage**                            | **Primary owner**                 | **HospitalOS support now / later**                                |
|-----------------------------------------------|-----------------------------------|-------------------------------------------------------------------|
| Pre-arrival request                           | Family/ambulance + receiving team | NOW: facility capability + receiving request; no acuity inference |
| Handover at entrance                          | EMS / receiving emergency staff   | LATER: structured handover packet                                 |
| Clinical triage                               | Qualified clinician/triage staff  | NEVER AI triage; may display already-entered category             |
| Emergency assessment/stabilization            | Emergency team                    | No blocking on paperwork, payment or app                          |
| Registration / identity                       | Registration staff                | LATER: assist with known details, unidentified-patient support    |
| Disposition: observe/admit/transfer/discharge | Treating clinician                | LATER: initiate operational workflows only upon order             |
| Inpatient bed assignment                      | Authorized bed manager            | LATER: resource bundle allocation and approvals                   |

## Emergency receiving is not inpatient admission

An emergency bay/resuscitation space is different from ICU or ward bed capacity. A hospital with no ICU bed may still provide emergency assessment/stabilization within its capabilities; a free ICU bed does not authorize direct admission. The clinical team determines the next disposition.

## Paperwork and identity rules

- Optional pre-arrival fields: case reference, approximate patient age band, family contact, estimated arrival, structured EMS information if supplied by an authorized source.

- Never make Aadhaar, ABHA, full name, payment, insurance or signature mandatory before a time-critical emergency receiving request.

- When formal admission is ordered later, the hospital may require more documents, policies and valid consent; AI can prefill, not fabricate signatures or replace informed clinical consent.

- For minors, unconscious patients, unidentified patients and medico-legal cases, use hospital and applicable legal protocols. Do not assume an accompanying person is automatically authorized to make every decision.

# 04 User-facing emergency workflow

## Step-by-step

- 1\. Entry: prominent “Find Emergency Care” with “Call 112 / local emergency services” visible. Accessible on mobile, low bandwidth, Hindi/English-ready.

- 2\. Location: geolocation with permission or manual locality/pincode; do not require GPS.

- 3\. Preferences: affordable/government preferred, private preferred, no cost preference; optional distance radius, default auto-expand if none match.

- 4\. Requirements: ordinary user chooses “I do not know” rather than guessing medical acuity; authorized EMS/clinician may specify ICU-capable, obstetric, trauma, pediatric or necessary resources.

- 5\. Candidate discovery: eligibility + resource freshness + estimated road travel time + cost preference; show factual reasons and unknowns.

- 6\. Facility selection: choose suitable option; show verification statement “capacity confirmation not yet received.”

- 7\. Request creation: one active formal receiving request; send to authorized hospital emergency admin; track countdown.

- 8\. Result: accepted -\> confirm status and arrival instructions; declined/expired -\> refresh and offer next suitable option; no dangerous waiting loop.

- 9\. Post-selection: direction/contact and advice to continue necessary emergency care; request cancellation and updated ETA are supported.

> **AFFORDABILITY RULE**
> Never use small/medium/large hospital as a proxy for price. Use hospital ownership/category plus verified affordable-services/insurance/scheme attributes. Preserve access to medically appropriate care even when affordability is a concern.

# 05 Hospital acceptance, timer and fallback

## Receiving request state machine

DRAFT -\> MATCHED -\> REQUEST_PENDING -\> {ACCEPTED, DECLINED, EXPIRED, WITHDRAWN} -\> (after revalidation) RECEIVING_CONFIRMED / HOLD_FAILED -\> DETAILS_SHARED -\> ARRIVAL_REPORTED (optional). Rejection/expiry can create a new versioned request after refreshed matching.

| **Event**                    | **System reaction**                                                                                          | **Owner of decision**           |
|------------------------------|--------------------------------------------------------------------------------------------------------------|---------------------------------|
| Patient chooses candidate    | Create idempotent request + push notification; start 30s response window                                     | User requests; backend executes |
| Admin accepts                | Authenticate staff + recheck data; record accepted_by and timestamp; optionally attempt atomic resource hold | Authorized hospital admin       |
| Admin declines               | Capture short reason code, notify user, refresh candidate list                                               | Authorized hospital admin       |
| 30s timeout                  | Mark expired; optionally remind once; provide fallback; no auto-accept                                       | Backend timer                   |
| Late acceptance arrives      | Reject stale version; ask for a new request instead of silently confirming                                   | Backend                         |
| Resource changed before hold | Fail reservation and mark not confirmed; escalate to admin                                                   | Transactional service           |
| User cancels                 | Withdraw case and release eligible provisional hold                                                          | User + policy-checked backend   |
| Duplicate request/replay     | Return same result via idempotency key                                                                       | Backend                         |

## Timing policy

The 30-second acceptance timer is a DEMO / configurable product policy, NOT a universal EMS standard. For presentation, shorten to 8-10 seconds. A timeout means “no confirmation received,” not “hospital unable to give emergency care.” Never require a patient or ambulance to wait for a countdown before seeking urgent care.

## Fallback protocol

Primary: request Hospital B; A and C may receive read-only availability queries, not simultaneous reserved acceptance cases. Upon decline/timeout, refresh eligibility, request next candidate (with consent or configured low-risk permission), and show call/emergency alternatives. Receiving confirmation does not by itself direct the ambulance or guarantee a bed.

# 06 Resource manager and hospital data dictionary

HospitalOS needs verified branch-level operational status, not an invented “available beds” answer. Initial Resource Manager screens let authorized staff update data manually; future adapters can ingest hospital systems.

| **Domain**           | **Minimum fields for MVP**                                             | **Important meaning**                                         |
|----------------------|------------------------------------------------------------------------|---------------------------------------------------------------|
| Hospital             | hospital_id, tenant_id, facility type, address, coordinates, contact   | Verified ownership; opt-in listing                            |
| Emergency service    | receiving_active, 24x7 flag, capabilities, contact, last_verified      | Emergency assessment service independent of ward availability |
| ED space             | emergency bays, ready/occupied/blocked/held                            | Receiving availability is not inpatient admission             |
| ICU / beds           | total, staffed_ready, occupied, held, cleaning, out_of_service         | Free physical bed ≠ clinically ready bed                      |
| Equipment            | type, ready, broken, maintenance, last_checked                         | Device capability verified by authorized hospital             |
| Staff                | receiving coverage role, status, shift validity                        | No public exposure of staff private rosters                   |
| Cost information     | government/charitable/private, published rates and schemes if verified | Never promise treatment price or eligibility                  |
| Readiness evidence   | source, verified_by, observed_at, expires_at, version                  | Unknown/stale shown as not verified                           |
| Admin receiving desk | on-duty authorized role, channel, response hours                       | Acceptance needs a real accountable operator                  |

## State vocabulary

Resources: AVAILABLE_READY, REQUESTED, HELD, OCCUPIED, CLEANING, BLOCKED, OUT_OF_SERVICE, UNKNOWN. Separate clinical service capability (supports ICU) from capacity (one staffed ICU bed ready) and from case acceptance (admin accepted this request).

## Freshness

Every live resource claim stores source, observed_at, verified_by, version and a configured freshness threshold. Initial suggested demo threshold: 60 seconds for frequently changing bed state; this is NOT a certified requirement. If stale: badge “Needs reconfirmation,” exclude from “confirmed ready” counts and block automatic holds pending refresh.

# 07 Eligibility, recommendation and affordability logic

## Eligibility filter before ranking

- Required emergency service is operating (where a formal receiving confirmation is requested).

- Clinician/EMS-specified required service/capability is supported, if such a requirement exists.

- Required resources and staffing are verified ready, if a ready-resource match is claimed.

- Resource data is fresh enough for the particular claim; stale hospitals may be shown as “verify directly,” not falsely ranked as confirmed ready.

- The candidate can receive a formal request through an authorized desk. If not, display “contact facility” rather than implying acceptance is possible.

## Ranking after filtering

Use road ETA as a leading factor, then readiness, confirmed capacity/ability to respond, and patient affordability preference. A transparent demo score can be: 45% travel ETA + 30% current readiness + 15% response/data reliability + 10% affordability preference. These percentages are arbitrary product-demo weights, NOT clinical rules, and should be approved or replaced by local EMS/medical governance before real use.

## Statuses and explanation language

| **Display status**                        | **When to show**                                                          | **Not allowed to imply**                              |
|-------------------------------------------|---------------------------------------------------------------------------|-------------------------------------------------------|
| Suitable candidate – request confirmation | Verified required capability + live operational status                    | Guaranteed care / bed / admission                     |
| Needs verification                        | Known relevant service but current status stale or incomplete             | Resources confirmed available                         |
| Does not meet specified requirement       | Verified absence of a requested clinician-defined capability/resource     | Hospital cannot provide any emergency assessment      |
| Receiving confirmed                       | Authorized hospital accepted current request; any hold separately checked | EMS has approved reroute; inpatient admission ordered |

## Unknown condition rule

If a relative says “my father is unconscious,” the app must urge urgent emergency contact, not infer an ICU or specialty requirement. Do not ask patients to select clinical severity scores. The app may filter known emergency-service capabilities and present direct contacts while qualified medical staff determine care needs.

# 08 Resource holds, concurrency and lifecycle

A resource hold is optional for the MVP but important as a robust design. An admin acceptance and a bed hold must be separate audited events. A hold is provisional; clinical admission/priority rules can supersede it according to approved hospital policies.

| **Transition**                            | **Guard**                                                                       |
|-------------------------------------------|---------------------------------------------------------------------------------|
| AVAILABLE_READY -\> HELD                  | Authorized acceptance; fresh staff/equipment checks; database lock + uniqueness |
| HELD -\> CONFIRMED                        | Receiving-team confirmation and case still current                              |
| HELD -\> EXPIRED                          | TTL/reconfirmation policy applied; no active authorized override                |
| HELD -\> RELEASED                         | Case canceled/invalidated; audited release                                      |
| HELD -\> INVALIDATED                      | Equipment/bed/staff capability lost; notify human and supervisor                |
| CONFIRMED -\> OCCUPIED                    | Actual clinical/resource handoff recorded by staff                              |
| OCCUPIED -\> CLEANING -\> AVAILABLE_READY | Authorized operational updates                                                  |

## Atomicity / database safety

Use PostgreSQL transaction and SELECT ... FOR UPDATE on selected resource; verify state and matching case; create hold + resource state in same transaction. Add a partial uniqueness invariant for active holds and idempotency keys for API retries. Never allow the LLM to write resource availability directly.

> **TWO-AMBULANCE TEST**
> Two synthetic emergency cases request ICU-B12 at the same instant. Exactly ONE hold must succeed and the other must receive RESOURCE_ALREADY_HELD, then be replanned. This is stronger evidence than an animated agent conversation.

# 09 AI task force and operational workflows

The existing voice receptionist remains an independent specialized capability. Emergency coordination uses a supervisor with narrow specialist tasks and deterministic tools. A “real agent” chooses tools/actions within policy when information changes; routine search, scoring, locks, timers and logging stay as ordinary services.

| **Component**               | **Autonomy**                                                               | **Permitted tools / outputs**                                       |
|-----------------------------|----------------------------------------------------------------------------|---------------------------------------------------------------------|
| Supervisor Agent            | Plan/delegate permitted operational work; monitor, replan, explain         | read_case, get_candidates, create_agent_task, request_human_review  |
| Resource Specialist         | Investigate conflicts, stale information, missing resource coverage        | get_resources, refresh_resource_status, create_verification_request |
| Matching Specialist         | Explain deterministic candidate eligibility/ranking                        | get_ranked_candidates; no clinical weights or direct routing        |
| Coordination Specialist     | Prepare and track hospital requests and follow-ups                         | send_request, check_status, notify_staff within policy              |
| Voice Front Desk (existing) | Handle appointments and doctor/department questions                        | existing approved booking/search tools; future handoff              |
| Admission Agent (later)     | Administrative document preparation AFTER clinician-led admission workflow | draft_registration; never approve admission                         |
| Delegation Agent (future)   | Low-risk policy-bounded actions only                                       | scoped requests/reminders; no autonomous clinical acceptance        |

## Approval matrix

| **Action**                                  | **Auto**                                          | **Requires human**                            |
|---------------------------------------------|---------------------------------------------------|-----------------------------------------------|
| Refresh bed inventory / explain discrepancy | Yes, read-only                                    | No                                            |
| Notify a receiving admin / remind once      | Yes within site policy                            | Not necessarily                               |
| Create formal acceptance request            | Yes after user action or explicit delegated scope | User / authorized requester                   |
| Confirm hospital can receive patient        | No                                                | Receiving hospital authorized staff           |
| Hold resource after acceptance              | Backend may execute if pre-authorized             | Authorized hospital policy + prior acceptance |
| Override held resource / transport choice   | No                                                | Qualified authorized personnel                |
| Complete clinical admission / triage        | No                                                | Treating clinical team                        |

## Observe -\> plan -\> act -\> verify

For each agent event: rationale (short summary), tool called, input identifiers (no excessive PHI), resulting state, source timestamp, actor, policy result, and next task. Redact model prompts/agent transcripts before they appear in public screens.

# 10 Platform architecture and integration plan

Reuse the working multi-tenant doctor/department and appointment backend. Add resource and emergency modules with a single transactional source of truth. Hospital group boundaries should support multiple branches in the same network, but initial demo can seed just three.

> **SYSTEM BOUNDARY**
> Public/ambulance view <-> Emergency API <-> Eligibility & request state service <-> Hospital admin dashboard <-> PostgreSQL + realtime events; supervisor and specialist agents call approved APIs through scoped tools, never raw cross-tenant SQL.

| **Layer**   | **Today**                                                        | **Future**                                    |
|-------------|------------------------------------------------------------------|-----------------------------------------------|
| Frontend    | React/Next.js public finder, hospital resource/admin, task force | Native apps / dispatcher tools                |
| API         | Existing backend + emergency module, RBAC                        | FHIR/HL7, ADT/bed systems                     |
| Data        | PostgreSQL transactional resources, cases, holds, audit          | Hospital EHR/HMS adapter layer                |
| Realtime    | WebSockets or Supabase Realtime                                  | Event bus, cross-hospital feeds               |
| Agent layer | LLM tool calling plus policy gate                                | More specialized and configurable task forces |
| Workflow    | Request timers, retries, durable case status                     | Temporal or equivalent when needed            |
| Routing     | Seeded ETA for demo with explicit labeling                       | Approved road routing API                     |

## Integration caution

No 102/108/112 integration is needed for the demo, and HospitalOS must not imply government or EMS endorsement. Hospital membership/verification requires facility contracts, verified admin identities, and operational data agreements before genuine real-time matching can be claimed.

# 11 Data model, API contracts and event taxonomy

## Tables / objects

| **Entity**                   | **Core fields**                                                                        |
|------------------------------|----------------------------------------------------------------------------------------|
| networks / hospitals         | network_id, hospital_id, tenant_id, facility_verified, lat/lng, published_capabilities |
| resources                    | resource_id, hospital_id, type, readiness_state, version, observed_at, source          |
| staffing_readiness           | hospital_id, service, coverage_state, verified_at, valid_until                         |
| equipment                    | equipment_id, hospital_id, capabilities, state, observed_at                            |
| emergency_cases              | case_id, request_actor, approximate_location, requirements_source, state, expiry       |
| candidate_assessments        | case_id, hospital_id, eligibility, reason_codes, ETA, score, verified_at               |
| acceptance_requests          | request_id, case_id, hospital_id, state, deadline_at, response_actor                   |
| resource_holds               | hold_id, resource_id, case_id, state, expires_at, confirmed_by                         |
| agent_tasks / event_log      | task_id, case_id, agent_type, tool, status, actor, event_type, timestamp               |
| delegation_policies (future) | grantor, scope, action list, guardrails, expires_at, revoked_at                        |

## Minimum API surface

- GET /public/hospitals?lat=&lng=&preference= — discover verified listings and current status disclaimers

- POST /emergency/cases — create synthetic/new case with actor and capability requirement source

- GET /emergency/cases/:id/candidates — fetch deterministic eligibility and explanation

- POST /emergency/cases/:id/requests — send acceptance request to one selected facility

- POST /emergency/requests/:id/decision — authenticated receiving-admin accept/decline with version + idempotency

- POST /resources/:id/holds — backend-only atomic hold after prior approval

- GET /emergency/cases/:id/events — scoped event history for user/admin/supervisor

- PATCH /hospitals/:id/resources/:rid — authorized resource manager update with optimistic version

- GET /hospitals/:id/receiving-requests — hospital request inbox; server-side tenant checks

## Canonical events

CASE_CREATED, REQUIREMENTS_RECORDED, CANDIDATES_EVALUATED, ACCEPTANCE_REQUESTED, REQUEST_REMINDER_SENT, ACCEPTANCE_DECLINED, ACCEPTANCE_EXPIRED, HOSPITAL_ACCEPTED, RESOURCE_REVALIDATED, HOLD_CREATED, HOLD_CONFLICT, HOLD_EXPIRED, RESOURCE_INVALIDATED, RECEIVING_DETAILS_SHARED, REQUEST_WITHDRAWN, AGENT_TASK_CREATED, AGENT_TASK_COMPLETED, HUMAN_REVIEW_REQUESTED.

# 12 User experience and screen specifications

| **Screen**                      | **Core components**                                                                               | **Behavior**                                     |
|---------------------------------|---------------------------------------------------------------------------------------------------|--------------------------------------------------|
| S1 Patient: Find Emergency Care | 112 warning; location/manual address; affordable/private/any; optional known requirement; radius  | No diagnosis questions; default can be “unknown” |
| S2 Patient: Hospital Results    | 3 ranked cards; ETA, service readiness, verified timestamp, cost category, why match; request CTA | No false “guaranteed” badge; unverified labeled  |
| S3 Patient: Request tracking    | Case ref, status, timer, alert, fallback, cancellation, emergency contact                         | State-driven; no fake countdown success          |
| S4 Hospital: Resource Manager   | Beds/ED bays/ICU/staff/equipment; states, update controls, source, freshness                      | Authorized branch staff only                     |
| S5 Hospital: Emergency Inbox    | Pending cases, ETA, required capabilities, accept/decline, reason codes, age                      | Backend revalidates at acceptance                |
| S6 Network Command Center       | Aggregate branch status, case pipeline, exceptions and alerts                                     | Network-scoped view                              |
| S7 Task Force                   | Supervisor goal, specialist tasks, real tool events, changes, approval/escalation history         | Show genuine back-end outcomes                   |
| S8 Existing Voice Assistant     | Call/voice booking, appointment lookup, doctor/department discovery                               | Unchanged existing workflow                      |

## Mobile and accessibility

Large click targets, bilingual Hindi/English copy, accessible contrast, minimal steps, location permission alternatives, direct call actions, and status labels not dependent on color. Show disclaimer once clearly rather than creating a wall of medical text.

# 13 India regulatory and policy mapping (as checked 01 Nov 2026)

> **REGULATORY SCOPE**
> This mapping is India-first, not a substitute for specialist legal and clinical review. State clinical-establishment laws, EMS destination rules, medical practice rules, consumer-protection obligations and hospital-specific protocols require local validation before real patient use.

## 13.1 Emergency help and ambulance context

\[OFFICIAL\] Government ERSS identifies 112 as the pan-India emergency response number. NHM describes 108 predominantly as emergency response and 102 mainly as patient transport (notably maternal/child services), but operational arrangements vary by jurisdiction. Design: prominent 112, local verified emergency contacts, no claim of dispatch partnership. \[R1\] \[R2\]

## 13.2 Clinical Establishments (Registration and Regulation) Act, 2010

\[LAW, WHERE APPLICABLE\] Section 12(2) requires clinical establishments to undertake emergency medical examination/treatment to stabilize, within staff/facilities available, a person brought with an emergency medical condition. The central framework applies in adopting jurisdictions, and rules differ by state/UT. Official Ministry material identifies adopting jurisdictions including Rajasthan, Bihar and others, while Delhi is not covered by that central adoption list; assess local law separately. Facility registration and minimum standards need verification, not a generic platform “certified” badge. \[R3\] \[R4\]

Design consequence: never depict “hospital declined app request” as legally authorizing denial of emergency assessment. A digital pre-arrival request is not equivalent to patient presentation or clinical interfacility transfer. An unaccepted app request does not override statutory duties when a patient physically arrives.

## 13.3 Emergency standards / NABH

\[STANDARD\] NABH Emergency Department Certification emphasizes protocols for triage, emergency response, training, documentation, patient rights and communication. NABH certification/accreditation is voluntary unless applicable policy/contract provides otherwise. Display only verified certification and do not treat certification as proof of a currently ready bed. \[R5\] \[R6\]

## 13.4 Patient rights, access, transparency and fair pricing

\[GUIDANCE / LOCALLY IMPLEMENTED\] Ministry patient-rights materials include dignity, informed consent, information and emergency-care-related expectations. Implementation and enforceability must be assessed in the state/facility. For HospitalOS: do not make payment/identity mandatory for urgent assistance; use verified prices only; do not advertise cheap/expensive hospital size equivalence; no false claims of acceptance or quality. \[R7\]

## 13.5 Digital Personal Data Protection Act, 2023 and Rules, 2025

\[LAW – PHASED COMMENCEMENT\] MeitY notified the DPDP Rules in Nov 2025. Gazette G.S.R. 843(E) dated 13 Nov 2025 appoints immediate commencement for specified institutional/definition provisions, a further group after ONE YEAR from Gazette publication, and the main processing/rights/obligations provisions after EIGHTEEN MONTHS. On 01 Nov 2026, those future commencement points had not yet arrived. Do not claim every provision is already enforceable; plan now for the staged regime and review all notifications before production. \[R8\] \[R9\]

Design consequence: purpose limitation, minimal case data, clear accessible notices, lawful processing basis appropriate to context, secure third-party processing agreements, retention/deletion schedules, access controls and breach procedures. Health data is sensitive in practice; do not assume emergency circumstances permit indiscriminate reuse.

## 13.6 Other current privacy/security duties

\[LEGAL REVIEW REQUIRED\] Check continuing applicability of the Information Technology Act and related security/privacy rules, confidentiality and medical-record duties, relevant contractual terms, and state-specific requirements during the DPDP transition. Do not write a single universal “consent checkbox” as the complete legal basis for emergency care or data exchange.

## 13.7 ABDM interoperability – optional, not a license

\[POLICY / ECOSYSTEM\] ABDM supports Health Facility Registry, interoperable digital health records and consent-aware exchange. The ABDM Health Data Management Policy describes privacy by design and federated data sharing. HFR participation does not by itself prove facility licensing or live capacity. For the hackathon, do not require ABHA/HFR or real patient records. \[R10\]

## 13.8 Explicit stop-rules

- No clinical triage, AI diagnosis, treatment recommendation or transport diversion directive.

- No pre-arrival request or payment workflow delaying necessary medical assessment.

- No claim “bed reserved” unless the transactional system confirms an active hold.

- No hospital acceptance without a properly authenticated receiving authority in MVP.

- No automated medical/EMS protocol override even if an AI agent suggests it.

- No misleading certification/ambulance/government partnership or fabricated hospital capability.

- No use of real patient data in the hackathon and no scraping of private hospital systems.

# 14 Security, privacy and incident management

| **Control**            | **Implementation requirement**                                                            |
|------------------------|-------------------------------------------------------------------------------------------|
| Identity/RBAC          | Verified staff accounts, least privilege, separate patient/public and admin scopes        |
| Multi-tenancy          | Server-enforced tenant and branch scoping; tests for cross-tenant leakage                 |
| Clinical/personal data | Collect minimal fields, encrypt in transit and at rest, avoid PHI in logs/prompts         |
| Tool safety            | LLM tools scoped, allowlisted, input validated, with policy gate and audit                |
| Event integrity        | Append-only audit entries with actor, time, previous/next state, reason, request ID       |
| Resource transactions  | Atomic holds, idempotency keys, optimistic versioning, retry-safe APIs                    |
| Auth/session           | Short-lived sessions, secure cookies where appropriate, strong credentials/MFA for admins |
| Messaging              | Send minimal case data; staff views require access checks; no public PII notification     |
| Reliability            | Stale-data alerts, queue retries, reconnect support, manual escalation, downtime banner   |
| Incident response      | Owner/contacts, alerting, revocation, rollback, forensic logs and breach decision process |

For the hackathon, deploy only synthetic data. For production, obtain contractual permission and detailed legal/security review before processing personal or patient health information or claiming authenticated facility integrations.

# 15 Failure handling and acceptance-test matrix

| **Scenario**                           | **Expected result**                                                                |
|----------------------------------------|------------------------------------------------------------------------------------|
| Two cases request same staffed ICU bed | One atomic hold; one explicit conflict event and fallback                          |
| Admin declines                         | Reason recorded; user informed; candidates refreshed; no implicit clinical refusal |
| 30s timeout / app offline              | Expires safely; no auto accept; show emergency-contact alternative                 |
| Admin accepts after timeout            | Stale response rejected / explicit fresh action required                           |
| Bed or equipment fails after match     | Candidate readiness invalidated and request revalidated                            |
| Data older than threshold              | Unverified label, no “confirmed available” badge                                   |
| Nearby hospital lacks inpatient ICU    | May still show emergency capability; do not misstate overall care inability        |
| Family selects affordability preferred | Ranking adapts among suitable options, critical capability stays visible           |
| Wrong tenant admin clicks accept       | 403/permission denial and audit                                                    |
| Duplicate API/webhook delivery         | Idempotent; one request state transition                                           |
| LLM requests direct DB update          | Tool gate rejects; deterministic API only                                          |
| GPS denied or no signal                | Manual location/address still works                                                |
| No hospitals eligible                  | No false match; prompt emergency-service call and expand criteria safely           |
| Existing voice booking used            | Current booking and appointment lookup remain functional                           |

## MVP release gate

All P0 scenarios above pass; simulated data labels visible; frontend and backend statuses synchronized; no duplicate holds; explicit human receiving acceptance; no real personal health data; 112/local emergency call visible; no claims of diagnosis/guaranteed admission; recoverable full demo reset.

# 16 Hackathon build plan and demo script

## Workstream order

- W1: Seed three synthetic hospitals in a single chain; implement hospital resources, statuses, timestamps and branch permissions.

- W2: Implement eligibility and matching as deterministic functions; add preference-sensitive ranking and explainable reasons.

- W3: Add case create, request send, admin accept/decline, timer, timeout, fallback and audited state events.

- W4: Add PostgreSQL atomic hold/revalidation and realtime updates; make two-concurrent-cases test possible.

- W5: Add Supervisor Agent + resource/matching/coordination specialist tools; log real tool calls and an exception-handling loop.

- W6: Build patient finder, hospital admin inbox, resource dashboard and task-force screens; leave voice reception intact.

- W7: End-to-end tests, synthetic data check, stable reset, fallback recorded demo, and final pitch.

## Five-minute demonstration

| **Window** | **What happens**                                                                    | **What it proves**                |
|------------|-------------------------------------------------------------------------------------|-----------------------------------|
| 0:00–0:40  | Pain point + existing voice appointment system in one sentence                      | Working foundation; not slideware |
| 0:40–1:30  | Resource dashboard: three hospitals, staffed ICU vs physical bed                    | Operational resource accuracy     |
| 1:30–2:25  | Patient finder: affordability + location, three ranked results                      | Explainable matching              |
| 2:25–3:15  | Request Hospital B, pending timer; admin opens inbox and accepts                    | Real two-sided workflow           |
| 3:15–4:10  | Resource hold and agent activity; inject equipment/bed conflict or second patient   | Atomicity and replanning          |
| 4:10–4:40  | Show receiving status, audit event stream and directions                            | Outcome and trust                 |
| 4:40–5:00  | Existing voice receptionist books a regular OPD appointment; future platform vision | Unified specialist-agent story    |

## Judge-facing pitch

> **25-SECOND OPENING**
> In an emergency, the nearest hospital is not always ready for the resources a patient may need. Hospital information and staff readiness sit in different systems, so families and receiving teams struggle to coordinate. HospitalOS makes hospital capability visible, gets explicit receiving confirmation, and uses a controlled AI task force to move the operational work forward—without replacing doctors or emergency dispatch.

# 17 Roadmap, KPIs, risks and open decisions

## Product phases

| **Phase**               | **Capability**                                                                                 |
|-------------------------|------------------------------------------------------------------------------------------------|
| MVP / hackathon         | Resource directory, emergency matching, request/acceptance, state events, agent coordination   |
| Pilot phase             | Verified hospital feeds, staff workflow, reliable holds, institutional security and validation |
| V2: Arrival management  | Administrative pre-arrival packet, arrival acknowledgments, handover status                    |
| V3: Hospital operations | Clinician-authorized admission handoff, bed placement, discharge/cleaning cycle                |
| V4: Network task forces | Interfacility transfer admin, shift/resource management, equipment coordination                |
| V5: Policy delegation   | Custom admin workflows and narrowly scoped agent delegation under audit                        |

## KPIs to measure in a real pilot (not invented results)

- Median facility-request response time; percentage of requests accepted/declined/timed-out.

- Capacity freshness coverage; mismatch rate between displayed and actual status.

- Double-booking rate (target zero); hold conflicts correctly rejected.

- Administrative handoff time and number of follow-up calls per case.

- Appropriate arrival-readiness confirmations and revalidation delays.

- User abandonment or fallback frequency; affordability option utilization.

- Staff satisfaction, escalation rate, and override reasons.

## Top risks and mitigations

| **Risk**                                      | **Mitigation / owner**                                                   |
|-----------------------------------------------|--------------------------------------------------------------------------|
| Stale or misleading resource data             | Hospital operations owner; mandatory update provenance and expiry        |
| Illegal/unsafe routing or refusal implication | Clinical governance lead; non-diagnostic matching + emergency banner     |
| Wrong staff accepting                         | Hospital administrator; verified RBAC and audit                          |
| Over-engineered agents                        | Engineering lead; use few real agents and reliable workflows             |
| Unclear paying buyer                          | Founder discovery with ED, transfer center, bed management, hospital COO |
| Cross-hospital data sharing                   | Legal/security review, facility agreements and tenant boundaries         |
| Consent/DPDP transition uncertainty           | India counsel; track statutory commencement/notification updates         |

## Decisions locked vs needing validation

LOCKED: preserve existing voice system; India-first synthetic network; hospital human acceptance; no clinical diagnosis; app does not integrate with ambulances; resource manager precedes matching; timer expiration never auto-accepts; task-force demo shows real tool activity.

VALIDATE BEFORE REAL PILOT: which state and hospital types; which roles may accept; whether/when a provisional hold is allowed; clinical escalation SOP; hospital data update cadence; cost/scheme verification; legal basis for data processing and retention; receiving service hours; hospital partnership and licensing verification.

# 18 Official source register

Primary and policy sources checked for this document. The interpretation and product requirements are our proposed design; official publications remain authoritative. Source URLs are included for audit and future review.

**\[R1\] Government of India – 112 Emergency Response Support System  
**https://112.gov.in/

**\[R2\] National Health Mission – Emergency Response / Patient Transport 108 and 102  
**https://nhm.gov.in/nhm_live/index1.php?lang=1&level=2&lid=189&sublinkid=1217

**\[R3\] Clinical Establishments Act: Ministry FAQ and state adoption  
**https://clinicalestablishments.mohfw.gov.in/en/faq

**\[R4\] Clinical Establishments Act 2010, section 12(2), Ministry text  
**https://www.clinicalestablishments.mohfw.gov.in/sites/default/files/2023-07/Act%202010-23.pdf

**\[R5\] NABH – Emergency Department Certification Programme  
**https://nabh.co/programmes/emergency-department-in-hospitals-certification-programme/

**\[R6\] NABH – Emergency Department certification overview  
**https://portal.nabh.co/Emergency_Intro.aspx

**\[R7\] MoHFW – Charter of Patients Rights and Responsibilities  
**https://clinicalestablishments.mohfw.gov.in/sites/default/files/2023-06/3181.pdf

**\[R8\] MeitY – Digital Personal Data Protection Rules 2025 / official notifications  
**https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa

**\[R9\] Gazette G.S.R. 843(E) – DPDP Act phased commencement (13 Nov 2025)  
**https://www.meity.gov.in/static/uploads/2025/11/c56ceae6c383460ca69577428d36828b.pdf

**\[R10\] ABDM – Health Data Management Policy  
**https://abdm.gov.in/static/media/health_management_policy_bac9429a79.80f74bc3e039c00acd4f.pdf

**\[R11\] DGHS – Hospital Manual, April 2025  
**https://dghs.mohfw.gov.in/uploads/assets/b9gSYbHAzy9pIrF74o1Aw7bvw91KW9Axd5wrlqPd.pdf

**\[R12\] Clinical Establishments – State/UT rules and notifications  
**https://clinicalestablishments.mohfw.gov.in/en/state-and-uts-rules-and-notification

## Final product definition

> **HOSPITALOS IN ONE SENTENCE**
> A multi-tenant hospital operations layer that turns verified resources into explainable emergency facility options, accountable receiving requests, safe provisional resource allocation, and event-driven AI administrative coordination.

Prepared: 01 November 2026. Regulatory status and operational protocols must be rechecked against official notifications and local hospital/EMS governance before real-world implementation.
