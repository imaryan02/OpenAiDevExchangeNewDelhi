import { useCallback, useEffect, useState, type FormEvent } from "react";
import { authenticatedFetch, type AuthSession } from "../lib/supabaseAuth";
import { apiBase, formatVerified, responseMessage, type Facility, type Resource } from "./types";
import "./styles.css";

type Editable = Pick<Resource, "emergency_open" | "ed_bays_ready" | "icu_beds_ready" | "ventilators_ready" | "ct_available" | "trauma_available" | "pediatric_available" | "obstetric_available">;
const counts: { key: keyof Pick<Editable, "ed_bays_ready" | "icu_beds_ready" | "ventilators_ready">; label: string; hint: string }[] = [
  { key: "ed_bays_ready", label: "Receiving spaces ready", hint: "Spaces available for an initial handoff" },
  { key: "icu_beds_ready", label: "ICU beds ready", hint: "Beds marked ready in this demo snapshot" },
  { key: "ventilators_ready", label: "Ventilators ready", hint: "Equipment listed as ready" },
];
const capabilities: { key: keyof Pick<Editable, "ct_available" | "trauma_available" | "pediatric_available" | "obstetric_available">; label: string }[] = [
  { key: "ct_available", label: "CT imaging" }, { key: "trauma_available", label: "Trauma" },
  { key: "pediatric_available", label: "Pediatric" }, { key: "obstetric_available", label: "Obstetric" },
];
const isCurrent = (value: string) => { const age = Date.now() - new Date(value).getTime(); return age >= 0 && age <= 24 * 60 * 60 * 1000; };
const available = (ready: number, held: number) => Math.max(0, ready - held);

export function ResourcesPage({ session, organizationId, canEdit, onReceiving }: { session: AuthSession; organizationId: string; canEdit: boolean; onReceiving: () => void }) {
  const [resources, setResources] = useState<Resource[]>([]);
  const [network, setNetwork] = useState<Facility[]>([]);
  const [draft, setDraft] = useState<Record<string, Editable>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError("");
    try {
      const response = await authenticatedFetch(`${apiBase}/v1/hospitalos/resources?organization_id=${encodeURIComponent(organizationId)}`, session, { signal });
      if (!response.ok) throw new Error(await responseMessage(response));
      const body = await response.json() as Resource[];
      if (signal?.aborted) return;
      setResources(body);
      setDraft(Object.fromEntries(body.map(item => [item.id, {
        emergency_open: item.emergency_open, ed_bays_ready: item.ed_bays_ready,
        icu_beds_ready: item.icu_beds_ready, ventilators_ready: item.ventilators_ready,
        ct_available: item.ct_available, trauma_available: item.trauma_available,
        pediatric_available: item.pediatric_available, obstetric_available: item.obstetric_available,
      }])));
    } catch (cause) { if (!signal?.aborted) setError(cause instanceof Error ? cause.message : "Could not load resources."); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [organizationId, session]);

  const loadNetwork = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await fetch(`${apiBase}/v1/hospitalos/facilities?origin=CENTRAL_DELHI`, { signal });
      if (!response.ok) return;
      const body = await response.json() as { facilities: Facility[] };
      if (!signal?.aborted) setNetwork(body.facilities);
    } catch { /* The connected snapshot remains usable if comparison data is unavailable. */ }
  }, []);

  useEffect(() => { const controller = new AbortController(); void load(controller.signal); void loadNetwork(controller.signal); return () => controller.abort(); }, [load, loadNetwork]);

  const update = (id: string, change: Partial<Editable>) => setDraft(previous => ({ ...previous, [id]: { ...previous[id], ...change } }));
  const save = async (event: FormEvent<HTMLFormElement>, resource: Resource) => {
    event.preventDefault();
    if (!canEdit || !draft[resource.id]) return;
    setSaving(resource.id); setError(""); setMessage("");
    try {
      const response = await authenticatedFetch(`${apiBase}/v1/hospitalos/resources/${resource.id}`, session, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...draft[resource.id], organization_id: organizationId, expected_version: resource.version }),
      });
      if (!response.ok) throw new Error(await responseMessage(response));
      await load(); await loadNetwork();
      setMessage("Demo snapshot saved. The locator now uses these values.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save resources."); }
    finally { setSaving(null); }
  };

  return <div className="hos-resources page-stack">
    <section className="hos-resource-intro surface"><div><span className="section-kicker">HOSPITALOS · SYNTHETIC DEMO</span><h2>Receiving resources</h2><p>One connected desk, three invented facilities. This board shows the resource values used by the public locator. It does not describe real emergency availability.</p></div><a href="/demo/hospitalos" target="_blank" rel="noreferrer">Open public locator ↗</a></section>
    {error && <div className="hos-error" role="alert">{error}</div>}{message && <div className="alert-banner success" role="status">{message}</div>}
    {loading && <div className="surface">Loading demo resources…</div>}
    {!loading && !resources.length && !error && <div className="surface">No connected demo facility is linked to this organization.</div>}
    {resources.map(resource => { const state = draft[resource.id]; if (!state) return null;
      const current = isCurrent(resource.verified_at);
      return <div className="hos-resource-board" key={resource.id}>
        <section className="surface hos-resource-overview" aria-label={`${resource.name} resource snapshot`}>
          <div className="hos-resource-heading"><div><span className="hos-eyebrow">CONNECTED FACILITY · SYNTHETIC DATA</span><h2>{resource.name}</h2><p>{resource.area} · {resource.updated_by ? "Staff-updated" : "Seeded"} demo snapshot · {formatVerified(resource.verified_at)}</p></div><span className={`hos-status ${current && resource.emergency_open ? "match" : ""}`}>{!current ? "Reconfirmation needed" : resource.emergency_open ? "Receiving marked open" : "Receiving marked closed"}</span></div>
          <div className="hos-resource-metrics">
            <div><span>Receiving spaces</span><strong>{available(resource.ed_bays_ready, resource.ed_holds_active)}<small> available</small></strong><p>{resource.ed_bays_ready} ready · {resource.ed_holds_active} on active holds</p></div>
            <div><span>ICU beds</span><strong>{available(resource.icu_beds_ready, resource.icu_holds_active)}<small> available</small></strong><p>{resource.icu_beds_ready} ready · {resource.icu_holds_active} on active holds</p></div>
            <div><span>Ventilators</span><strong>{resource.ventilators_ready}<small> ready</small></strong><p>Readiness count; no hold tracking</p></div>
            <div><span>Awaiting response</span><strong>{resource.pending_requests}<small> requests</small></strong><p>Pending Geeta demo requests</p></div>
          </div>
          <div className="hos-resource-capabilities"><div><strong>Listed capabilities</strong><span>Availability flags, not a clinical assessment.</span></div><div>{capabilities.map(item => <span className={resource[item.key] ? "is-listed" : ""} key={item.key}>{resource[item.key] ? "✓" : "—"} {item.label}</span>)}</div></div>
          <div className="hos-resource-overview-foot"><span>Snapshot v{resource.version} · {current ? "Updated within 24 hours" : "Older than 24 hours"}</span><button type="button" onClick={onReceiving}>View receiving requests →</button></div>
        </section>
        <form className="surface hos-resource-form" onSubmit={event => void save(event, resource)}><div className="hos-resource-heading"><div><span className="hos-eyebrow">UPDATE CONNECTED SNAPSHOT</span><h2>Set today’s demo readiness</h2><p>Edits change the invented values used for matching. Active holds come from accepted demo requests.</p></div></div>
          <label className="hos-open-toggle"><input type="checkbox" checked={state.emergency_open} disabled={!canEdit} onChange={event => update(resource.id, { emergency_open: event.target.checked })} /><span>Emergency receiving marked open</span></label>
          <div className="hos-resource-grid">{counts.map(field => <label key={field.key}>{field.label}<input type="number" min="0" max="1000" step="1" required disabled={!canEdit} value={state[field.key]} onChange={event => update(resource.id, { [field.key]: event.target.value === "" ? 0 : Number(event.target.value) })} /><small>{field.hint}</small></label>)}</div>
          <fieldset><legend>Listed capabilities</legend><div className="hos-capability-grid">{capabilities.map(field => <label key={field.key}><input type="checkbox" checked={state[field.key]} disabled={!canEdit} onChange={event => update(resource.id, { [field.key]: event.target.checked })} />{field.label}</label>)}</div></fieldset>
          <div className="hos-resource-actions"><p>{canEdit ? "Saving records a new demo update time. It does not alter appointment capacity." : "Organization administrators can edit this snapshot."}</p>{canEdit && <button type="submit" disabled={saving === resource.id}>{saving === resource.id ? "Saving…" : "Save demo resources"}</button>}</div>
        </form>
      </div>;
    })}
    {network.length > 0 && <section className="surface hos-network"><div className="hos-resource-heading"><div><span className="hos-eyebrow">PUBLIC DEMO NETWORK</span><h2>How the three listings compare</h2><p>Comparison facilities are read-only. Only Geeta Medicine can receive an app request in this demo.</p></div></div><div className="hos-network-list">{network.map(facility => <div className="hos-network-row" key={facility.slug}><div><strong>{facility.name}</strong><span>{facility.area} · {facility.connected_receiving_desk ? "Connected desk" : "Comparison only"}</span></div><div><strong>{facility.ed_bays_available}</strong><span>receiving available</span></div><div><strong>{facility.icu_beds_available}</strong><span>ICU available</span></div><div><strong>{facility.ventilators_ready}</strong><span>ventilators ready</span></div><span className={`hos-status ${facility.recommended ? "match" : ""}`}>{facility.recommended ? "General match" : "Check needed"}</span></div>)}</div><p className="hos-network-note">General receiving check from Central Delhi. Availability subtracts active demo holds; refresh the public locator for other filters.</p></section>}
  </div>;
}
