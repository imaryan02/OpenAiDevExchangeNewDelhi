import { useCallback, useEffect, useState, type FormEvent } from "react";
import { authenticatedFetch, type AuthSession } from "../lib/supabaseAuth";
import { apiBase, formatVerified, responseMessage, type Resource } from "./types";
import "./styles.css";

type Editable = Pick<Resource, "emergency_open" | "ed_bays_ready" | "icu_beds_ready" | "ventilators_ready" | "ct_available" | "trauma_available" | "pediatric_available" | "obstetric_available">;
const fields: { key: keyof Pick<Editable, "ed_bays_ready" | "icu_beds_ready" | "ventilators_ready">; label: string }[] = [
  { key: "ed_bays_ready", label: "Ready receiving spaces" },
  { key: "icu_beds_ready", label: "Ready ICU beds" },
  { key: "ventilators_ready", label: "Ready ventilators" },
];
const capabilities: { key: keyof Pick<Editable, "ct_available" | "trauma_available" | "pediatric_available" | "obstetric_available">; label: string }[] = [
  { key: "ct_available", label: "CT available" },
  { key: "trauma_available", label: "Trauma capability" },
  { key: "pediatric_available", label: "Pediatric capability" },
  { key: "obstetric_available", label: "Obstetric capability" },
];

export function ResourcesPage({ session, organizationId, canEdit }: { session: AuthSession; organizationId: string; canEdit: boolean }) {
  const [resources, setResources] = useState<Resource[]>([]);
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

  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);

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
      setMessage("Demo resources saved. The public locator will use this update on refresh.");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save resources."); }
    finally { setSaving(null); }
  };

  return <div className="hos-resources page-stack"><section className="hos-resource-intro surface"><div><span className="section-kicker">HOSPITALOS · SYNTHETIC DEMO</span><h2>Receiving resources</h2><p>Manage the invented resource snapshot for Geeta Medicine. Changes update the public demo locator; they do not change appointment capacity or any real emergency service.</p></div><a href="/demo/hospitalos" target="_blank" rel="noreferrer">Open public locator ↗</a></section>
    {error && <div className="hos-error" role="alert">{error}</div>}{message && <div className="alert-banner success" role="status">{message}</div>}
    {loading && <div className="surface">Loading demo resources…</div>}
    {!loading && !resources.length && !error && <div className="surface">No connected demo facility is linked to this organization.</div>}
    {resources.map(resource => { const state = draft[resource.id]; if (!state) return null; return <form className="surface hos-resource-form" key={resource.id} onSubmit={event => void save(event, resource)}><div className="hos-resource-heading"><div><span className="hos-eyebrow">CONNECTED FACILITY · SYNTHETIC DATA</span><h2>{resource.name}</h2><p>{resource.area} · Last updated {formatVerified(resource.verified_at)}</p></div><span className="hos-version">Snapshot v{resource.version}</span></div><label className="hos-open-toggle"><input type="checkbox" checked={state.emergency_open} disabled={!canEdit} onChange={event => update(resource.id, { emergency_open: event.target.checked })} /><span>Emergency receiving marked open</span></label><div className="hos-resource-grid">{fields.map(field => <label key={field.key}>{field.label}<input type="number" min="0" max="1000" step="1" required disabled={!canEdit} value={state[field.key]} onChange={event => update(resource.id, { [field.key]: event.target.value === "" ? 0 : Number(event.target.value) })} /></label>)}</div><fieldset><legend>Listed capabilities</legend><div className="hos-capability-grid">{capabilities.map(field => <label key={field.key}><input type="checkbox" checked={state[field.key]} disabled={!canEdit} onChange={event => update(resource.id, { [field.key]: event.target.checked })} />{field.label}</label>)}</div></fieldset><div className="hos-resource-actions"><p>{canEdit ? "Saving records a new demo verification time." : "Organization administrators can edit this snapshot."}</p>{canEdit && <button type="submit" disabled={saving === resource.id}>{saving === resource.id ? "Saving…" : "Save demo resources"}</button>}</div></form>; })}
  </div>;
}
