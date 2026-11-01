# Enterprise voice-agent integration playbook — publication blueprint

Direction: practical integration handbook with Geeta Medicine and Friday engineering case studies; polished enterprise presentation. Updated 5 October 2026: the owner has relaxed the 12-page limit to prioritize beginner-accessible explanations and actionable implementation steps. The original page table below is a thematic budget, superseded by the expanded sequence that follows.

Audience: developers, architects and technical leads who know their existing enterprise application and need to add a dependable telephone voice interface. Readers should finish knowing which components to build, where authority belongs, how to choose a speech architecture, how to execute business operations safely, and how to verify the complete system.

| Page | Reader question | Essential content | Visual |
| --- | --- | --- | --- |
| 1 | What are we building and why? | Purpose, scope, vocabulary, both case studies and the voice-over-business-operations pattern | Compact product/platform map |
| 2 | Where does the voice layer fit? | Existing enterprise system, carrier gateway, identity, agent, tool adapter, transactions, operations UI; shared versus separate domain boundaries | High-level architecture diagram |
| 3 | What technology and interfaces does each layer need? | Responsibility-based stack, staff/personal UI roles, backend/Supabase boundaries, concrete repository equivalents, replaceable provider/configuration choices | Stack and ownership table |
| 4 | Should I choose Chained or Realtime? | Two speech pipelines, orchestration differences, interruption, observability, latency considerations without invented benchmarks; current Chained mutation limit | Side-by-side flow diagrams and decision table |
| 5 | How does a request become an enterprise action? | Tool contracts, allow-lists, trusted caller/tenant binding, read-only versus preview versus commit, adapter boundary to existing APIs | Small tool contract plus low-level component map |
| 6 | How does Geeta Medicine book an appointment? | Caller versus patient, grounded availability, signed offer, controlled readback, carrier mark, later consent, transaction and verified response | Booking sequence diagram |
| 7 | What must the database guarantee? | Schema groups and relationships, capacity, versions, idempotency, quote/consent snapshots, forward-only rescheduling, RLS/backend-role distinction | Selective ER diagram and invariants table |
| 8 | How does Friday continue work after a call? | Independent owner domain, tasks, bounded memory, durable follow-ups, callback attempts and delivery evidence | Follow-up lifecycle/state diagram |
| 9 | How do we trace and investigate a voice agent? | Dedicated observability section: caller/call/turn/response/tool/query/proposal/readback/commit correlation; investigation tabs, latency, interruptions, usage, capture health, privacy, LIVE versus rehearsal; unavailable provider internals and future extensions | Annotated trace waterfall and compact coverage matrix |
| 10 | How do we deploy and operate it? | Vercel/Azure/Supabase topology, credentials and channel configuration, warm startup, WebSocket/codec requirements, workers, single-process limits | Deployment diagram and compact configuration table |
| 11 | How do we prove the whole system works? | Contract tests, concurrent capacity, corrections/barge-in, late/duplicate events, commit uncertainty, unanswered callbacks, actual phone and notification acceptance | Failure/expected-behaviour test matrix |
| 12 | How do I apply this to my enterprise software? | Ordered implementation roadmap, case-study status caveats, key decisions, concise source references | Implementation checklist and readiness gates |

## Writing and design rules

- Explain the reusable mechanism first, then show the repository implementation as evidence.
- Expand STT, TTS, VAD, RLS, SSE and idempotency at first use.
- Use one diagram to explain each important boundary; avoid a diagram containing every module/table.
- Keep source code to one concise tool contract and one transaction/consent example at most. Link deeper code in source notes.
- Describe caller identity as authenticated carrier metadata under the provider trust boundary; do not imply it proves a person's identity or understanding.
- Label implemented, restricted, unverified and proposed capabilities consistently.
- Use clinic bookings as the main transactional example and Friday as the continuity/callback example.
- Reserve space for failure paths and operational verification; include essential setup commands while linking full database DDL.
- Keep the cover integrated with substantive opening content. The user relaxed the original page budget; actionable coverage takes priority.

## Pending reconciliation

The owner-supplied context schema contains all 39 public tables in the repository inventory, including observability and Personal Agent storage. It omits functions, indexes, triggers, policies/grants and migration history; the guide can now describe the table model while qualifying live safeguard deployment. Current provider choice should reflect the actual accepted configuration: source/deployment selects Twilio personal callbacks, while older documentation specifies VoiceLink. Historical live-call evidence should be dated and separated from the local checks completed on 5 October 2026.

## Expanded implementation sequence

The editable deliverable is `ENTERPRISE_VOICE_AGENT_PLAYBOOK.md`; PDF export follows content review. The revised sequence is: foundations; product boundaries; architecture/stack; Chained versus Realtime; workflow selection; reference setup; identity; enterprise tools; speech transport; consent/transactions; database; Friday continuity; frontend; observability; deployment; testing/troubleshooting; enterprise handover; checklist/references.

Each build step explains the concept, specifies the work, supplies contracts/commands where useful, names repository equivalents and gives an acceptance checkpoint. Distinguish repository commands from proposed adapter designs and synthetic examples. Include successful and interrupted booking paths, uncertain commits, bounded memory, provider acceptance/delivery states, and an enterprise adaptation recipe. Rendered page count will be established after review; completeness takes precedence over a fixed count.

Research source: [PROJECT_ANALYSIS_2026-10-05.md](E:/Projects/Ai_receptionist/docs/PROJECT_ANALYSIS_2026-10-05.md).

## Reader-review revision, version 1.1

The handbook now includes a connected setup/text/Chained/Realtime walkthrough, explicit membership/session prerequisites, prompt/context and error contracts, a runnable synthetic remote-adapter lab, a worked Friday reminder scenario, an evaluation dataset and measurable pilot-budget definitions. Historical review details moved to Appendix A; advanced terms are explained inline and in Appendix B. Source references use pinned repository links or portable relative links. A generated HTML edition embeds all nine validated Mermaid diagrams and provides offline full-size controls. Markdown remains the content source; PDF is deferred.
