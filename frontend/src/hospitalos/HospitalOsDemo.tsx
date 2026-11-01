import { useEffect, useState } from "react";
import { apiBase, formatVerified, responseMessage, type Facility, type Origin, type Preference, type Requirement } from "./types";
import "./styles.css";

const reasons: Record<string, string> = {
  CURRENT_DEMO_RESOURCES_MATCH: "Matches the selected demo resource checks",
  STATUS_NEEDS_RECONFIRMATION: "Resource update is over 24 hours old",
  EMERGENCY_SERVICE_NOT_OPEN: "Emergency service marked closed",
  NO_READY_RECEIVING_SPACE: "No ready receiving space listed",
  ICU_RESOURCE_NOT_READY: "No ICU bed marked ready",
  TRAUMA_CAPABILITY_NOT_LISTED: "Trauma capability is not listed",
  PEDIATRIC_CAPABILITY_NOT_LISTED: "Pediatric capability is not listed",
  OBSTETRIC_CAPABILITY_NOT_LISTED: "Obstetric capability is not listed",
};

export default function HospitalOsDemo() {
  const [audience, setAudience] = useState<"PATIENT" | "AMBULANCE">("PATIENT");
  const [origin, setOrigin] = useState<Origin>("CENTRAL_DELHI");
  const [preference, setPreference] = useState<Preference>("ANY");
  const [requirement, setRequirement] = useState<Requirement>("GENERAL");
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ origin, preference, requirement });
        const response = await fetch(`${apiBase}/v1/hospitalos/facilities?${params}`, { signal: controller.signal });
        if (!response.ok) throw new Error(await responseMessage(response));
        const body = await response.json() as { facilities: Facility[] };
        setFacilities(body.facilities);
      } catch (cause) {
        if (!controller.signal.aborted) { setFacilities([]); setError(cause instanceof Error ? cause.message : "Could not load demo facilities."); }
      } finally { if (!controller.signal.aborted) setLoading(false); }
    };
    void load();
    return () => controller.abort();
  }, [origin, preference, requirement, refresh]);

  const matching = facilities.filter(facility => facility.recommended).length;
  return <main className="hos-public">
    <header className="hos-header"><div className="hos-brand"><span className="hos-brand-mark">H</span><div><strong>HospitalOS</strong><span>Resource locator demo</span></div></div><a href="/" className="hos-header-link">Clinic workspace</a></header>
    <div className="hos-notice" role="note"><strong>Synthetic demonstration.</strong> Names, locations, resource counts and distances here are invented. This is not a live hospital directory or emergency dispatch service. For a real emergency in India, call <a href="tel:112">112</a>.</div>
    <section className="hos-hero"><div><span className="hos-eyebrow">DELHI · DEMO NETWORK</span><h1>Find a facility for the next step.</h1><p>Compare example receiving resources and see why a facility appears in the recommendation. Confirm real availability directly with a hospital before travel.</p></div><a className="hos-emergency" href="tel:112"><span>Emergency help in India</span><strong>Call 112 ↗</strong></a></section>
    <section className="hos-filter-panel" aria-label="Facility search">
      <div className="hos-audience" role="group" aria-label="I am searching as"><button type="button" aria-pressed={audience === "PATIENT"} onClick={() => { setAudience("PATIENT"); setRequirement("GENERAL"); }}>Patient or family</button><button type="button" aria-pressed={audience === "AMBULANCE"} onClick={() => setAudience("AMBULANCE")}>Ambulance crew</button></div>
      <div className="hos-filter-grid"><label>Starting area<select value={origin} onChange={event => setOrigin(event.target.value as Origin)}><option value="CENTRAL_DELHI">Central Delhi</option><option value="NORTH_DELHI">North Delhi</option><option value="EAST_DELHI">East Delhi</option></select></label>{audience === "AMBULANCE" && <label>Requirement supplied by clinical team<select value={requirement} onChange={event => setRequirement(event.target.value as Requirement)}><option value="GENERAL">Unknown / general receiving space</option><option value="ICU">ICU bed</option><option value="TRAUMA">Trauma capability</option><option value="PEDIATRIC">Pediatric capability</option><option value="OBSTETRIC">Obstetric capability</option></select></label>}<label>Cost preference<select value={preference} onChange={event => setPreference(event.target.value as Preference)}><option value="ANY">Any</option><option value="AFFORDABLE">Government or charitable first</option><option value="PRIVATE">Private first</option></select></label></div>
      <p className="hos-filter-help">{audience === "AMBULANCE" ? "Enter a resource requirement only if supplied by a qualified clinical team. Verify destination through your operational protocol." : "No medical requirement is inferred from symptoms. These filters compare invented facility data and do not assess clinical suitability."}</p>
    </section>
    <section className="hos-results" aria-live="polite"><div className="hos-results-heading"><div><span className="hos-eyebrow">FACILITY COMPARISON</span><h2>{loading ? "Checking demo resources…" : `${matching} of ${facilities.length} match the selected checks`}</h2></div><button type="button" onClick={() => setRefresh(value => value + 1)} disabled={loading}>Refresh resources</button></div>
      {error && <div className="hos-error" role="alert">{error} <span>The demo API may not be enabled yet.</span></div>}
      {!loading && !error && facilities.length === 0 && <div className="hos-empty">No demo facilities are configured.</div>}
      <div className="hos-card-grid">{facilities.map((facility, index) => <article className={`hos-facility ${facility.recommended ? "hos-is-match" : ""}`} key={facility.slug}><div className="hos-card-top"><span className="hos-card-index">0{index + 1}</span><span className={facility.recommended ? "hos-status match" : "hos-status"}>{facility.recommended ? "Demo match" : "Check needed"}</span></div><h3>{facility.name}</h3><p className="hos-area">{facility.area} · ~{facility.distance_km} km demo distance</p><div className="hos-chips"><span>{facility.cost_category.toLowerCase()}</span><span>{facility.connected_receiving_desk ? "Connected Geeta desk" : "Comparison listing"}</span></div><div className="hos-counts"><div><strong>{facility.ed_bays_ready}</strong><span>Receiving spaces</span></div><div><strong>{facility.icu_beds_ready}</strong><span>ICU beds</span></div><div><strong>{facility.ventilators_ready}</strong><span>Ventilators</span></div></div><div className="hos-reasons">{facility.reason_codes.map(code => <p key={code}>{reasons[code] ?? code}</p>)}</div><div className="hos-card-foot"><span>Demo update: {formatVerified(facility.verified_at)}</span><span>{facility.connected_receiving_desk ? "Receiving requests open in Phase 2" : "No connected receiving desk"}</span></div></article>)}</div>
    </section>
  </main>;
}
