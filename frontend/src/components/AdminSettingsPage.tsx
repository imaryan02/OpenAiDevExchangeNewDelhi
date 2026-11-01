import { FormEvent, useEffect, useMemo, useState } from "react";
import { Badge, Button, Input, Select, Switch } from "@fluentui/react-components";

import { restoreSession } from "../lib/supabaseAuth";

type Item = { id: string; name: string; active: boolean };
type Location = Item & { address: string; timezone: string };
type Assignment = {
  id: string;
  display_name: string;
  doctor_name: string;
  location_id: string;
  department_id: string;
  location_name: string;
  department_name: string;
  fee_minor: number;
  currency: string;
  active: boolean;
};
type Rule = {
  id: string;
  assignment_id: string;
  weekday: number;
  local_starts_at: string;
  local_ends_at: string;
  booking_mode: "EXACT_TIME" | "SESSION_TOKEN";
  slot_minutes: number | null;
  max_patients: number | null;
  active: boolean;
};

const rupeesToMinor = (value: string) => {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) throw new Error("Enter the fee in rupees with at most two decimal places.");
  return Math.round(Number(normalized) * 100);
};
const minorToRupees = (value: number) => (value / 100).toFixed(2);
const formatInrMinor = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(value / 100);
type Exception = { id: string; assignment_id: string; local_date: string; exception_type: string; reason: string };
export type Configuration = {
  organization: { id: string; name: string; organization_type: "CLINIC" | "HOSPITAL"; timezone: string; status: string };
  locations: Location[];
  departments: Item[];
  assignments: Assignment[];
  schedule_rules: Rule[];
  schedule_exceptions?: Exception[];
};

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

type DoctorDraft = { id?: string; name: string; departmentId: string; locationId: string; fee: string };
type ScheduleDraft = {
  id?: string;
  assignmentId: string;
  weekday: string;
  startsAt: string;
  endsAt: string;
  limit: string;
  active: boolean;
};

const blankDoctor: DoctorDraft = { name: "", departmentId: "", locationId: "", fee: "0" };
const blankSchedule: ScheduleDraft = {
  assignmentId: "",
  weekday: "1",
  startsAt: "10:00",
  endsAt: "12:00",
  limit: "30",
  active: true,
};

export function AdminSettingsPage({
  configuration,
  focus = "settings",
  onConfigurationChange,
}: {
  configuration: Configuration | null;
  focus?: "departments" | "doctors" | "settings";
  onConfigurationChange?: (configuration: Configuration) => void;
}) {
  const [data, setData] = useState(configuration);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [departmentEditor, setDepartmentEditor] = useState<{ id?: string; name: string; active: boolean } | null>(null);
  const [doctorEditor, setDoctorEditor] = useState<DoctorDraft | null>(null);
  const [scheduleEditor, setScheduleEditor] = useState<ScheduleDraft | null>(null);
  const [expandedDoctor, setExpandedDoctor] = useState<string | null>(null);
  const [editingClinic, setEditingClinic] = useState(false);
  const [clinicName, setClinicName] = useState("");
  const [clinicType, setClinicType] = useState<"CLINIC" | "HOSPITAL">("CLINIC");
  const [siteName, setSiteName] = useState("");
  const [siteAddress, setSiteAddress] = useState("");

  useEffect(() => {
    setData(configuration);
    if (configuration) {
      setClinicName(configuration.organization.name);
      setClinicType(configuration.organization.organization_type);
      setSiteName(configuration.locations[0]?.name ?? "");
      setSiteAddress(configuration.locations[0]?.address ?? "");
    }
  }, [configuration]);

  const activeDepartments = useMemo(() => data?.departments.filter((item) => item.active) ?? [], [data]);
  const activeLocations = useMemo(() => data?.locations.filter((item) => item.active) ?? [], [data]);

  async function request(path: string, method: "POST" | "PATCH" | "DELETE", body?: object) {
    if (!data) return;
    const session = await restoreSession();
    if (!session) throw new Error("Your session expired. Sign in again.");
    const query = new URLSearchParams({ organization_id: data.organization.id });
    const response = await fetch(`${apiBaseUrl}/v1/configuration/${path}?${query}`, {
      method,
      headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.message ?? payload?.detail?.[0]?.msg ?? "The change could not be saved.");
    const refreshed = await fetch(`${apiBaseUrl}/v1/configuration?${query}`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    if (!refreshed.ok) throw new Error("The change was saved, but the page could not refresh.");
    const next = await refreshed.json() as Configuration;
    setData(next);
    onConfigurationChange?.(next);
  }

  async function runChange(action: () => Promise<void>, success: string) {
    setSaving(true);
    setMessage("");
    try {
      await action();
      setMessage(success);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The change could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function saveDepartment(event: FormEvent) {
    event.preventDefault();
    if (!departmentEditor) return;
    await runChange(async () => {
      if (departmentEditor.id) {
        await request(`departments/${departmentEditor.id}`, "PATCH", {
          name: departmentEditor.name,
          active: departmentEditor.active,
        });
      } else {
        await request("departments", "POST", { name: departmentEditor.name });
      }
      setDepartmentEditor(null);
    }, departmentEditor.id ? "Department updated." : "Department added.");
  }

  async function saveDoctor(event: FormEvent) {
    event.preventDefault();
    if (!doctorEditor) return;
    await runChange(async () => {
      if (doctorEditor.id) {
        const current = data?.assignments.find((doctor) => doctor.id === doctorEditor.id);
        await request(`assignments/${doctorEditor.id}`, "PATCH", {
          active: current?.active ?? true,
          display_name: doctorEditor.name,
          department_id: doctorEditor.departmentId,
          location_id: doctorEditor.locationId,
          fee_minor: rupeesToMinor(doctorEditor.fee),
        });
      } else {
        await request("assignments", "POST", {
          doctor_name: doctorEditor.name,
          display_name: doctorEditor.name,
          qualifications: [],
          department_id: doctorEditor.departmentId,
          location_id: doctorEditor.locationId,
          fee_minor: rupeesToMinor(doctorEditor.fee),
          currency: "INR",
        });
      }
      setDoctorEditor(null);
    }, doctorEditor.id ? "Doctor updated." : "Doctor added.");
  }

  async function deleteDoctor(doctor: Assignment) {
    const confirmed = window.confirm(
      `Delete ${doctor.display_name}? This permanently removes their schedules and unbooked availability.`
    );
    if (!confirmed) return;
    await runChange(async () => {
      await request(`assignments/${doctor.id}`, "DELETE");
      if (expandedDoctor === doctor.id) setExpandedDoctor(null);
      if (doctorEditor?.id === doctor.id) setDoctorEditor(null);
    }, `${doctor.display_name} deleted.`);
  }

  async function saveSchedule(event: FormEvent) {
    event.preventDefault();
    if (!scheduleEditor) return;
    const body = {
      weekday: Number(scheduleEditor.weekday),
      local_starts_at: scheduleEditor.startsAt,
      local_ends_at: scheduleEditor.endsAt,
      booking_mode: "SESSION_TOKEN",
      slot_minutes: null,
      max_patients: Number(scheduleEditor.limit),
      active: scheduleEditor.active,
    };
    await runChange(async () => {
      if (scheduleEditor.id) {
        await request(`schedule-rules/${scheduleEditor.id}`, "PATCH", body);
      } else {
        await request("schedule-rules", "POST", {
          ...body,
          assignment_id: scheduleEditor.assignmentId,
          effective_from: new Date().toISOString().slice(0, 10),
          effective_until: null,
          booking_cutoff_minutes: 30,
        });
      }
      setScheduleEditor(null);
      setExpandedDoctor(scheduleEditor.assignmentId);
    }, scheduleEditor.id ? "Weekly hours updated." : "Weekly hours added.");
  }

  async function saveClinic(event: FormEvent) {
    event.preventDefault();
    if (!data) return;
    await runChange(async () => {
      await request("organization", "PATCH", { name: clinicName, organization_type: clinicType });
      const site = data.locations[0];
      if (site) await request(`locations/${site.id}`, "PATCH", { name: siteName, address: siteAddress });
      setEditingClinic(false);
    }, "Clinic details updated.");
  }

  if (!data) return <div className="empty-panel">Loading clinic configuration…</div>;

  const scheduleEditorView = scheduleEditor && (
    <div className="schedule-editor-inline">
      <div className="editor-heading">
        <div><h3>{scheduleEditor.id ? "Edit availability" : "Add availability"}</h3><p>Set the recurring hours and how patients are booked.</p></div>
        <Button appearance="subtle" onClick={() => setScheduleEditor(null)}>Cancel</Button>
      </div>
      <form className="schedule-form" onSubmit={saveSchedule}>
        <label>Day<Select value={scheduleEditor.weekday} onChange={(_, value) => setScheduleEditor({ ...scheduleEditor, weekday: value.value })}>{weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}</Select></label>
        <label>From<Input type="time" value={scheduleEditor.startsAt} onChange={(_, value) => setScheduleEditor({ ...scheduleEditor, startsAt: value.value })} required /></label>
        <label>Until<Input type="time" value={scheduleEditor.endsAt} onChange={(_, value) => setScheduleEditor({ ...scheduleEditor, endsAt: value.value })} required /></label>
        <label>Patient capacity<Input type="number" min={1} value={scheduleEditor.limit} onChange={(_, value) => setScheduleEditor({ ...scheduleEditor, limit: value.value })} required /></label>
        <div className="schedule-form-actions">
          <Button type="submit" appearance="primary" disabled={saving}>{saving ? "Saving…" : "Save availability"}</Button>
          {scheduleEditor.id && <Button type="button" appearance="subtle" disabled={saving} onClick={() => runChange(async () => { await request(`schedule-rules/${scheduleEditor.id}`, "PATCH", { weekday: Number(scheduleEditor.weekday), local_starts_at: scheduleEditor.startsAt, local_ends_at: scheduleEditor.endsAt, booking_mode: "SESSION_TOKEN", slot_minutes: null, max_patients: Number(scheduleEditor.limit), active: !scheduleEditor.active }); setScheduleEditor(null); }, scheduleEditor.active ? "Availability disabled." : "Availability enabled.")}>{scheduleEditor.active ? "Mark unavailable" : "Mark available"}</Button>}
        </div>
      </form>
    </div>
  );

  return (
    <div className="settings-page admin-settings">
      {message && <div className="settings-notice" role="status">{message}</div>}

      {focus === "departments" && (
        <>
          <div className="management-header">
            <div><h2>Departments</h2><p>Organize doctors and appointment routing.</p></div>
            <Button appearance="primary" onClick={() => setDepartmentEditor({ name: "", active: true })}>＋ Add department</Button>
          </div>
          {departmentEditor && (
            <section className="surface editor-panel">
              <div className="editor-heading"><div><h3>{departmentEditor.id ? "Edit department" : "Add department"}</h3><p>Department changes appear in booking filters immediately.</p></div><Button appearance="subtle" onClick={() => setDepartmentEditor(null)}>Close</Button></div>
              <form className="admin-form" onSubmit={saveDepartment}>
                <label>Department name<Input value={departmentEditor.name} onChange={(_, value) => setDepartmentEditor({ ...departmentEditor, name: value.value })} required /></label>
                <Button type="submit" appearance="primary" disabled={saving}>{saving ? "Saving…" : departmentEditor.id ? "Save changes" : "Add department"}</Button>
              </form>
            </section>
          )}
          <section className="surface management-surface">
            <div className="record-table-head department-columns"><span>Department</span><span>Doctors</span><span>Status</span><span>Actions</span></div>
            {data.departments.map((item) => {
              const count = data.assignments.filter((doctor) => doctor.department_id === item.id).length;
              return <div className="record-table-row department-columns" key={item.id}>
                <strong>{item.name}</strong>
                <span>{count} {count === 1 ? "doctor" : "doctors"}</span>
                <Badge appearance="tint" color={item.active ? "success" : "informative"}>{item.active ? "Active" : "Inactive"}</Badge>
                <div className="row-actions">
                  <Button size="small" onClick={() => setDepartmentEditor({ id: item.id, name: item.name, active: item.active })}>Edit</Button>
                  <Button size="small" appearance="subtle" disabled={saving} onClick={() => runChange(() => request(`departments/${item.id}`, "PATCH", { name: item.name, active: !item.active }), item.active ? "Department deactivated." : "Department activated.")}>{item.active ? "Deactivate" : "Activate"}</Button>
                </div>
              </div>;
            })}
            {!data.departments.length && <div className="empty-panel">No departments yet. Add the first department to start assigning doctors.</div>}
          </section>
        </>
      )}

      {focus === "doctors" && (
        <>
          <div className="management-header">
            <div><h2>Doctors</h2><p>Manage doctor details, booking status, and recurring weekly hours.</p></div>
            <Button appearance="primary" onClick={() => setDoctorEditor({ ...blankDoctor, departmentId: activeDepartments[0]?.id ?? "", locationId: activeLocations[0]?.id ?? "" })}>＋ Add doctor</Button>
          </div>
          {doctorEditor && (
            <section className="surface editor-panel">
              <div className="editor-heading"><div><h3>{doctorEditor.id ? "Edit doctor" : "Add doctor"}</h3><p>Set the doctor’s department, clinic site, and consultation fee.</p></div><Button appearance="subtle" onClick={() => setDoctorEditor(null)}>Close</Button></div>
              <form className="admin-form doctor-form" onSubmit={saveDoctor}>
                <label>Doctor name<Input value={doctorEditor.name} onChange={(_, value) => setDoctorEditor({ ...doctorEditor, name: value.value })} required /></label>
                <label>Department<Select value={doctorEditor.departmentId} onChange={(_, value) => setDoctorEditor({ ...doctorEditor, departmentId: value.value })} required><option value="">Choose department</option>{activeDepartments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></label>
                <label>Clinic site<Select value={doctorEditor.locationId} onChange={(_, value) => setDoctorEditor({ ...doctorEditor, locationId: value.value })} required><option value="">Choose site</option>{activeLocations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</Select></label>
                <label>Consultation fee (INR)<Input type="number" min="0" step="0.01" value={doctorEditor.fee} onChange={(_, value) => setDoctorEditor({ ...doctorEditor, fee: value.value })} required /></label>
                <Button type="submit" appearance="primary" disabled={saving}>{saving ? "Saving…" : doctorEditor.id ? "Save changes" : "Add doctor"}</Button>
              </form>
            </section>
          )}
          <section className="surface management-surface doctor-directory">
            {data.assignments.map((doctor) => {
              const rules = data.schedule_rules.filter((rule) => rule.assignment_id === doctor.id);
              const expanded = expandedDoctor === doctor.id;
              return <article className="doctor-record" key={doctor.id}>
                <div className="doctor-record-main">
                  <div className="doctor-avatar">{doctor.display_name.replace(/^Dr\.?\s*/i, "").charAt(0).toUpperCase()}</div>
                  <div className="doctor-identity"><strong>{doctor.display_name}</strong><span>{doctor.department_name} · {doctor.location_name}</span><small>{formatInrMinor(doctor.fee_minor)} consultation</small></div>
                  <div className="doctor-status"><Switch checked={doctor.active} disabled={saving} label={doctor.active ? "Accepting bookings" : "Bookings paused"} onChange={(_, value) => runChange(() => request(`assignments/${doctor.id}`, "PATCH", { active: value.checked }), value.checked ? "Doctor activated." : "Doctor paused.")} /></div>
                  <div className="row-actions">
                    <Button size="small" onClick={() => setExpandedDoctor(expanded ? null : doctor.id)}>{expanded ? "Hide schedule" : "Weekly schedule"}</Button>
                    <Button size="small" appearance="subtle" onClick={() => setDoctorEditor({ id: doctor.id, name: doctor.display_name, departmentId: doctor.department_id, locationId: doctor.location_id, fee: minorToRupees(doctor.fee_minor) })}>Edit</Button>
                    <Button size="small" appearance="subtle" disabled={saving} onClick={() => void deleteDoctor(doctor)} style={{ color: "#c4314b" }}>Delete</Button>
                  </div>
                </div>
                {expanded && <div className="weekly-panel">
                  <div className="weekly-panel-heading"><div><h3>Weekly availability</h3><p>Select any day to add or edit recurring clinic hours.</p></div><div className="schedule-heading-actions"><div className="availability-legend"><span className="available-dot">Available</span><span className="unavailable-dot">Unavailable</span></div><Button size="small" appearance="primary" onClick={() => setScheduleEditor({ ...blankSchedule, assignmentId: doctor.id })}>＋ Add availability</Button></div></div>
                  <div className="weekly-grid">
                    {weekdays.map((day, dayIndex) => {
                      const dayRules = rules.filter((rule) => rule.weekday === dayIndex);
                      const available = dayRules.some((rule) => rule.active);
                      return <div className={`weekly-day ${available ? "available" : "unavailable"}`} key={day}>
                        <div className="weekly-day-heading"><strong>{day}</strong><span>{available ? "Available" : "Unavailable"}</span></div>
                        <div>{dayRules.length ? dayRules.map((rule) => <button className={`schedule-chip ${rule.active ? "" : "inactive"}`} key={rule.id} type="button" onClick={() => setScheduleEditor({ id: rule.id, assignmentId: doctor.id, weekday: String(rule.weekday), startsAt: rule.local_starts_at.slice(0, 5), endsAt: rule.local_ends_at.slice(0, 5), limit: String(rule.max_patients ?? 30), active: rule.active })}><span>{rule.local_starts_at.slice(0, 5)}–{rule.local_ends_at.slice(0, 5)}</span><small>{rule.active ? `Up to ${rule.max_patients ?? 30} patients` : "Disabled · click to edit"}</small></button>) : <button className="add-day-hours" type="button" onClick={() => setScheduleEditor({ ...blankSchedule, assignmentId: doctor.id, weekday: String(dayIndex) })}>＋ Add hours</button>}</div>
                      </div>;
                    })}
                  </div>
                  {scheduleEditor?.assignmentId === doctor.id && scheduleEditorView}
                </div>}
              </article>;
            })}
            {!data.assignments.length && <div className="empty-panel">No doctors yet. Add the first doctor and then configure weekly hours.</div>}
          </section>
        </>
      )}

      {focus === "settings" && (
        <>
          <div className="management-header">
            <div><h2>{data.organization.organization_type === "HOSPITAL" ? "Hospital" : "Clinic"} settings</h2><p>Manage the organization and its single reception site.</p></div>
            {!editingClinic && <Button appearance="primary" onClick={() => setEditingClinic(true)}>Edit details</Button>}
          </div>
          <section className="surface clinic-profile">
            {!editingClinic ? <>
              <div className="profile-title"><div className="clinic-monogram">{data.organization.name.charAt(0)}</div><div><strong>{data.organization.name}</strong><span>{data.organization.organization_type === "HOSPITAL" ? "Hospital" : "Clinic"} · Active</span></div></div>
              <dl className="profile-details">
                <div><dt>Reception site</dt><dd>{data.locations[0]?.name || "Not configured"}</dd></div>
                <div><dt>Address</dt><dd>{data.locations[0]?.address || "No address added"}</dd></div>
                <div><dt>Timezone</dt><dd>{data.organization.timezone}</dd></div>
                <div><dt>Currency</dt><dd>INR</dd></div>
              </dl>
            </> : <form className="clinic-form" onSubmit={saveClinic}>
              <div className="editor-heading"><div><h3>Edit clinic details</h3><p>This prototype uses one clinic or hospital with one reception site.</p></div><Button appearance="subtle" onClick={() => setEditingClinic(false)}>Cancel</Button></div>
              <div className="admin-form">
                <label>Organization name<Input value={clinicName} onChange={(_, value) => setClinicName(value.value)} required /></label>
                <label>Organization type<Select value={clinicType} onChange={(_, value) => setClinicType(value.value as typeof clinicType)}><option value="CLINIC">Clinic</option><option value="HOSPITAL">Hospital</option></Select></label>
                <label>Site name<Input value={siteName} onChange={(_, value) => setSiteName(value.value)} required /></label>
                <label>Address<Input value={siteAddress} onChange={(_, value) => setSiteAddress(value.value)} /></label>
                <Button type="submit" appearance="primary" disabled={saving}>{saving ? "Saving…" : "Save details"}</Button>
              </div>
            </form>}
          </section>
        </>
      )}
    </div>
  );
}
