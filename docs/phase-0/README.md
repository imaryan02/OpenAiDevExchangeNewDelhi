# Phase 0 — Product decisions and provider feasibility

Status: `IN_PROGRESS`  
PRD reference: Section 12, Phase 0 of `PRD_AND_IMPLEMENTATION_PLAN.md` (version 1.2). Use section titles because line numbers change during revisions.

## Purpose

Close the decisions and external-service assumptions that determine whether the prototype can be demonstrated as a real telephone system. This phase creates no application, database schema, provider account, secret, deployment, or paid resource.

## In scope

- Freeze the initial demo operating contract.
- Include separate contact/patient names, booking-scoped family access, returning-caller verification and AI cancellation/rescheduling in that contract.
- Confirm the actual telephone geography, timezone, fallback number availability, and authorized testers.
- Verify account access and critical technical behavior for OpenAI, Twilio, WhatsApp, and the selected hosting option.
- Prove the smallest real audio loop in an isolated spike only after the required credentials and test number are supplied.
- Record supported versus blocked capabilities, costs, replacement options, and gate evidence.

## Out of scope

- React, FastAPI, LangGraph, dashboard, database schema, SQL migrations, deployment, payment integration, and live patient data.
- Creating a new external account, buying a phone number, sending a message, placing a real call, or collecting payment without an explicit later instruction.

## Deliverables

| Artifact | Purpose | Status |
| --- | --- | --- |
| `DECISION_LOG.md` | Owner-approved product and demo decisions | Waiting for product-owner inputs |
| `PROVIDER_FEASIBILITY.md` | Evidence for each provider and fallbacks | Partially researched; account evidence pending |
| `G0_ACCEPTANCE.md` | Exact conditions for closing Gate G0 | Ready for evidence |
| `../../supabase/migrations/README.md` | Migration naming and execution convention | Ready; no SQL is intentionally present |
| `G0_ACCEPTANCE.md` response template | Collect the small set of project settings needed to test providers safely | Ready for product-owner input |
| `DEMO_PROFILE.md` | Confirmed India synthetic-demo settings and open dependencies | Partially confirmed |
| `PROVIDER_TEST_PROTOCOL.md` | Repeatable tests for India voice, transfer, bilingual audio, WhatsApp and initial capacity | Ready; awaiting account access |

## Rules

1. Record decisions by ID; do not quietly alter defaults in the PRD.
2. Do not put API keys, authentication tokens, phone numbers tied to real patients, or other secrets in these files or chat.
3. Use synthetic clinic/patient data only.
4. Mark a provider feature `VERIFIED` only with reproducible account/test evidence. Documentation alone is `RESEARCHED`.
5. Do not advance to Phase 1 until all G0 blockers are either verified or explicitly removed from the prototype scope.
