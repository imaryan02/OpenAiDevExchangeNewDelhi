import { useEffect, useState, type FormEvent } from "react";
import { apiBase, formatVerified, responseMessage, type DemoRequest, type TrackingCredentials } from "./types";

const labels: Record<DemoRequest["status"], string> = {
  PENDING: "Waiting for Geeta's demo receiving desk",
  ACCEPTED: "Geeta accepted the pre-arrival demo request",
  DECLINED: "Geeta declined this app request",
  EXPIRED: "No response before the demo deadline",
  WITHDRAWN: "Request withdrawn",
  HOLD_CONFLICT: "Demo resource hold could not be made",
};
const eventLabels: Record<string, string> = {
  CASE_CREATED: "Demo case created", ACCEPTANCE_REQUESTED: "Request sent to Geeta",
  REQUEST_EXPIRED: "Response window expired", REQUEST_DECLINED: "Geeta declined",
  HOSPITAL_ACCEPTED: "Geeta admin accepted", RESOURCE_REVALIDATED: "Resources rechecked",
  HOLD_CREATED: "Provisional resource hold created", HOLD_CONFLICT: "Resource hold conflict",
  REQUEST_WITHDRAWN: "Request withdrawn", ETA_UPDATED: "Demo ETA updated",
  TASK_COMPLETED: "Operational task checked", HUMAN_REVIEW_REQUESTED: "Human review flagged",
};

export function RequestTracker({ credentials, initial, onClear }: { credentials: TrackingCredentials; initial: DemoRequest; onClear: () => void }) {
  const [request, setRequest] = useState(initial);
  const [now, setNow] = useState(Date.now());
  const [eta, setEta] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch(`${apiBase}/v1/hospitalos/tracking`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(credentials),
        });
        if (!response.ok) throw new Error(await responseMessage(response));
        const body = await response.json() as DemoRequest;
        if (active) { setRequest(body); setError(""); }
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : "Tracking is unavailable."); }
    };
    void refresh();
    const poll = window.setInterval(() => { void refresh(); }, 2500);
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { active = false; window.clearInterval(poll); window.clearInterval(clock); };
  }, [credentials]);

  const mutate = async (path: "withdraw" | "eta", extra?: object) => {
    setBusy(true); setError("");
    try {
      const response = await fetch(`${apiBase}/v1/hospitalos/tracking/${path}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...credentials, ...extra }),
      });
      if (!response.ok) throw new Error(await responseMessage(response));
      setRequest(await response.json() as DemoRequest);
      setEta("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not update the demo request."); }
    finally { setBusy(false); }
  };
  const updateEta = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); void mutate("eta", { eta_minutes: Number(eta) }); };
  const seconds = Math.max(0, Math.ceil((new Date(request.deadline_at).getTime() - now) / 1000));
  const active = request.status === "PENDING" || request.status === "ACCEPTED";
  return <section className="hos-tracker" aria-live="polite"><div className="hos-tracker-top"><div><span className="hos-eyebrow">PRIVATE DEMO TRACKING</span><h2>{labels[request.status]}</h2><p>Case reference: <strong>{request.case_id.slice(0, 8).toUpperCase()}</strong> · {request.facility_name}</p></div><span className={`hos-status ${request.status === "ACCEPTED" ? "match" : ""}`}>{request.status.replace("_", " ")}</span></div>
    <p className="hos-tracker-warning">This is a synthetic pre-arrival coordination request. It does not guarantee treatment, admission, transport, or a real bed. Do not wait for this timer during a real emergency; call <a href="tel:112">112</a>.</p>
    {request.status === "PENDING" && <p className="hos-countdown">Demo response window: <strong>{seconds}s</strong> remaining</p>}
    {request.status === "ACCEPTED" && <p className="hos-accept-note">An authorized Geeta admin accepted this demo request. {request.hold_state === "ACTIVE" ? "A provisional demo resource hold is active." : "No active demo resource hold remains."} {request.arrival_note && <span>Receiving note: {request.arrival_note}.</span>} Coordinate directly with the facility using established channels.</p>}
    {(["DECLINED", "EXPIRED", "HOLD_CONFLICT"] as string[]).includes(request.status) && <p className="hos-fallback">No receiving confirmation is active. The other synthetic listings are for comparison and cannot receive app requests. For a real emergency, call 112 or use your established emergency-care channels.</p>}
    {error && <p className="hos-error" role="alert">{error}</p>}
    {active && <div className="hos-tracker-actions"><form onSubmit={updateEta}><label>Updated demo ETA (minutes)<input type="number" min="1" max="240" required value={eta} onChange={event => setEta(event.target.value)} /></label><button type="submit" disabled={busy}>Update ETA</button></form><button type="button" onClick={() => void mutate("withdraw")} disabled={busy}>Withdraw request</button></div>}
    <div className="hos-event-list"><h3>Activity</h3>{request.events.map(event => <div key={event.id}><span>{eventLabels[event.event_type] ?? event.event_type}</span><time>{formatVerified(event.occurred_at)}</time></div>)}</div>
    <button type="button" className="hos-clear" onClick={onClear}>Clear this browser's demo tracking</button>
  </section>;
}
