# Project code map — 26 September 2026

Inventory of all 205 Git-tracked files present at review start. Dependencies, generated output, caches, private environment contents and the two new review documents are excluded. Behavioral findings and validation limits are in [docs/PROJECT_CODE_REVIEW_2026-09-26.md](E:/Projects/Ai_receptionist/docs/PROJECT_CODE_REVIEW_2026-09-26.md).

**Entry points**

Default backend: app.main:app. Alternatives: app.voice_main:app, app.voicelink_main:app, app.sarvam_main:app. Browser: frontend/index.html → src/main.tsx → App.tsx. The conference entry uses the ?conference query parameter. SQL migrations are owner-run files, with no automatic migration runner in application startup.

**Declared API routes**

Source declarations only. Sarvam routes belong to the separate Sarvam app; all other listed routes are mounted by the default app.

| Method | Path | Handler |
| --- | --- | --- |
| POST | /v1/agent/chat | [backend/app/api/routes/agent.py](E:/Projects/Ai_receptionist/backend/app/api/routes/agent.py:23) → chat_with_reception_agent |
| GET | /v1/availability | [backend/app/api/routes/availability.py](E:/Projects/Ai_receptionist/backend/app/api/routes/availability.py:17) → list_availability |
| POST | /v1/schedule/generate | [backend/app/api/routes/availability.py](E:/Projects/Ai_receptionist/backend/app/api/routes/availability.py:54) → generate_schedule |
| GET | /v1/booking-options | [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py:82) → booking_options |
| POST | /v1/booking-intake | [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py:144) → create_booking_intake |
| GET | /v1/appointments | [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py:300) → list_appointments |
| POST | /v1/appointments/{appointment_id}/visit-status | [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py:398) → update_visit_status |
| POST | /v1/appointments/holds | [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py:445) → create_hold |
| POST | /v1/appointments/{appointment_id}/confirm | [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py:481) → confirm_hold |
| POST | /v1/appointments/{appointment_id}/cancel | [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py:555) → cancel |
| POST | /v1/appointments/{appointment_id}/reschedule | [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py:579) → reschedule |
| GET | /v1/configuration | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:188) → get_configuration |
| PATCH | /v1/configuration/organization | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:257) → update_organization |
| POST | /v1/configuration/locations | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:280) → create_location |
| POST | /v1/configuration/departments | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:317) → create_department |
| PATCH | /v1/configuration/locations/{location_id} | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:343) → update_location |
| POST | /v1/configuration/assignments | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:373) → create_assignment |
| POST | /v1/configuration/schedule-rules | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:416) → create_schedule_rule |
| POST | /v1/configuration/schedule-exceptions | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:483) → create_schedule_exception |
| PATCH | /v1/configuration/departments/{department_id} | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:562) → update_department |
| PATCH | /v1/configuration/assignments/{assignment_id} | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:592) → update_assignment |
| DELETE | /v1/configuration/assignments/{assignment_id} | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:645) → delete_assignment |
| PATCH | /v1/configuration/schedule-rules/{rule_id} | [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py:715) → update_schedule_rule |
| GET | /health/live | [backend/app/api/routes/health.py](E:/Projects/Ai_receptionist/backend/app/api/routes/health.py:10) → liveness |
| GET | /health/ready | [backend/app/api/routes/health.py](E:/Projects/Ai_receptionist/backend/app/api/routes/health.py:15) → readiness |
| GET | /v1/me | [backend/app/api/routes/me.py](E:/Projects/Ai_receptionist/backend/app/api/routes/me.py:11) → get_me |
| GET | /v1/patients | [backend/app/api/routes/patients.py](E:/Projects/Ai_receptionist/backend/app/api/routes/patients.py:50) → list_patients |
| GET | /v1/caller-profile | [backend/app/api/routes/patients.py](E:/Projects/Ai_receptionist/backend/app/api/routes/patients.py:145) → get_caller_profile |
| PATCH | /v1/patients/{patient_id} | [backend/app/api/routes/patients.py](E:/Projects/Ai_receptionist/backend/app/api/routes/patients.py:206) → update_patient |
| PATCH | /v1/patients/{patient_id}/contacts/{contact_id} | [backend/app/api/routes/patients.py](E:/Projects/Ai_receptionist/backend/app/api/routes/patients.py:241) → update_patient_contact |
| DELETE | /v1/patients/{patient_id} | [backend/app/api/routes/patients.py](E:/Projects/Ai_receptionist/backend/app/api/routes/patients.py:310) → delete_patient |
| DELETE | /v1/patients/{patient_id}/contacts/{contact_id} | [backend/app/api/routes/patients.py](E:/Projects/Ai_receptionist/backend/app/api/routes/patients.py:528) → unlink_patient_contact |
| GET | /v1/presentation/calls | [backend/app/api/routes/presentation.py](E:/Projects/Ai_receptionist/backend/app/api/routes/presentation.py:35) → calls |
| GET | /v1/presentation/calls/{call_id}/events | [backend/app/api/routes/presentation.py](E:/Projects/Ai_receptionist/backend/app/api/routes/presentation.py:50) → events |
| POST | /v1/sarvam/caller-lookup | [backend/app/api/routes/sarvam.py](E:/Projects/Ai_receptionist/backend/app/api/routes/sarvam.py:73) → caller_lookup |
| POST | /v1/sarvam/availability | [backend/app/api/routes/sarvam.py](E:/Projects/Ai_receptionist/backend/app/api/routes/sarvam.py:81) → availability |
| POST | /v1/sarvam/booking/prepare | [backend/app/api/routes/sarvam.py](E:/Projects/Ai_receptionist/backend/app/api/routes/sarvam.py:89) → prepare_booking |
| POST | /v1/sarvam/booking/confirm | [backend/app/api/routes/sarvam.py](E:/Projects/Ai_receptionist/backend/app/api/routes/sarvam.py:97) → confirm_booking |
| POST | /v1/twilio/voice | [backend/app/api/routes/voice.py](E:/Projects/Ai_receptionist/backend/app/api/routes/voice.py:39) → inbound_voice |
| POST | /v1/twilio/stream-status | [backend/app/api/routes/voice.py](E:/Projects/Ai_receptionist/backend/app/api/routes/voice.py:91) → stream_status |
| WEBSOCKET | /v1/twilio/media | [backend/app/api/routes/voice.py](E:/Projects/Ai_receptionist/backend/app/api/routes/voice.py:106) → voice_media |
| WEBSOCKET | /v1/voicelink/media | [backend/app/api/routes/voice.py](E:/Projects/Ai_receptionist/backend/app/api/routes/voice.py:130) → voicelink_media |
| POST | /v1/voicelink/events | [backend/app/api/routes/voice.py](E:/Projects/Ai_receptionist/backend/app/api/routes/voice.py:165) → voicelink_events |

**Database tables**

| Table | Defining migration |
| --- | --- |
| public.organizations | [supabase/migrations/20260910000100_phase1_tenant_foundation.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260910000100_phase1_tenant_foundation.sql:14) |
| public.locations | [supabase/migrations/20260910000100_phase1_tenant_foundation.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260910000100_phase1_tenant_foundation.sql:25) |
| public.departments | [supabase/migrations/20260910000100_phase1_tenant_foundation.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260910000100_phase1_tenant_foundation.sql:38) |
| public.doctors | [supabase/migrations/20260910000100_phase1_tenant_foundation.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260910000100_phase1_tenant_foundation.sql:49) |
| public.organization_users | [supabase/migrations/20260910000100_phase1_tenant_foundation.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260910000100_phase1_tenant_foundation.sql:58) |
| public.doctor_assignments | [supabase/migrations/20260910000100_phase1_tenant_foundation.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260910000100_phase1_tenant_foundation.sql:68) |
| public.audit_events | [supabase/migrations/20260910000100_phase1_tenant_foundation.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260910000100_phase1_tenant_foundation.sql:90) |
| public.schedule_rules | [supabase/migrations/20260911000100_phase2_scheduling.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000100_phase2_scheduling.sql:10) |
| public.schedule_exceptions | [supabase/migrations/20260911000100_phase2_scheduling.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000100_phase2_scheduling.sql:42) |
| public.appointment_sessions | [supabase/migrations/20260911000100_phase2_scheduling.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000100_phase2_scheduling.sql:67) |
| public.appointment_slots | [supabase/migrations/20260911000100_phase2_scheduling.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000100_phase2_scheduling.sql:98) |
| public.contacts | [supabase/migrations/20260911000200_phase2_contact_patient_identity.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000200_phase2_contact_patient_identity.sql:8) |
| public.contact_phones | [supabase/migrations/20260911000200_phase2_contact_patient_identity.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000200_phase2_contact_patient_identity.sql:19) |
| public.patients | [supabase/migrations/20260911000200_phase2_contact_patient_identity.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000200_phase2_contact_patient_identity.sql:44) |
| public.patient_contacts | [supabase/migrations/20260911000200_phase2_contact_patient_identity.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000200_phase2_contact_patient_identity.sql:55) |
| public.appointments | [supabase/migrations/20260911000300_phase2_appointments.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000300_phase2_appointments.sql:8) |
| public.appointment_contact_permissions | [supabase/migrations/20260911000300_phase2_appointments.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000300_phase2_appointments.sql:59) |
| public.verification_challenges | [supabase/migrations/20260911000300_phase2_appointments.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000300_phase2_appointments.sql:77) |
| public.payment_attempts | [supabase/migrations/20260911000300_phase2_appointments.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000300_phase2_appointments.sql:100) |
| public.idempotency_records | [supabase/migrations/20260911000400_phase2_transactional_booking.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000400_phase2_transactional_booking.sql:8) |
| public.outbox_jobs | [supabase/migrations/20260911000500_phase2_cancellation_outbox.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000500_phase2_cancellation_outbox.sql:6) |
| public.inbox_events | [supabase/migrations/20260911001200_phase2_durable_booking_side_effects.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911001200_phase2_durable_booking_side_effects.sql:13) |
| public.voice_call_sessions | [supabase/migrations/20260912000100_voice_call_sessions.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260912000100_voice_call_sessions.sql:6) |
| public.voice_operation_records | [supabase/migrations/20260912000100_voice_call_sessions.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260912000100_voice_call_sessions.sql:27) |

**Repository, packaging and deployment**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [.editorconfig](E:/Projects/Ai_receptionist/.editorconfig) | 16 | Build, entry-point, dependency or repository configuration. |
| [.github/workflows/ai-receptionist-backend-AutoDeployTrigger-d2b084f2-4c49-4354-be5c-ae075cc99ad2.yml](E:/Projects/Ai_receptionist/.github/workflows/ai-receptionist-backend-AutoDeployTrigger-d2b084f2-4c49-4354-be5c-ae075cc99ad2.yml) | 61 | GitHub Actions Azure auto-deployment. |
| [.github/workflows/ci.yml](E:/Projects/Ai_receptionist/.github/workflows/ci.yml) | 37 | GitHub Actions quality checks. |
| [.gitignore](E:/Projects/Ai_receptionist/.gitignore) | 39 | Build, entry-point, dependency or repository configuration. |
| [Dockerfile](E:/Projects/Ai_receptionist/Dockerfile) | 34 | Root-context backend image build and Uvicorn startup. |
| [backend/.dockerignore](E:/Projects/Ai_receptionist/backend/.dockerignore) | 20 | Build, entry-point, dependency or repository configuration. |
| [backend/.env.example](E:/Projects/Ai_receptionist/backend/.env.example) | 67 | Environment variable template. |
| [backend/Dockerfile](E:/Projects/Ai_receptionist/backend/Dockerfile) | 34 | Backend-context equivalent image build. |
| [backend/pyproject.toml](E:/Projects/Ai_receptionist/backend/pyproject.toml) | 70 | Python dependencies and Ruff/Mypy/Pytest settings. |
| [backend/requirements.lock](E:/Projects/Ai_receptionist/backend/requirements.lock) | 77 | Pinned Python runtime/development dependency set. |

**Product and operational documentation**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [ANTIGRAVITY_IMPLEMENTATION_SUMMARY.md](E:/Projects/Ai_receptionist/ANTIGRAVITY_IMPLEMENTATION_SUMMARY.md) | 137 | Antigravity Implementation Summary & Technical Blueprint. |
| [PRD_AND_IMPLEMENTATION_PLAN.md](E:/Projects/Ai_receptionist/PRD_AND_IMPLEMENTATION_PLAN.md) | 1298 | AI Voice Receptionist — Product Requirements and Delivery Plan. |
| [PRODUCT.md](E:/Projects/Ai_receptionist/PRODUCT.md) | 33 | Product. |
| [README.md](E:/Projects/Ai_receptionist/README.md) | 575 | AI Receptionist. |
| [docs/AZURE_VERCEL_DEPLOYMENT_GUIDE.md](E:/Projects/Ai_receptionist/docs/AZURE_VERCEL_DEPLOYMENT_GUIDE.md) | 167 | Production Deployment Guide: Backend on Azure + Frontend on Vercel. |
| [docs/CALL_DISCONNECT_INVESTIGATION_2026-09-25.md](E:/Projects/Ai_receptionist/docs/CALL_DISCONNECT_INVESTIGATION_2026-09-25.md) | 126 | Incoming-call disconnect investigation. |
| [docs/CONFERENCE_RUNBOOK.md](E:/Projects/Ai_receptionist/docs/CONFERENCE_RUNBOOK.md) | 224 | Geeta Medicine AI Receptionist — Conference Operations Runbook. |
| [docs/PROJECT_AUDIT_2026-09-12.md](E:/Projects/Ai_receptionist/docs/PROJECT_AUDIT_2026-09-12.md) | 790 | AI receptionist project audit. |
| [docs/VOICE_AGENT_INDUSTRY_UPGRADE_PLAN.md](E:/Projects/Ai_receptionist/docs/VOICE_AGENT_INDUSTRY_UPGRADE_PLAN.md) | 343 | Voice agent industry upgrade plan. |
| [docs/phase-0/DECISION_LOG.md](E:/Projects/Ai_receptionist/docs/phase-0/DECISION_LOG.md) | 42 | Phase 0 decision log. Historical design/evidence; verify current behavior in source. |
| [docs/phase-0/DEMO_PROFILE.md](E:/Projects/Ai_receptionist/docs/phase-0/DEMO_PROFILE.md) | 46 | Initial synthetic demo profile. Historical design/evidence; verify current behavior in source. |
| [docs/phase-0/G0_ACCEPTANCE.md](E:/Projects/Ai_receptionist/docs/phase-0/G0_ACCEPTANCE.md) | 64 | Gate G0 acceptance record. Historical design/evidence; verify current behavior in source. |
| [docs/phase-0/PROVIDER_FEASIBILITY.md](E:/Projects/Ai_receptionist/docs/phase-0/PROVIDER_FEASIBILITY.md) | 35 | Provider feasibility matrix. Historical design/evidence; verify current behavior in source. |
| [docs/phase-0/PROVIDER_TEST_PROTOCOL.md](E:/Projects/Ai_receptionist/docs/phase-0/PROVIDER_TEST_PROTOCOL.md) | 62 | Phase 0 provider test protocol. Historical design/evidence; verify current behavior in source. |
| [docs/phase-0/README.md](E:/Projects/Ai_receptionist/docs/phase-0/README.md) | 42 | Phase 0 — Product decisions and provider feasibility. Historical design/evidence; verify current behavior in source. |
| [docs/phase-2/G2_EVIDENCE.md](E:/Projects/Ai_receptionist/docs/phase-2/G2_EVIDENCE.md) | 49 | Gate G2 evidence — scheduling and transactional booking core. Historical design/evidence; verify current behavior in source. |
| [docs/phase-3/STATUS.md](E:/Projects/Ai_receptionist/docs/phase-3/STATUS.md) | 33 | Phase 3 status. Historical design/evidence; verify current behavior in source. |
| [docs/phase-6/SARVAM_SETUP.md](E:/Projects/Ai_receptionist/docs/phase-6/SARVAM_SETUP.md) | 64 | Sarvam voice-agent setup. Historical design/evidence; verify current behavior in source. |
| [docs/phase-6/STATUS.md](E:/Projects/Ai_receptionist/docs/phase-6/STATUS.md) | 41 | Phase 6 voice status. Historical design/evidence; verify current behavior in source. |

**Backend foundations and providers**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [backend/app/__init__.py](E:/Projects/Ai_receptionist/backend/app/__init__.py) | 1 | Python package marker. |
| [backend/app/core/__init__.py](E:/Projects/Ai_receptionist/backend/app/core/__init__.py) | 1 | Python package marker. |
| [backend/app/core/config.py](E:/Projects/Ai_receptionist/backend/app/core/config.py) | 185 | Classes: Settings; Functions: get_settings |
| [backend/app/core/errors.py](E:/Projects/Ai_receptionist/backend/app/core/errors.py) | 38 | Classes: ErrorResponse, ApiError; Functions: api_error_handler |
| [backend/app/core/logging.py](E:/Projects/Ai_receptionist/backend/app/core/logging.py) | 17 | Functions: configure_logging |
| [backend/app/core/request_context.py](E:/Projects/Ai_receptionist/backend/app/core/request_context.py) | 42 | Classes: CorrelationIdMiddleware |
| [backend/app/db/__init__.py](E:/Projects/Ai_receptionist/backend/app/db/__init__.py) | 1 | Python package marker. |
| [backend/app/db/session.py](E:/Projects/Ai_receptionist/backend/app/db/session.py) | 28 | Functions: get_session_factory, get_db_session |
| [backend/app/integrations/__init__.py](E:/Projects/Ai_receptionist/backend/app/integrations/__init__.py) | 1 | Python package marker. |
| [backend/app/integrations/openai_audio.py](E:/Projects/Ai_receptionist/backend/app/integrations/openai_audio.py) | 115 | Classes: OpenAIAudioClient |
| [backend/app/integrations/openai_realtime.py](E:/Projects/Ai_receptionist/backend/app/integrations/openai_realtime.py) | 164 | Classes: RealtimePreflightResult, OpenAIRealtimeSession; Functions: preflight |
| [backend/app/integrations/twilio.py](E:/Projects/Ai_receptionist/backend/app/integrations/twilio.py) | 93 | Classes: WhatsAppDelivery, TwilioWhatsAppClient |
| [backend/app/main.py](E:/Projects/Ai_receptionist/backend/app/main.py) | 81 | Main FastAPI application, middleware, errors and maintenance lifespan. |
| [backend/app/repositories/__init__.py](E:/Projects/Ai_receptionist/backend/app/repositories/__init__.py) | 1 | Python package marker. |
| [backend/app/repositories/memberships.py](E:/Projects/Ai_receptionist/backend/app/repositories/memberships.py) | 31 | Classes: Membership; Functions: list_active_memberships |
| [backend/app/sarvam_main.py](E:/Projects/Ai_receptionist/backend/app/sarvam_main.py) | 36 | Separate Sarvam shared-secret tool gateway. |
| [backend/app/schemas/__init__.py](E:/Projects/Ai_receptionist/backend/app/schemas/__init__.py) | 1 | Python package marker. |
| [backend/app/schemas/common.py](E:/Projects/Ai_receptionist/backend/app/schemas/common.py) | 6 | Classes: HealthResponse |
| [backend/app/schemas/identity.py](E:/Projects/Ai_receptionist/backend/app/schemas/identity.py) | 14 | Classes: MembershipResponse, PrincipalResponse |
| [backend/app/security/__init__.py](E:/Projects/Ai_receptionist/backend/app/security/__init__.py) | 1 | Python package marker. |
| [backend/app/security/auth.py](E:/Projects/Ai_receptionist/backend/app/security/auth.py) | 124 | Classes: Principal; Functions: get_jwks_client, _decode_token, get_current_principal, _resolve_principal_with_supabase |
| [backend/app/services/__init__.py](E:/Projects/Ai_receptionist/backend/app/services/__init__.py) | 1 | Python package marker. |
| [backend/app/services/booking_errors.py](E:/Projects/Ai_receptionist/backend/app/services/booking_errors.py) | 64 | Functions: translate_booking_db_error |
| [backend/app/services/health.py](E:/Projects/Ai_receptionist/backend/app/services/health.py) | 30 | Functions: database_is_ready |
| [backend/app/services/maintenance.py](E:/Projects/Ai_receptionist/backend/app/services/maintenance.py) | 49 | Functions: run_maintenance |
| [backend/app/services/schedule_generation.py](E:/Projects/Ai_receptionist/backend/app/services/schedule_generation.py) | 195 | Functions: generate_sessions, rebuild_assignment_sessions |
| [backend/app/voice_main.py](E:/Projects/Ai_receptionist/backend/app/voice_main.py) | 27 | Alternative voice-only FastAPI entry point. |
| [backend/app/voicelink_main.py](E:/Projects/Ai_receptionist/backend/app/voicelink_main.py) | 29 | Alternative voice and observer FastAPI entry point. |

**Agent orchestration and tools**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [backend/app/agent/__init__.py](E:/Projects/Ai_receptionist/backend/app/agent/__init__.py) | 1 | Python package marker. |
| [backend/app/agent/dialogue.py](E:/Projects/Ai_receptionist/backend/app/agent/dialogue.py) | 164 | Functions: caller_utterance, explicit_confirmation, offer_readback, confirmation_reply |
| [backend/app/agent/graph.py](E:/Projects/Ai_receptionist/backend/app/agent/graph.py) | 566 | Classes: AgentState, AvailabilityInput, DepartmentSuggestionInput, CallerFamilyInput, ClinicInformationInput, VerifyCodeInput, UpcomingAppointmentsInput, PrepareBookingOfferInput, ConfirmBookingOfferInput, CancelAppointmentInput, RescheduleAppointmentInput; Functions: build_tools, _explicit_confirmation, build_graph |
| [backend/app/agent/operation_service.py](E:/Projects/Ai_receptionist/backend/app/agent/operation_service.py) | 138 | Classes: TrackedCall, VoiceOperationService |
| [backend/app/agent/policy.py](E:/Projects/Ai_receptionist/backend/app/agent/policy.py) | 74 | Module setup / executable configuration. |
| [backend/app/agent/service.py](E:/Projects/Ai_receptionist/backend/app/agent/service.py) | 144 | Classes: ReceptionAgent |
| [backend/app/agent/tools.py](E:/Projects/Ai_receptionist/backend/app/agent/tools.py) | 1708 | Classes: ToolExecutor; Functions: _normalize_doctor_name, _match_doctor, _best_doctor_match, _best_department_match, _problem_route, _format_clinic_datetime |

**Backend APIs**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [backend/app/api/__init__.py](E:/Projects/Ai_receptionist/backend/app/api/__init__.py) | 1 | Python package marker. |
| [backend/app/api/router.py](E:/Projects/Ai_receptionist/backend/app/api/router.py) | 24 | Module setup / executable configuration. |
| [backend/app/api/routes/__init__.py](E:/Projects/Ai_receptionist/backend/app/api/routes/__init__.py) | 1 | Python package marker. |
| [backend/app/api/routes/agent.py](E:/Projects/Ai_receptionist/backend/app/api/routes/agent.py) | 36 | Classes: AgentChatRequest; Functions: chat_with_reception_agent |
| [backend/app/api/routes/availability.py](E:/Projects/Ai_receptionist/backend/app/api/routes/availability.py) | 77 | Functions: list_availability, generate_schedule |
| [backend/app/api/routes/bookings.py](E:/Projects/Ai_receptionist/backend/app/api/routes/bookings.py) | 602 | Classes: HoldRequest, CancelRequest, VisitStatusRequest, RescheduleRequest, BookingIntakeRequest, PaymentConfirmRequest; Functions: require_booking_staff, booking_options, create_booking_intake, list_appointments, update_visit_status, create_hold, confirm_hold, cancel, reschedule |
| [backend/app/api/routes/configuration.py](E:/Projects/Ai_receptionist/backend/app/api/routes/configuration.py) | 797 | Classes: OrganizationUpdate, LocationCreate, LocationUpdate, DepartmentCreate, DepartmentUpdate, AssignmentCreate, ScheduleRuleCreate, ActiveUpdate, ScheduleExceptionCreate, AssignmentUpdate, ScheduleRuleUpdate; Functions: require_org_admin, require_org_member, set_actor, ensure_schedule_does_not_overlap, get_configuration, update_organization, create_location, create_department, update_location, create_assignment, create_schedule_rule, create_schedule_exception, update_department, update_assignment, delete_assignment, update_schedule_rule |
| [backend/app/api/routes/health.py](E:/Projects/Ai_receptionist/backend/app/api/routes/health.py) | 20 | Functions: liveness, readiness |
| [backend/app/api/routes/me.py](E:/Projects/Ai_receptionist/backend/app/api/routes/me.py) | 20 | Functions: get_me |
| [backend/app/api/routes/patients.py](E:/Projects/Ai_receptionist/backend/app/api/routes/patients.py) | 553 | Classes: PatientUpdate, PatientContactUpdate; Functions: require_booking_staff, list_patients, get_caller_profile, update_patient, update_patient_contact, delete_patient, unlink_patient_contact |
| [backend/app/api/routes/presentation.py](E:/Projects/Ai_receptionist/backend/app/api/routes/presentation.py) | 85 | Functions: authorize, calls, events |
| [backend/app/api/routes/sarvam.py](E:/Projects/Ai_receptionist/backend/app/api/routes/sarvam.py) | 107 | Classes: CallerLookupRequest, AvailabilityRequest, PrepareBookingRequest, ConfirmBookingRequest; Functions: require_sarvam, run_tool, caller_lookup, availability, prepare_booking, confirm_booking |
| [backend/app/api/routes/voice.py](E:/Projects/Ai_receptionist/backend/app/api/routes/voice.py) | 180 | Functions: _signed_twilio_parameters, inbound_voice, stream_status, voice_media, _valid_voicelink_token, voicelink_media, voicelink_events |

**Voice domain, transport and presentation**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [backend/app/voice/__init__.py](E:/Projects/Ai_receptionist/backend/app/voice/__init__.py) | 1 | Python package marker. |
| [backend/app/voice/approval.py](E:/Projects/Ai_receptionist/backend/app/voice/approval.py) | 102 | Functions: _normalize, is_explicit_approval, invalidates_pending_offer |
| [backend/app/voice/booking_controller.py](E:/Projects/Ai_receptionist/backend/app/voice/booking_controller.py) | 111 | Classes: PendingBooking, VoiceBookingController |
| [backend/app/voice/call_runtime.py](E:/Projects/Ai_receptionist/backend/app/voice/call_runtime.py) | 271 | Classes: VoiceCallRuntime |
| [backend/app/voice/caller_items.py](E:/Projects/Ai_receptionist/backend/app/voice/caller_items.py) | 54 | Classes: CallerItem, CallerItems |
| [backend/app/voice/codec.py](E:/Projects/Ai_receptionist/backend/app/voice/codec.py) | 259 | Classes: Pcm24kToAlaw8k, TurnEvent, MulawTurnDetector, AlawTurnDetector; Functions: mulaw_to_pcm16_sample, pcm16_sample_to_mulaw, mulaw8k_to_wav, pcm24k_to_mulaw8k, alaw_to_pcm16_sample, pcm16_sample_to_alaw, alaw8k_to_wav, pcm24k_to_alaw8k, alaw8k_to_pcm24k, mulaw_energy |
| [backend/app/voice/confirmation_intent.py](E:/Projects/Ai_receptionist/backend/app/voice/confirmation_intent.py) | 71 | Classes: ConfirmationIntent, ConfirmationIntentClassifier |
| [backend/app/voice/events.py](E:/Projects/Ai_receptionist/backend/app/voice/events.py) | 51 | Classes: VoiceEventType, VoiceEvent |
| [backend/app/voice/gateway.py](E:/Projects/Ai_receptionist/backend/app/voice/gateway.py) | 213 | Classes: VoiceProtocolError, TwilioVoiceGateway |
| [backend/app/voice/presentation.py](E:/Projects/Ai_receptionist/backend/app/voice/presentation.py) | 274 | Classes: PresentationStore, Scope; Functions: redact, tool_scope, presentation_scope, start_call, emit, dialogue, available_tools, selected_tool, audio_transfer, response_fragment, voice_event, safe_result, safe_arguments, committed |
| [backend/app/voice/proposals.py](E:/Projects/Ai_receptionist/backend/app/voice/proposals.py) | 30 | Classes: BookingProposal; Functions: booking_proposal |
| [backend/app/voice/readback.py](E:/Projects/Ai_receptionist/backend/app/voice/readback.py) | 89 | Classes: PlaybackStatus, ReadbackSegment, ReadbackPlaybackLedger |
| [backend/app/voice/readback_player.py](E:/Projects/Ai_receptionist/backend/app/voice/readback_player.py) | 64 | Classes: AlawSynthesizer, ControlledReadbackPlayer |
| [backend/app/voice/readback_text.py](E:/Projects/Ai_receptionist/backend/app/voice/readback_text.py) | 58 | Functions: booking_readback, _format_fee |
| [backend/app/voice/realtime_policy.py](E:/Projects/Ai_receptionist/backend/app/voice/realtime_policy.py) | 66 | Functions: _clean_context_value, _caller_context, receptionist_instructions |
| [backend/app/voice/realtime_prompt.txt](E:/Projects/Ai_receptionist/backend/app/voice/realtime_prompt.txt) | 777 | Receptionist policy template populated with clinic/caller context. |
| [backend/app/voice/security.py](E:/Projects/Ai_receptionist/backend/app/voice/security.py) | 76 | Functions: twilio_signature, valid_twilio_signature, create_stream_binding, verify_stream_binding |
| [backend/app/voice/session.py](E:/Projects/Ai_receptionist/backend/app/voice/session.py) | 193 | Classes: CallStateError, CallerTurn, OperationProposal, CallSession |
| [backend/app/voice/session_store.py](E:/Projects/Ai_receptionist/backend/app/voice/session_store.py) | 236 | Classes: PersistedCallSession, CallSessionStore; Functions: _json_payload |
| [backend/app/voice/voicelink_gateway.py](E:/Projects/Ai_receptionist/backend/app/voice/voicelink_gateway.py) | 852 | Classes: CapturedTurn, VoiceLinkVoiceGateway; Functions: _phone_digits, _normalize_e164_phone, _is_outbound_media, _split_sentences, _longest_common_ngram, _is_human_request, _is_self_echo |
| [backend/app/voice/voicelink_realtime_gateway.py](E:/Projects/Ai_receptionist/backend/app/voice/voicelink_realtime_gateway.py) | 1037 | Classes: VoiceLinkRealtimeGateway |

**Operational and diagnostic scripts**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [backend/check_voice_booking_readiness.py](E:/Projects/Ai_receptionist/backend/check_voice_booking_readiness.py) | 47 | Functions: main |
| [backend/check_voice_confirmation_intent.py](E:/Projects/Ai_receptionist/backend/check_voice_confirmation_intent.py) | 40 | Functions: main |
| [backend/scripts/check_sweta_availability.py](E:/Projects/Ai_receptionist/backend/scripts/check_sweta_availability.py) | 43 | Functions: main |
| [backend/scripts/configure_twilio_voice.py](E:/Projects/Ai_receptionist/backend/scripts/configure_twilio_voice.py) | 47 | Changes Twilio webhook configuration; not run. |
| [backend/scripts/configure_voicelink_env.py](E:/Projects/Ai_receptionist/backend/scripts/configure_voicelink_env.py) | 20 | Updates local voice environment configuration; not run. |
| [backend/scripts/discover_sarvam_voice.py](E:/Projects/Ai_receptionist/backend/scripts/discover_sarvam_voice.py) | 105 | Provider discovery and environment update helper; not run. |
| [backend/scripts/probe_voice_startup.py](E:/Projects/Ai_receptionist/backend/scripts/probe_voice_startup.py) | 59 | Functions: probe |
| [backend/scripts/realtime_preflight.py](E:/Projects/Ai_receptionist/backend/scripts/realtime_preflight.py) | 31 | Functions: main |
| [backend/scripts/smoke_openai_audio.py](E:/Projects/Ai_receptionist/backend/scripts/smoke_openai_audio.py) | 24 | Functions: main |
| [backend/scripts/smoke_voice_webhook.py](E:/Projects/Ai_receptionist/backend/scripts/smoke_voice_webhook.py) | 35 | Functions: main |
| [backend/scripts/smoke_voicelink.py](E:/Projects/Ai_receptionist/backend/scripts/smoke_voicelink.py) | 49 | Functions: main |
| [backend/scripts/start_test_voice_call.py](E:/Projects/Ai_receptionist/backend/scripts/start_test_voice_call.py) | 85 | Initiates an external outbound telephone test; not run. |
| [scripts/seed_demo_rehearsal.py](E:/Projects/Ai_receptionist/scripts/seed_demo_rehearsal.py) | 356 | Mutating database rehearsal seed; not run. |

**Backend tests**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [backend/tests/test_agent.py](E:/Projects/Ai_receptionist/backend/tests/test_agent.py) | 605 | 18 test functions before parameterization. test_agent_refuses_to_run_without_backend_configuration; test_phase_three_tools_keep_private_records_behind_verification; test_voice_doctor_name_variants_resolve_to_canonical_assignment … |
| [backend/tests/test_booking_errors.py](E:/Projects/Ai_receptionist/backend/tests/test_booking_errors.py) | 37 | 4 test functions before parameterization. test_capacity_conflict_has_a_stable_safe_code; test_exact_slot_conflict_has_a_stable_safe_code; test_unknown_database_failure_is_not_misclassified … |
| [backend/tests/test_caller_items.py](E:/Projects/Ai_receptionist/backend/tests/test_caller_items.py) | 32 | 2 test functions before parameterization. test_transcripts_delivered_once_in_speech_order_with_original_timestamp; test_unknown_items_and_overload_fail_closed |
| [backend/tests/test_confirmation_intent.py](E:/Projects/Ai_receptionist/backend/tests/test_confirmation_intent.py) | 48 | 3 test functions before parameterization. test_structured_intent_validated_and_readback_supplied; test_invalid_or_refused_classification_never_confirms; test_timeout_never_confirms |
| [backend/tests/test_conversation_reliability.py](E:/Projects/Ai_receptionist/backend/tests/test_conversation_reliability.py) | 293 | 8 test functions before parameterization. test_barge_in_requires_sustained_speech_and_preserves_start_of_utterance; test_voicelink_preserves_completed_turns_while_worker_is_busy; test_short_caller_repetitions_are_not_dropped_as_echo … |
| [backend/tests/test_demo_dialogue.py](E:/Projects/Ai_receptionist/backend/tests/test_demo_dialogue.py) | 342 | 11 test functions before parameterization. test_non_consent_and_changed_fields_are_rejected; test_clear_bilingual_acceptance; test_only_matching_offer_name_may_be_repeated_in_acceptance … |
| [backend/tests/test_g2_database.py](E:/Projects/Ai_receptionist/backend/tests/test_g2_database.py) | 748 | 8 test functions before parameterization. test_hold_replay_exact_slot_and_confirmation_are_idempotent; test_expired_hold_releases_slot_and_fails_simulated_payment; test_token_cancellation_frees_capacity_without_reusing_numbers … |
| [backend/tests/test_health.py](E:/Projects/Ai_receptionist/backend/tests/test_health.py) | 83 | 5 test functions before parameterization. test_liveness_has_correlation_id; test_readiness_reports_unconfigured_database; test_me_requires_a_bearer_token … |
| [backend/tests/test_openai_realtime.py](E:/Projects/Ai_receptionist/backend/tests/test_openai_realtime.py) | 141 | 6 test functions before parameterization. test_voice_event_has_correlated_identifiers_without_transcript; test_audio_only_configuration_uses_semantic_vad_and_pcm; test_voice_configuration_accepts_gateway_instructions … |
| [backend/tests/test_phase2_discovery.py](E:/Projects/Ai_receptionist/backend/tests/test_phase2_discovery.py) | 197 | 6 test functions before parameterization. test_doctor_name_normalization; test_ambiguous_doctor_detection; test_search_availability_returns_ambiguous_doctor_error … |
| [backend/tests/test_phase3_voicelink.py](E:/Projects/Ai_receptionist/backend/tests/test_phase3_voicelink.py) | 157 | 4 test functions before parameterization. test_human_request_detection; test_self_echo_does_not_suppress_slot_repetition; test_incoming_speech_barge_in_sends_clear_event … |
| [backend/tests/test_phase4_operations.py](E:/Projects/Ai_receptionist/backend/tests/test_phase4_operations.py) | 294 | 6 test functions before parameterization. test_dialogue_cancellation_and_reschedule_replies; test_cancel_appointment_authorized_caller; test_cancel_appointment_unauthorized_caller_denied … |
| [backend/tests/test_presentation_observer.py](E:/Projects/Ai_receptionist/backend/tests/test_presentation_observer.py) | 139 | 7 test functions before parameterization. test_identity_and_audio_are_observed_without_phone_or_audio_payload; test_database_wrapper_marks_actual_return_and_failure; test_manifest_and_selection_are_distinct_from_execution … |
| [backend/tests/test_realtime_policy.py](E:/Projects/Ai_receptionist/backend/tests/test_realtime_policy.py) | 50 | 1 test functions before parameterization. test_realtime_policy_prevents_repeated_introductions_and_unnatural_delivery |
| [backend/tests/test_scenarios.py](E:/Projects/Ai_receptionist/backend/tests/test_scenarios.py) | 399 | 6 test functions before parameterization. test_scenario_1_registered_caller_booking_for_registered_mother; test_scenario_2_registered_caller_booking_for_unregistered_family_member; test_scenario_3_symptom_routing_to_general_medicine … |
| [backend/tests/test_schedule_generation.py](E:/Projects/Ai_receptionist/backend/tests/test_schedule_generation.py) | 157 | 3 test functions before parameterization. test_closed_exception_suppresses_generated_session; test_replacement_hours_override_weekly_times; test_weekly_overlap_is_rejected_before_generation |
| [backend/tests/test_twilio.py](E:/Projects/Ai_receptionist/backend/tests/test_twilio.py) | 52 | 2 test functions before parameterization. test_twilio_whatsapp_adapter_normalizes_recipient_and_hides_credentials; test_twilio_whatsapp_adapter_requires_backend_configuration |
| [backend/tests/test_voice.py](E:/Projects/Ai_receptionist/backend/tests/test_voice.py) | 340 | 13 test functions before parameterization. test_mulaw_turn_detector_finalizes_speech_after_silence; test_pcm_downsampling_outputs_twilio_rate; test_alaw_codec_and_turn_detector_support_voicelink_audio … |
| [backend/tests/test_voice_approval.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_approval.py) | 46 | 4 test functions before parameterization. test_explicit_approval_requires_clear_confirmation; test_short_or_ambiguous_reply_is_not_approval; test_rejection_or_correction_invalidates_pending_offer … |
| [backend/tests/test_voice_atomic_booking.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_atomic_booking.py) | 169 | 2 test functions before parameterization. test_booking_and_operation_share_commit_and_failures_never_report_success; test_cancel_and_reschedule_use_the_same_atomic_approval_boundary |
| [backend/tests/test_voice_booking_controller.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_booking_controller.py) | 92 | 2 test functions before parameterization. test_booking_controller_requires_ack_then_later_explicit_approval; test_correction_invalidates_readback_before_approval |
| [backend/tests/test_voice_call_runtime.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_call_runtime.py) | 120 | 4 test functions before parameterization. test_runtime_creates_one_durable_owner_fence_per_call; test_uncertain_start_is_not_retried; test_preparation_and_carrier_ack_are_committed_and_reject_early_approval … |
| [backend/tests/test_voice_operation_service.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_operation_service.py) | 94 | 2 test functions before parameterization. test_operation_service_requires_readback_before_approval_and_records_lifecycle; test_operation_service_requires_carrier_ack_for_controlled_readback |
| [backend/tests/test_voice_pacing.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_pacing.py) | 95 | 4 test functions before parameterization. test_buffered_and_streamed_speech_use_same_profile_and_keep_full_text; test_speech_errors_are_not_swallowed_and_long_readbacks_are_not_truncated; test_cached_speech_isolated_by_voice_speed_model_and_clinic … |
| [backend/tests/test_voice_proposals.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_proposals.py) | 26 | 2 test functions before parameterization. test_booking_proposal_never_exposes_the_signed_offer_token; test_booking_proposal_rejects_failed_or_incomplete_offer |
| [backend/tests/test_voice_readback.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_readback.py) | 44 | 3 test functions before parameterization. test_only_matching_sent_segment_can_be_acknowledged; test_interrupt_invalidates_a_pending_readback_and_stale_mark; test_next_readback_interrupts_the_previous_segment |
| [backend/tests/test_voice_readback_player.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_readback_player.py) | 94 | 4 test functions before parameterization. test_readback_player_sends_isolated_media_and_matching_mark; test_readback_player_does_not_leave_failed_tts_segment_authorizable; test_interruption_during_synthesis_sends_no_audio_or_mark … |
| [backend/tests/test_voice_readback_text.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_readback_text.py) | 24 | 2 test functions before parameterization. test_booking_readback_includes_all_critical_details_in_hinglish; test_booking_readback_requires_every_critical_detail |
| [backend/tests/test_voice_session.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_session.py) | 78 | 5 test functions before parameterization. test_delayed_transcript_cannot_turn_early_speech_into_consent; test_only_a_turn_after_completed_readback_can_approve; test_correction_invalidates_an_offer_before_it_can_be_confirmed … |
| [backend/tests/test_voice_session_store.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_session_store.py) | 147 | 5 test functions before parameterization. test_reconciliation_requires_positive_scoped_commit_evidence; test_store_uses_owner_and_version_compare_and_swap; test_store_rejects_stale_owner_or_version … |
| [backend/tests/test_voice_startup.py](E:/Projects/Ai_receptionist/backend/tests/test_voice_startup.py) | 73 | 2 test functions before parameterization. test_greeting_sends_audio_before_synthesis_finishes_and_without_filler_lock; test_failed_greeting_stream_does_not_cache_partial_audio |
| [backend/tests/test_voicelink_realtime_gateway.py](E:/Projects/Ai_receptionist/backend/tests/test_voicelink_realtime_gateway.py) | 980 | 30 test functions before parameterization. test_voice_instructions_use_trusted_organization_context; test_voice_instructions_prefetch_saved_family_for_authenticated_caller; test_booking_offer_is_read_back_without_leaking_signed_token … |

**Frontend configuration and tests**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [frontend/.env.example](E:/Projects/Ai_receptionist/frontend/.env.example) | 3 | Environment variable template. |
| [frontend/index.html](E:/Projects/Ai_receptionist/frontend/index.html) | 14 | Build, entry-point, dependency or repository configuration. |
| [frontend/package-lock.json](E:/Projects/Ai_receptionist/frontend/package-lock.json) | 2741 | Resolved npm dependency lock. |
| [frontend/package.json](E:/Projects/Ai_receptionist/frontend/package.json) | 25 | Frontend dependencies and dev/typecheck/build commands. |
| [frontend/tests/presentation.test.mjs](E:/Projects/Ai_receptionist/frontend/tests/presentation.test.mjs) | 77 | 11 Node regression tests for presentation state, streaming and source wiring. |
| [frontend/tsconfig.app.json](E:/Projects/Ai_receptionist/frontend/tsconfig.app.json) | 21 | Build, entry-point, dependency or repository configuration. |
| [frontend/tsconfig.json](E:/Projects/Ai_receptionist/frontend/tsconfig.json) | 8 | Build, entry-point, dependency or repository configuration. |
| [frontend/tsconfig.node.json](E:/Projects/Ai_receptionist/frontend/tsconfig.node.json) | 16 | Build, entry-point, dependency or repository configuration. |
| [frontend/vercel.json](E:/Projects/Ai_receptionist/frontend/vercel.json) | 12 | Vite build and SPA route rewrite. |
| [frontend/vite.config.ts](E:/Projects/Ai_receptionist/frontend/vite.config.ts) | 11 | Build, entry-point, dependency or repository configuration. |

**Frontend source**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [frontend/src/App.tsx](E:/Projects/Ai_receptionist/frontend/src/App.tsx) | 193 | Authentication, workspace state, polling, navigation and booking handlers; legacy components remain. |
| [frontend/src/components/AdminSettingsPage.tsx](E:/Projects/Ai_receptionist/frontend/src/components/AdminSettingsPage.tsx) | 373 | Clinic, departments, doctors, fees and weekly hours. |
| [frontend/src/components/AiAssistantPage.tsx](E:/Projects/Ai_receptionist/frontend/src/components/AiAssistantPage.tsx) | 88 | Staff chat UI with a per-mount thread ID. |
| [frontend/src/components/AppointmentsManager.tsx](E:/Projects/Ai_receptionist/frontend/src/components/AppointmentsManager.tsx) | 47 | Appointment filters, payment/status display and visit actions. |
| [frontend/src/components/AvailabilityPage.tsx](E:/Projects/Ai_receptionist/frontend/src/components/AvailabilityPage.tsx) | 68 | Doctor availability cards and week calendar. |
| [frontend/src/components/BookingPage.tsx](E:/Projects/Ai_receptionist/frontend/src/components/BookingPage.tsx) | 117 | Session choice, caller/patient form and payment choice. |
| [frontend/src/components/Observatory.tsx](E:/Projects/Ai_receptionist/frontend/src/components/Observatory.tsx) | 177 | Architecture canvas and observed-event selection. |
| [frontend/src/components/OverviewPage.tsx](E:/Projects/Ai_receptionist/frontend/src/components/OverviewPage.tsx) | 202 | Operational overview derived from loaded records. |
| [frontend/src/components/PatientsPage.tsx](E:/Projects/Ai_receptionist/frontend/src/components/PatientsPage.tsx) | 204 | Caller/family directory, editing and purge workflows. |
| [frontend/src/components/PresentationCinematic.css](E:/Projects/Ai_receptionist/frontend/src/components/PresentationCinematic.css) | 280 | Presentation styles. |
| [frontend/src/components/PresentationPage.css](E:/Projects/Ai_receptionist/frontend/src/components/PresentationPage.css) | 4 | Presentation styles. |
| [frontend/src/components/PresentationPage.tsx](E:/Projects/Ai_receptionist/frontend/src/components/PresentationPage.tsx) | 417 | Live/rehearsal control, stream following, pacing and layout. |
| [frontend/src/components/PresentationPolish.css](E:/Projects/Ai_receptionist/frontend/src/components/PresentationPolish.css) | 280 | Presentation styles. |
| [frontend/src/components/PresentationTruth.css](E:/Projects/Ai_receptionist/frontend/src/components/PresentationTruth.css) | 15 | Presentation styles. |
| [frontend/src/lib/supabaseAuth.ts](E:/Projects/Ai_receptionist/frontend/src/lib/supabaseAuth.ts) | 17 | Custom REST login and localStorage session helper. |
| [frontend/src/main.tsx](E:/Projects/Ai_receptionist/frontend/src/main.tsx) | 14 | Build, entry-point, dependency or repository configuration. |
| [frontend/src/presentation/state.ts](E:/Projects/Ai_receptionist/frontend/src/presentation/state.ts) | 106 | Appointment/event reducers, pacing and authenticated reconnect loop. |
| [frontend/src/presentation/trace.ts](E:/Projects/Ai_receptionist/frontend/src/presentation/trace.ts) | 113 | Synthetic scenarios and heartbeat-aware SSE parser. |
| [frontend/src/styles.css](E:/Projects/Ai_receptionist/frontend/src/styles.css) | 687 | Staff workspace styles. |
| [frontend/src/vite-env.d.ts](E:/Projects/Ai_receptionist/frontend/src/vite-env.d.ts) | 1 | Build, entry-point, dependency or repository configuration. |

**Database migrations**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [supabase/migrations/20260910000100_phase1_tenant_foundation.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260910000100_phase1_tenant_foundation.sql) | 295 | Phase: 1 — Foundation, tenancy and authenticated skeleton Requirements: TEN-01, TEN-02, IAM-01, DOC-01, SEC-01, OBS-01 |
| [supabase/migrations/20260911000100_phase2_scheduling.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000100_phase2_scheduling.sql) | 240 | Phase: 2.1 — Scheduling foundation Requirements: SCH-01, SCH-02, DOC-01, TEN-01, TEN-02 |
| [supabase/migrations/20260911000200_phase2_contact_patient_identity.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000200_phase2_contact_patient_identity.sql) | 136 | Phase: 2.2a — Contact and patient identity Requirements: PAT-01, PAT-02, RET-01, TEN-01 |
| [supabase/migrations/20260911000300_phase2_appointments.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000300_phase2_appointments.sql) | 174 | Phase: 2.2b — Appointment, authorization, verification and simulated payment records Requirements: QUE-01, PAT-02, RET-01, RET-02, CHG-01 |
| [supabase/migrations/20260911000400_phase2_transactional_booking.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000400_phase2_transactional_booking.sql) | 227 | Phase: 2.2c — Transactional holds, confirmation, expiry and token allocation Requirements: SCH-02, QUE-01, CHG-01, PAY-01 |
| [supabase/migrations/20260911000500_phase2_cancellation_outbox.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000500_phase2_cancellation_outbox.sql) | 77 | Phase: 2.3a — Cancellation and durable notification outbox Apply after 20260911000400_phase2_transactional_booking.sql. |
| [supabase/migrations/20260911000600_phase2_rescheduling.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000600_phase2_rescheduling.sql) | 51 | Phase: 2.3b — Atomic staff rescheduling Apply after 20260911000500_phase2_cancellation_outbox.sql. |
| [supabase/migrations/20260911000700_phase2_function_variable_resolution.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000700_phase2_function_variable_resolution.sql) | 60 | Phase 2 corrective migration: make table-column resolution explicit in functions whose RETURNS TABLE fields overlap names such as status. |
| [supabase/migrations/20260911000800_phase2_simulated_payment_default.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000800_phase2_simulated_payment_default.sql) | 29 | Phase 2 corrective migration: holds use the local payment simulator by default. Apply after 20260911000700_phase2_function_variable_resolution.sql. |
| [supabase/migrations/20260911000900_phase2_payment_methods.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911000900_phase2_payment_methods.sql) | 39 | Phase 2 payment-method capture for manual and AI-assisted bookings. Existing prototype payment processing remains simulated. |
| [supabase/migrations/20260911001000_phase2_relationship_integrity.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911001000_phase2_relationship_integrity.sql) | 60 | Phase 2 corrective migration: deterministic caller/patient relationship integrity. One active E.164 mobile belongs to one contact per organization (existing index). |
| [supabase/migrations/20260911001100_phase2_verification_challenge_operations.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911001100_phase2_verification_challenge_operations.sql) | 177 | Phase: 2.2d — Verification challenge lifecycle Requirements: RET-01, RET-02, CHG-01 |
| [supabase/migrations/20260911001200_phase2_durable_booking_side_effects.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911001200_phase2_durable_booking_side_effects.sql) | 174 | Phase: 2.3c — Durable booking side effects and provider work queues Requirements: PAY-01, MSG-01, OBS-01 |
| [supabase/migrations/20260911001300_phase2_quote_consent_snapshots.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911001300_phase2_quote_consent_snapshots.sql) | 178 | Phase: 2.2d — Immutable booking quote and explicit consent snapshots Requirements: BKG-01 |
| [supabase/migrations/20260911001400_india_localization.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911001400_india_localization.sql) | 89 | Move the Geeta Medicine demo from Nepal defaults to India defaults. Existing appointment and payment rows belong to this synthetic demo, so their |
| [supabase/migrations/20260911001400_phase2_session_windows_only.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260911001400_phase2_session_windows_only.sql) | 6 | Preserve all historical data while preventing creation of new exact-time rules. |
| [supabase/migrations/20260912000100_voice_call_sessions.sql](E:/Projects/Ai_receptionist/supabase/migrations/20260912000100_voice_call_sessions.sql) | 69 | Durable, versioned session and operation ledger for telephone voice calls. Additive migration: existing appointments and booking idempotency are unchanged. |
| [supabase/migrations/README.md](E:/Projects/Ai_receptionist/supabase/migrations/README.md) | 31 | Supabase migration convention. |

**Database seeds**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [supabase/seeds/20260911000100_geeta_medicine_synthetic_demo.sql](E:/Projects/Ai_receptionist/supabase/seeds/20260911000100_geeta_medicine_synthetic_demo.sql) | 29 | Synthetic demo setup only. Run after Phase 2 migrations. Creates Geeta Medicine, Main Branch, Dr Amit Sharma, exact-time and token schedules. |
| [supabase/seeds/20260911000200_attach_geeta_admin.sql](E:/Projects/Ai_receptionist/supabase/seeds/20260911000200_attach_geeta_admin.sql) | 36 | Run after creating a demo user in Supabase Dashboard -> Authentication -> Users. Replace the UUID below with that user's ID. Do not put an email or password here. |
| [supabase/seeds/20260913000100_remove_stray_g2_test_data.sql](E:/Projects/Ai_receptionist/supabase/seeds/20260913000100_remove_stray_g2_test_data.sql) | 75 | Remove only synthetic tenants left by backend/tests/test_g2_database.py. Keeps unrelated organizations and transfers their test user's membership to |
| [supabase/seeds/20260913000200_geeta_conference_demo.sql](E:/Projects/Ai_receptionist/supabase/seeds/20260913000200_geeta_conference_demo.sql) | 211 | Idempotent Geeta Medicine conference dataset. Azure must use VOICE_ORGANIZATION_ID=c562e817-bfae-4428-904d-15ac84b9acd7. |

**Database verification**

| File | Lines | Purpose / declared structure |
| --- | ---: | --- |
| [supabase/verification/20260910000100_phase1_tenant_foundation_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260910000100_phase1_tenant_foundation_checks.sql) | 75 | Run after 20260910000100_phase1_tenant_foundation.sql. Read-only: returns one JSON result containing every Phase 1 verification check. |
| [supabase/verification/20260911000100_phase2_scheduling_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911000100_phase2_scheduling_checks.sql) | 20 | Run after 20260911000100_phase2_scheduling.sql. Read-only single-result verification. |
| [supabase/verification/20260911000200_phase2_contact_patient_identity_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911000200_phase2_contact_patient_identity_checks.sql) | 14 | Run after 20260911000200_phase2_contact_patient_identity.sql. Read-only single-result verification. |
| [supabase/verification/20260911000300_phase2_appointments_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911000300_phase2_appointments_checks.sql) | 13 | Run after 20260911000300_phase2_appointments.sql. Read-only single-result verification. |
| [supabase/verification/20260911000400_phase2_transactional_booking_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911000400_phase2_transactional_booking_checks.sql) | 11 | Run after 20260911000400_phase2_transactional_booking.sql. Read-only single-result verification. |
| [supabase/verification/20260911000500_phase2_cancellation_outbox_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911000500_phase2_cancellation_outbox_checks.sql) | 9 | Read-only verification for 20260911000500_phase2_cancellation_outbox.sql. |
| [supabase/verification/20260911000600_phase2_rescheduling_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911000600_phase2_rescheduling_checks.sql) | 1 | SQL verification or fixture statements. |
| [supabase/verification/20260911001100_phase2_verification_challenge_operations_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911001100_phase2_verification_challenge_operations_checks.sql) | 19 | SQL verification or fixture statements. |
| [supabase/verification/20260911001200_phase2_durable_booking_side_effects_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911001200_phase2_durable_booking_side_effects_checks.sql) | 21 | SQL verification or fixture statements. |
| [supabase/verification/20260911001300_phase2_quote_consent_snapshots_checks.sql](E:/Projects/Ai_receptionist/supabase/verification/20260911001300_phase2_quote_consent_snapshots_checks.sql) | 12 | SQL verification or fixture statements. |

**Suggested reading order**

1. Main app, router, settings and authentication.
2. Manual booking: App.tsx → booking routes → SQL hold/confirmation.
3. Realtime booking: gateway → runtime → domain session/persistence → ToolExecutor.
4. Compare Chained gateway → ReceptionAgent → graph against Realtime consent enforcement.
5. Trace overview, appointment and calendar read models back to API limits and date windows.
6. Presentation reducers/parser alongside observer capture and SSE routes.
7. Tests by module, followed by SQL acceptance in an isolated migrated database. Provider and seed scripts require deliberate target selection.
