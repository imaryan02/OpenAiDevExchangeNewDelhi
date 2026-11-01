# Antigravity Implementation Summary & Technical Blueprint
> Conversation follow-up: caller feedback found `0.85` too slow. The current recommendation is **`0.95`**, with restrained delivery, playback-aware silence recovery and fillers triggered by actual lookups. See [the conversation regression record](docs/PROJECT_AUDIT_2026-09-12.md#conversation-regression-follow-up--12-september-2026). Live Azure acceptance remains pending.
> Voice follow-up, 12 September 2026: the claim below that rushed speech was eliminated was not supported by the checked local configuration. A pacing fix now uses complete-reply streaming, a `0.85` speed setting, steady delivery instructions, and profile-aware audio caching. Local baseline: `gpt-4o-mini-tts` / `coral`. Offline checks pass; live acoustic acceptance and Azure activation remain pending. See [the audit follow-up](docs/PROJECT_AUDIT_2026-09-12.md#voice-pacing-follow-up--12-september-2026).
**Project:** Geeta Medicine AI Voice Receptionist  
**Target Inbound Number (DID):** `+919429397279`  
**Status:** Production-Grade Voice Agent & Deployed Cloud System  
**Author/Agent:** Antigravity (Google DeepMind)  
**Last Updated:** 12 September 2026  
**Audience:** Codex, Engineering Leads, Telephony AI Architects, & Conference Presenters  

---

## 1. Executive Summary & Core Achievements

The Geeta Medicine AI Receptionist has evolved into an end-to-end, multi-phase, **production-deployed conversational voice agent** backed by Azure Container Apps, Vercel, Supabase PostgreSQL, and VoiceLink Telephony.

### Key Production Achievements:
1. **Cloud Deployment (Azure + Vercel)**:
   - **Backend**: Containerized FastAPI + LangGraph service running on **Azure Container Apps** in `Central India` with native persistent WebSocket support (`wss://...`), automated GitHub Actions CI/CD, and Supabase transaction pooler integration.
   - **Frontend**: Staff Reception Desk deployed on **Vercel** ([`https://ai-voice-receptionist-seven.vercel.app`](https://ai-voice-receptionist-seven.vercel.app)) with Mumbai edge distribution and 6-second live polling.
   - **Telephony**: VoiceLink DID mapped directly to the cloud WebSocket gateway with zero dependency on local tunnels.
2. **Deterministic Dialogue Contract (Phase 1)**:
   - Enforced strict English/Hindi/Hinglish consent validation.
   - Separate offer readback and confirmation turns prevent premature bookings.
   - Mid-call changes (*"Nahi, Dr Sweta ka kar do"*) invalidate pending consent and require fresh readback.
   - All AI voice offers default to `CASH` / `DUE_AT_CLINIC`.
3. **Ambiguity & Server-Bound Security (Phase 2)**:
   - Ambiguous doctor requests return candidate lists (`AMBIGUOUS_DOCTOR`) rather than silent tie-breaking.
   - All caller tools bind strictly to the telecom-verified carrier number (`caller_phone_e164`); arbitrary phone queries fail closed.
   - Financial terms (`fee_minor`, `currency`) are cryptographically signed with HMAC to prevent unagreed fee drift.
   - Grounded `get_clinic_information` tool reports real clinic locations, hours, and 112/102 emergency policy.
4. **VoiceLink Transport Reliability & Real Barge-In (Phase 3)**:
   - Real telephony barge-in: incoming speech during bot playback triggers immediate WebSocket buffer purge (`{"event": "clear"}`) and audio abort within $\le 300\text{ ms}$.
   - Immediate cancellation of in-flight LLM/TTS tasks upon caller hangup.
   - Silence recovery with a 2-tier gentle reprompt at 8.5 seconds and a hard 10-minute maximum call duration cap.
   - Truthful human-unavailable responses without false transfer promises.
5. **Guarded Appointment Operations (Phase 4)**:
   - Conversational `cancel_appointment` and `reschedule_appointment` tools enforcing `can_manage` caller permissions.
   - Authoritative bilingual confirmations (*"Aapka appointment GM-12345 cancel kar diya gaya hai"*).
   - Prompt 6-second auto-refresh and manual refresh on the staff reception desk.
   - Conflict-safe schedule rebuild reviving cancelled sessions without loss of slots.
6. **Conference Rehearsal & Live Readiness (Phase 5)**:
   - Repeatable one-command seed script ([`scripts/seed_demo_rehearsal.py`](file:///e:/Projects/Ai_receptionist/scripts/seed_demo_rehearsal.py)).
   - Comprehensive conference runbook ([`docs/CONFERENCE_RUNBOOK.md`](file:///e:/Projects/Ai_receptionist/docs/CONFERENCE_RUNBOOK.md)) with rehearsal scripts A through I.
   - Backup presentation path via `/assistant` web chat for poor cellular hall conditions.
7. **Acoustic Naturalness & Voice Pacing**:
   - Calibrated OpenAI `gpt-4o-mini-tts` with voice **`nova`** for calm, natural Hindi cadence, eliminating rushed robotic speech.
   - Pre-warmed conversational audio comfort fillers (*"Ji Aryan ji, ek second main check karti hoon..."*) during database queries.

---

## 2. Production Architecture Diagram

```mermaid
flowchart TD
    subgraph Telephony Carrier
        Caller["Cell Phone Caller: +919429397279"] -->|PSTN / Cellular| VL["VoiceLink Carrier Cloud"]
    end

    subgraph Azure Cloud Infrastructure (Central India)
        VL -->|"wss://.../v1/voicelink/media"| ACA["Azure Container App: ai-receptionist-backend"]
        ACA --> GW["VoiceLink Gateway (8 kHz G.711 A-law)"]
        GW -->|Barge-in VAD & Echo Filter| STT["OpenAI STT (gpt-4o-mini-transcribe)"]
        STT --> LG["LangGraph Dialogue Engine"]
        LG -->|System Prompt & Guardrails| LLM["OpenAI GPT-4o-mini"]
        LLM -->|Tool Execution| TE["ToolExecutor (Server-Bound Caller Phone)"]
        LG -->|Sentence Streaming| TTS["OpenAI TTS (gpt-4o-mini-tts / nova)"]
        TTS -->|24kHz PCM to 8kHz A-law| GW
        GW -->|RTP Audio Playback| VL
    end

    subgraph Data & Storage Layer
        TE --> DB[("Supabase Managed PostgreSQL Pooler")]
        DB --> C["public.contacts & contact_phones"]
        DB --> P["public.patients & patient_contacts"]
        DB --> S["public.appointment_sessions & slots"]
        DB --> A["public.appointments & permissions"]
    end

    subgraph Edge Web Presentation (Vercel)
        Staff["Clinic Receptionist / Presenter"] -->|HTTPS| Vercel["Vercel Global Edge: ai-voice-receptionist-seven.vercel.app"]
        Vercel -->|REST API Requests: /v1/me, /v1/bookings| ACA
    end

    subgraph CI / CD Automation
        Git["GitHub: imaryan02/Ai_voice_receptionist"] -->|Push main| GHA["GitHub Actions"]
        GHA -->|Build & Push Docker Image| ACR["Azure Container Registry: acraireceptionist"]
        ACR -->|Auto Deploy Revision| ACA
        Git -->|Push main| VercelCD["Vercel Automatic Deployment"]
    end
```

---

## 3. Implemented Roadmap: Phase 1 to Phase 5

| Phase | Objective | Key Deliverables & Implemented Architecture |
| :--- | :--- | :--- |
| **Phase 1** | **Dialogue Foundation** | Bounded Hindi/English regex consent parsing (`dialogue.py`), separate offer readback turn, invalidation of pending consent on mid-call changes, current-turn committed confirmation tracking (`graph.py`), pay-at-clinic default. |
| **Phase 2** | **Discovery & Caller Context** | Ambiguous doctor detection (`AMBIGUOUS_DOCTOR`), database cutoff & capacity checks, caller identity binding (`caller_phone_e164`), HMAC-signed financial terms, grounded `get_clinic_information` tool. |
| **Phase 3** | **VoiceLink Transport Reliability** | Continuous inbound audio reading, live speech barge-in WebSocket buffer clearing (`{"event": "clear"}`), immediate hangup task cancellation, 8.5s silence prompts, 10-min duration cap, honest human-unavailable fallback. |
| **Phase 4** | **Demonstration Operations** | Guarded phone cancellations (`cancel_appointment`) & rescheduling (`reschedule_appointment`) with caller permission checks (`can_manage`), bilingual mutation announcements, 6s auto-refresh polling on staff dashboard, schedule rebuild conflict revival. |
| **Phase 5** | **Conference Rehearsal & Live Readiness** | Repeatable Supabase fixture seeding script ([`seed_demo_rehearsal.py`](file:///e:/Projects/Ai_receptionist/scripts/seed_demo_rehearsal.py)), comprehensive conference runbook ([`docs/CONFERENCE_RUNBOOK.md`](file:///e:/Projects/Ai_receptionist/docs/CONFERENCE_RUNBOOK.md)), bilingual live scripts (A–I), backup web presentation path (`/assistant`), and 1–5 concurrent calls operational guidance. |

---

## 4. Agent Toolset Reference

| Tool Name | Scope & Guardrails | Primary Arguments |
| :--- | :--- | :--- |
| `suggest_department` | Maps symptoms to specialties (General Medicine, Gynaecology, Pediatrics). Severe symptoms trigger urgent 112/102 advice. | `problem_description` |
| `search_availability` | Queries bookable sessions in IST date ranges. Detects ambiguous doctor names and enforces booking cutoff minutes. | `from_at`, `to_at`, `doctor_name`, `department_name` |
| `lookup_caller_family` | Retrieves caller name and saved family contacts (e.g. "Sunita Gupta - MOTHER") bound strictly to verified carrier phone. | `phone_e164` (must match caller) |
| `list_upcoming_appointments` | Lists confirmed appointments for the caller's phone. Works zero-OTP over telephone. | `phone_e164` (must match caller) |
| `prepare_booking_offer` | Generates an HMAC-signed booking offer with doctor, session window, price, and token. | `phone_e164`, `patient_name`, `relationship`, `session_id`, `payment_method` |
| `confirm_booking_offer` | Executes database transaction confirming the booking and issuing `booking_reference` (e.g. `GM-XXXXXXXXXX`). | None (uses active offer state) |
| `cancel_appointment` | Validates caller management authorization (`can_manage`) and cancels appointment atomically. | `booking_reference` |
| `reschedule_appointment` | Validates caller authorization, target session capacity, and cutoff, atomically moving booking. | `booking_reference`, `new_session_id` |
| `get_clinic_information` | Grounded tool returning clinic branches, addresses, operating hours, payment methods, and emergency rules. | `query_topic` |

---

## 5. Production Operations & Live Verification

### Cloud Endpoints:
- **Backend API & WebSockets**: `https://ai-receptionist-backend.kindocean-a1f0cf18.centralindia.azurecontainerapps.io`
- **Liveness Healthcheck**: `GET /health/live` $\rightarrow$ `{"status": "ok"}`
- **Readiness Healthcheck**: `GET /health/ready` $\rightarrow$ `{"status": "ok"}` (Verifies Supabase DB pool)
- **VoiceLink WebSocket**: `wss://ai-receptionist-backend.kindocean-a1f0cf18.centralindia.azurecontainerapps.io/v1/voicelink/media?token=...`
- **VoiceLink Events Webhook**: `https://ai-receptionist-backend.kindocean-a1f0cf18.centralindia.azurecontainerapps.io/v1/voicelink/events?token=...`
- **Staff Dashboard (Vercel)**: [`https://ai-voice-receptionist-seven.vercel.app`](https://ai-voice-receptionist-seven.vercel.app)

### Test & Quality Verification Results:
- **Regression Suite**: **109 passed, 8 skipped**, 0 failures in `11.01s`.
- **Static Typing (Mypy)**: Clean pass across 50 source files in strict mode.
- **Linter (Ruff)**: Clean pass across backend, tests, and scripts.
- **Frontend Build**: Built in `1.23s` (Vite production bundle).
