import { useCallback, useEffect, useRef, useState } from "react";
import { authenticatedFetch, type AuthSession } from "../lib/supabaseAuth";
import { apiBase, formatVerified, responseMessage, type DemoRequest } from "./types";
import "./styles.css";

const tasks = [
  { kind: "RESOURCE_RECHECK", label: "Recheck Geeta resources" },
  { kind: "MATCHING_REVIEW", label: "Review candidate checks" },
  { kind: "COORDINATION_FOLLOWUP", label: "Check follow-up" },
] as const;

export function ReceivingInbox({ session, organizationId, canDecide }: { session: AuthSession; organizationId: string; canDecide: boolean }) {
  const [requests, setRequests] = useState<DemoRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [arrivalNotes, setArrivalNotes] = useState<Record<string, string>>({});
  const decisionKeys = useRef<Record<string, string>>({});
  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await authenticatedFetch(`${apiBase}/v1/hospitalos/requests?organization_id=${encodeURIComponent(organizationId)}`, session, { signal });
      if (!response.ok) throw new Error(await responseMessage(response));
      const body = await response.json() as DemoRequest[];
      if (!signal?.aborted) { setRequests(body); setError(""); }
    } catch (cause) { if (!signal?.aborted) setError(cause instanceof Error ? cause.message : "Could not load receiving requests."); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [organizationId, session]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const timer = window.setInterval(() => { void load(controller.signal); }, 3000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [load]);

  const decide = async (request: DemoRequest, decision: "ACCEPT" | "DECLINE") => {
    if (!canDecide) return;
    const actionKey = `${request.id}:${decision}`;
    decisionKeys.current[actionKey] ??= crypto.randomUUID();
    setBusy(request.id); setError(""); setMessage("");
    try {
      const response = await authenticatedFetch(`${apiBase}/v1/hospitalos/requests/${request.id}/decision`, session, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, expected_version: request.version,
          decision_key: decisionKeys.current[actionKey], decision,
          arrival_note: decision === "ACCEPT" ? (arrivalNotes[request.id] ?? "") : null }),
      });
      if (!response.ok) throw new Error(await responseMessage(response));
      const result = await response.json() as DemoRequest;
      delete decisionKeys.current[actionKey];
      setMessage(`Request ${request.case_id.slice(0, 8).toUpperCase()}: ${result.status.replace("_", " ")}.`);
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not decide request."); }
    finally { setBusy(null); }
  };
  const runTask = async (request: DemoRequest, kind: typeof tasks[number]["kind"]) => {
    setBusy(request.id); setError(""); setMessage("");
    try {
      const response = await authenticatedFetch(`${apiBase}/v1/hospitalos/requests/${request.id}/tasks`, session, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, kind }),
      });
      if (!response.ok) throw new Error(await responseMessage(response));
      setMessage("Operational check saved to the case activity.");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not run the check."); }
    finally { setBusy(null); }
  };
  const askSupervisor = async (request: DemoRequest) => {
    setBusy(request.id); setError(""); setMessage("");
    try {
      const response = await authenticatedFetch(`${apiBase}/v1/hospitalos/requests/${request.id}/supervisor`, session, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId }),
      });
      if (!response.ok) throw new Error(await responseMessage(response));
      setMessage("Supervisor suggestion saved. Review it before running a check.");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Supervisor is unavailable."); }
    finally { setBusy(null); }
  };

  return <div className="hos-inbox page-stack"><section className="surface hos-resource-intro"><div><span className="section-kicker">HOSPITALOS · SYNTHETIC DEMO</span><h2>Receiving requests</h2><p>Geeta Medicine's connected desk. A pre-arrival app response is separate from clinical assessment, transport and admission.</p></div><button type="button" onClick={() => void load()}>Refresh inbox</button></section>
    {error && <div className="hos-error" role="alert">{error}</div>}{message && <div className="alert-banner success" role="status">{message}</div>}
    {loading && <div className="surface">Loading requests…</div>}
    {!loading && !requests.length && <section className="surface hos-inbox-empty"><span className="hos-eyebrow">READY FOR A DEMO REQUEST</span><h2>The receiving desk is clear</h2><p>No synthetic request is waiting for Geeta Medicine. Open the locator in another window and send a demo confirmation request to see the handoff here.</p><div className="hos-inbox-steps"><div><strong>01</strong><span>Choose patient/family or ambulance in the public locator.</span></div><div><strong>02</strong><span>Compare the three invented facility snapshots and request Geeta.</span></div><div><strong>03</strong><span>Review and accept or decline here. Acceptance places a temporary resource hold.</span></div></div><a href="/demo/hospitalos" target="_blank" rel="noreferrer">Open public locator ↗</a></section>}
    {requests.map(request => <article className="surface hos-inbox-card" key={request.id}><div className="hos-inbox-heading"><div><span className="hos-eyebrow">CASE {request.case_id.slice(0, 8).toUpperCase()}</span><h2>{request.facility_name}</h2><p>{request.audience === "AMBULANCE" ? "Ambulance demo" : "Patient/family demo"} · {request.origin.replace("_", " ")} · {request.requirement === "GENERAL" ? "Requirement unknown/general" : request.requirement}</p></div><span className={`hos-status ${request.status === "ACCEPTED" ? "match" : ""}`}>{request.status.replace("_", " ")}</span></div><div className="hos-inbox-meta"><span>Requested {formatVerified(request.created_at)}</span><span>Response deadline {formatVerified(request.deadline_at)}</span><span>ETA {request.eta_minutes ? `${request.eta_minutes} min` : "not supplied"}</span><span>Hold {request.hold_state ?? "none"}</span></div>
      {request.status === "PENDING" && canDecide && <div className="hos-inbox-actions"><label className="hos-arrival-label">Optional demo arrival note (no patient data)<input maxLength={240} value={arrivalNotes[request.id] ?? ""} onChange={event => setArrivalNotes(previous => ({ ...previous, [request.id]: event.target.value }))} placeholder="Meet the receiving desk" /></label><button type="button" disabled={busy === request.id} onClick={() => void decide(request, "ACCEPT")}>Accept demo request</button><button type="button" disabled={busy === request.id} onClick={() => void decide(request, "DECLINE")}>Decline</button></div>}
      <div className="hos-task-actions"><strong>Operational checks</strong>{canDecide && <button type="button" disabled={busy === request.id} onClick={() => void askSupervisor(request)}>Ask AI supervisor</button>}{canDecide && tasks.map(task => <button key={task.kind} type="button" disabled={busy === request.id} onClick={() => void runTask(request, task.kind)}>{task.label}</button>)}</div>
      {request.events.filter(event => event.event_type === "AGENT_TASK_CREATED").slice(-1).map(event => { const kind = String(event.detail.kind); const suggested = tasks.find(task => task.kind === kind); return <div className="hos-agent-suggestion" key={event.id}><strong>Supervisor suggested: {suggested?.label ?? "Human review"}</strong><span>Suggestion only. An administrator chooses whether to run the check.</span>{suggested && canDecide && <button type="button" disabled={busy === request.id} onClick={() => void runTask(request, suggested.kind)}>Run suggested check</button>}</div>; })}
      <details className="hos-inbox-events"><summary>Activity · {request.events.length} events</summary>{request.events.map(event => <div key={event.id}><span>{event.event_type.replaceAll("_", " ")}</span><time>{formatVerified(event.occurred_at)}</time>{event.event_type === "TASK_COMPLETED" && <small>{JSON.stringify(event.detail)}</small>}</div>)}</details>
    </article>)}
  </div>;
}
