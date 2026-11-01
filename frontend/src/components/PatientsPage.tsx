import { FormEvent, useEffect, useMemo, useState } from "react";
import { Badge, Button, Input, Select } from "@fluentui/react-components";
import { DeleteRegular, SearchRegular } from "@fluentui/react-icons";

import { restoreSession } from "../lib/supabaseAuth";

type PatientContact = { contact_id: string; contact_name: string; phone_e164: string | null; relationship: string };
type Patient = {
  id: string;
  display_name: string;
  disambiguation: string;
  status: "ACTIVE" | "ARCHIVED";
  appointment_count: number;
  last_appointment_at: string | null;
  next_appointment_at: string | null;
  contacts: PatientContact[];
};

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const formatDate = (value: string | null) => value ? new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(value)) : "—";

export function PatientsPage({ organizationId }: { organizationId: string }) {
  const [records, setRecords] = useState<Patient[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [editing, setEditing] = useState<{ patient: Patient; contact: PatientContact | null } | null>(null);
  const [patientName, setPatientName] = useState("");
  const [note, setNote] = useState("");
  const [contactName, setContactName] = useState("");
  const [phone, setPhone] = useState("");
  const [relationship, setRelationship] = useState("SELF");

  const callerGroups = useMemo(() => {
    const groups = new Map<string, {
      key: string;
      contact: PatientContact | null;
      patients: { patient: Patient; contact: PatientContact | null }[];
    }>();
    for (const patient of records) {
      if (!patient.contacts.length) {
        groups.set(`patient:${patient.id}`, {
          key: `patient:${patient.id}`,
          contact: null,
          patients: [{ patient, contact: null }],
        });
        continue;
      }
      for (const contact of patient.contacts) {
        const key = `contact:${contact.contact_id}`;
        const group = groups.get(key) ?? { key, contact, patients: [] };
        group.patients.push({ patient, contact });
        groups.set(key, group);
      }
    }
    return [...groups.values()].sort((a, b) =>
      (a.contact?.contact_name ?? a.patients[0].patient.display_name).localeCompare(
        b.contact?.contact_name ?? b.patients[0].patient.display_name,
      ),
    );
  }, [records]);

  async function api(path: string, init?: RequestInit) {
    const session = await restoreSession();
    if (!session) throw new Error("Your session expired. Sign in again.");
    const response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json", ...init?.headers } });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.message ?? "The patient record could not be updated.");
    return payload;
  }

  async function load(search = query) {
    setLoading(true);
    try {
      const params = new URLSearchParams({ organization_id: organizationId, query: search.trim() });
      setRecords(await api(`/v1/patients?${params}`));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not load patients.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(""); }, [organizationId]);

  function openEditor(patient: Patient, contact: PatientContact | null) {
    setEditing({ patient, contact });
    setPatientName(patient.display_name);
    setNote(patient.disambiguation);
    setContactName(contact?.contact_name ?? "");
    setPhone(contact?.phone_e164 ?? "+91");
    setRelationship(contact?.relationship ?? "SELF");
    setMessage("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setLoading(true);
    setMessage("");
    try {
      const params = new URLSearchParams({ organization_id: organizationId });
      await api(`/v1/patients/${editing.patient.id}?${params}`, {
        method: "PATCH",
        body: JSON.stringify({ display_name: patientName, disambiguation: note, status: editing.patient.status }),
      });
      if (editing.contact) {
        await api(`/v1/patients/${editing.patient.id}/contacts/${editing.contact.contact_id}?${params}`, {
          method: "PATCH",
          body: JSON.stringify({ contact_name: contactName, phone_e164: phone.replace(/[\s()-]/g, ""), relationship }),
        });
      }
      setEditing(null);
      setMessage("Patient details updated.");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update the patient.");
      setLoading(false);
    }
  }

  async function deleteRecord(patient: Patient) {
    const confirmed = window.confirm(
      `Archive patient "${patient.display_name}"?\nThe record will be hidden from normal use while its appointment history remains available.`
    );
    if (!confirmed) return;
    setLoading(true);
    setMessage("");
    try {
      const params = new URLSearchParams({
        organization_id: organizationId,
      });
      const result = await api(`/v1/patients/${patient.id}?${params}`, {
        method: "DELETE",
      });
      if (editing?.patient.id === patient.id) {
        setEditing(null);
      }
      setMessage(`Patient "${patient.display_name}" archived.`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not delete patient.");
    } finally {
      setLoading(false);
    }
  }

  return <div className="page-stack patients-page">
    <section className="directory-toolbar">
      <div><h2>Patients and families</h2><p>{callerGroups.length} unique caller mobiles linked to {records.length} patient records.</p></div>
      <form onSubmit={(event) => { event.preventDefault(); void load(); }}><Input value={query} onChange={(_, data) => setQuery(data.value)} contentBefore={<SearchRegular />} placeholder="Patient, caller or mobile" /><Button appearance="primary" type="submit">Search</Button></form>
    </section>
    {message && <div className="settings-notice">{message}</div>}
    {editing && <section className="surface patient-editor">
      <div className="editor-heading"><div><h3>Edit patient record</h3><p>Patient and caller stay as separate identities linked by their relationship.</p></div><Button appearance="subtle" onClick={() => setEditing(null)}>Close</Button></div>
      <form className="patient-edit-form" onSubmit={save}>
        <label>Patient name<Input value={patientName} onChange={(_, data) => setPatientName(data.value)} required /></label>
        <label>Identification note<Input value={note} onChange={(_, data) => setNote(data.value)} placeholder="Optional, e.g. mother of Aryan" /></label>
        {editing.contact && <>
          <label>Caller name<Input value={contactName} onChange={(_, data) => setContactName(data.value)} required /></label>
          <label>Mobile number<Input value={phone} onChange={(_, data) => setPhone(data.value)} required /></label>
          <label>Relationship<Select value={relationship} onChange={(_, data) => setRelationship(data.value)}><option value="SELF">Self</option><option value="MOTHER">Mother</option><option value="FATHER">Father</option><option value="SPOUSE">Spouse</option><option value="CHILD">Child</option><option value="OTHER">Other</option></Select></label>
        </>}
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <Button appearance="primary" type="submit" disabled={loading}>{loading ? "Saving…" : "Save changes"}</Button>
          <Button appearance="subtle" icon={<DeleteRegular />} disabled={loading} onClick={() => deleteRecord(editing.patient)} style={{ color: "#c4314b" }}>Archive</Button>
        </div>
      </form>
    </section>}
    <section className="caller-directory">
      {callerGroups.map((group) => {
        const callerName = group.contact?.contact_name ?? "Unlinked patient";
        const totalAppointments = group.patients.reduce((sum, item) => sum + Number(item.patient.appointment_count), 0);
        return <article className="caller-family-card" key={group.key}>
          <header className="caller-family-header">
            <div className="caller-identity">
              <span className="patient-avatar">{callerName.charAt(0).toUpperCase()}</span>
              <div><strong>{callerName}</strong><span>{group.contact?.phone_e164 ?? "No mobile number"}</span></div>
            </div>
            <div className="caller-summary"><span><strong>{group.patients.length}</strong> linked patient{group.patients.length === 1 ? "" : "s"}</span><span><strong>{totalAppointments}</strong> appointment{totalAppointments === 1 ? "" : "s"}</span>{group.contact?.phone_e164 && <Badge size="small" appearance="tint" color="success">Unique mobile</Badge>}</div>
          </header>
          <div className="family-member-list">
            {group.patients.map(({ patient, contact }) => <div className="family-member-row" key={`${group.key}:${patient.id}`}>
              <div className="family-member-name"><strong>{patient.display_name}</strong><span>{patient.disambiguation || "No identification note"}</span></div>
              <Badge size="small" appearance="tint" color={contact?.relationship === "SELF" ? "success" : "informative"}>{contact?.relationship.replaceAll("_", " ") ?? "UNLINKED"}</Badge>
              <div className="family-visit"><strong>{patient.appointment_count}</strong><span>Total bookings</span></div>
              <div className="family-visit"><strong>{formatDate(patient.next_appointment_at)}</strong><span>{patient.next_appointment_at ? "Next visit" : `Last: ${formatDate(patient.last_appointment_at)}`}</span></div>
              <div style={{ display: "flex", gap: "0.4rem", alignItems: "center", justifyContent: "flex-end" }}>
                <Button size="small" onClick={() => openEditor(patient, contact)}>Edit patient</Button>
                <Button size="small" appearance="subtle" icon={<DeleteRegular />} onClick={() => deleteRecord(patient)} style={{ color: "#c4314b" }} title={`Archive ${patient.display_name}`}>Archive</Button>
              </div>
            </div>)}
          </div>
        </article>;
      })}
      {!loading && !records.length && <div className="empty-panel">No patient records match this search.</div>}
      {loading && !records.length && <div className="empty-panel">Loading patient records…</div>}
    </section>
  </div>;
}
