# Phase 3 status

Updated: 2026-09-11

## Completed foundation

- The authenticated staff text harness uses LangGraph and OpenAI through `ChatOpenAI`.
- Conversation state is checkpointed in process memory and isolated by organization, authenticated actor, and browser thread UUID.
- Availability and caller-family lookup tools use typed inputs and inject the organization context in the backend.
- Tool execution uses an allowlist, sequential calls, a four-call cap, and sanitized errors.
- Provider-fake tests prove tool routing and follow-up conversation memory without network calls.
- OpenAI and Twilio credentials remain backend-only.
- The Twilio WhatsApp adapter is configured, validates destinations and message length, and has mock-provider tests.
- Returning-caller tools now issue an HMAC-protected one-time code over WhatsApp, verify it
  with bounded database challenges, and require the matching verified phone challenge before
  returning upcoming appointments.
- AI bookings now use signed five-minute offers, complete quote read-back,
  explicit-language consent checks in the graph, transactional holds, idempotent confirmation,
  and simulated Online/UPI payment. Missing family profiles can be created from name and
  relationship inside the final confirmation transaction. Successful confirmation consumes
  the active offer version. The signed offer stays in private server-side graph state and is
  injected into the confirmation tool call, so it is neither exposed to nor copied by the model.

## Remaining before Gate G3

- Replace the process-memory checkpointer with PostgreSQL persistence and add retention.
- Finish structured provenance and broader dependency invalidation across correction flows.
- Add guarded cancellation and rescheduling workflows.
- Add verified cancellation/rescheduling and family-member selection for new bookings.
- Add safe medical-boundary, urgent-risk, and human-handoff routes.
- Build the bilingual deterministic and live-model evaluation suite.

No live OpenAI or Twilio message was sent by the automated test suite.
