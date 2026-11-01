import { FormEvent, useEffect, useMemo, useState } from "react";
import { Badge, Button, Input, Select, Title2 } from "@fluentui/react-components";
import { SearchRegular } from "@fluentui/react-icons";

import { restoreSession } from "../lib/supabaseAuth";

export type Appointment = { id: string; organization_id: string; booking_reference: string; status: string; queue_status: string | null; version: number; token_number: number | null; patient_name: string; booker_name: string; phone_e164: string; scheduled_at: string; doctor_name: string; assignment_id: string; department_name: string; location_name: string; fee_minor?: number; currency?: string; payment_method?: string | null; payment_status?: string | null };
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const formatDateTime = (value: string) => new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(value));
const localDate = (value: string) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(value));
const formatMoney = (minor: number, currency = "INR") => new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(minor / 100);

export function AppointmentsManager(props: { appointments: Appointment[]; search: string; onSearch: (value: string) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onCancel: (item: Appointment) => void; onReschedule: (item: Appointment) => void; loading: boolean; onRefresh?: () => void }) {
  const [records, setRecords] = useState(props.appointments);
  const [visitError, setVisitError] = useState("");
  const initialToday = localDate(new Date().toISOString());
  const hasActiveToday = props.appointments.some(item => localDate(item.scheduled_at) === initialToday && item.status === "CONFIRMED");
  const hasUpcoming = props.appointments.some(item => localDate(item.scheduled_at) > initialToday && item.status === "CONFIRMED");
  const [doctor, setDoctor] = useState(""); const [department, setDepartment] = useState(""); const [location, setLocation] = useState(""); const [status, setStatus] = useState(""); const [date, setDate] = useState(""); const [updating, setUpdating] = useState(""); const [scope, setScope] = useState<"today" | "upcoming" | "history">(hasActiveToday || !hasUpcoming ? "today" : "upcoming");
  useEffect(() => setRecords(props.appointments), [props.appointments]);
  const values = (field: keyof Appointment) => Array.from(new Set(records.map(item => String(item[field] ?? "")).filter(Boolean))).sort();
  const today = localDate(new Date().toISOString());
  const filtered = useMemo(() => records.filter(item => {
    const recordDate = localDate(item.scheduled_at);
    const matchesScope = scope === "today" ? recordDate === today : scope === "upcoming" ? recordDate >= today && item.status === "CONFIRMED" : recordDate < today || item.status !== "CONFIRMED";
    return matchesScope && (!doctor || item.doctor_name === doctor) && (!department || item.department_name === department) && (!location || item.location_name === location) && (!status || item.status === status) && (!date || recordDate === date);
  }), [records, doctor, department, location, status, date, scope, today]);
  async function visit(item: Appointment, queueStatus: string) { setUpdating(item.id); setVisitError(""); try { const session = await restoreSession(); if (!session) throw new Error("Your session expired. Sign in again."); const response = await fetch(`${apiBaseUrl}/v1/appointments/${item.id}/visit-status`, { method: "POST", headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json" }, body: JSON.stringify({ organization_id: item.organization_id, expected_version: item.version, queue_status: queueStatus }) }); const updated = await response.json().catch(() => null) as (Partial<Appointment> & { message?: string }) | null; if (!response.ok) throw new Error(updated?.message ?? "Visit status could not be updated."); setRecords(current => current.map(record => record.id === item.id ? { ...record, ...updated } : record)); } catch (error) { setVisitError(error instanceof Error ? error.message : "Visit status could not be updated."); } finally { setUpdating(""); } }
  const todayRecords = records.filter(item => localDate(item.scheduled_at) === today);
  const confirmed = todayRecords.filter(item => item.status === "CONFIRMED").length;
  const checkedIn = todayRecords.filter(item => item.queue_status === "CHECKED_IN" || item.queue_status === "CALLED" || item.queue_status === "IN_CONSULTATION").length;
  const completed = todayRecords.filter(item => item.status === "COMPLETED").length;
  return <div className="page-stack appointments-operations">
    <section className="appointments-heading"><div><Title2>Appointment operations</Title2><p>Manage arrivals, queues, rescheduling, and visit outcomes.</p></div><form onSubmit={props.onSubmit} style={{ display: "flex", gap: "8px" }}><Input value={props.search} onChange={(_, data) => props.onSearch(data.value)} contentBefore={<SearchRegular />} placeholder="Reference, patient, caller or phone"/><Button type="submit" appearance="primary" disabled={props.loading}>Search</Button>{props.onRefresh && <Button type="button" appearance="secondary" onClick={props.onRefresh}>Refresh</Button>}</form></section>
    {visitError && <div className="alert-banner error">{visitError}</div>}
    <section className="appointment-summary"><button className={scope === "today" ? "active" : ""} onClick={() => setScope("today")}><span>Today</span><strong>{todayRecords.length}</strong><small>{confirmed} active</small></button><button className={scope === "upcoming" ? "active" : ""} onClick={() => setScope("upcoming")}><span>Upcoming</span><strong>{records.filter(item => localDate(item.scheduled_at) > today && item.status === "CONFIRMED").length}</strong><small>Confirmed visits</small></button><button className={scope === "history" ? "active" : ""} onClick={() => setScope("history")}><span>History</span><strong>{records.filter(item => item.status !== "CONFIRMED").length}</strong><small>Closed records</small></button><div><span>Checked in</span><strong>{checkedIn}</strong><small>{completed} completed today</small></div></section>
    <section className="appointment-filters"><Select aria-label="Doctor filter" value={doctor} onChange={(_, data) => setDoctor(data.value)}><option value="">All doctors</option>{values("doctor_name").map(x => <option key={x}>{x}</option>)}</Select><Select aria-label="Department filter" value={department} onChange={(_, data) => setDepartment(data.value)}><option value="">All departments</option>{values("department_name").map(x => <option key={x}>{x}</option>)}</Select><Select aria-label="Location filter" value={location} onChange={(_, data) => setLocation(data.value)}><option value="">All locations</option>{values("location_name").map(x => <option key={x}>{x}</option>)}</Select><Select aria-label="Status filter" value={status} onChange={(_, data) => setStatus(data.value)}><option value="">All statuses</option>{values("status").map(x => <option key={x}>{x.replaceAll("_", " ")}</option>)}</Select><Input aria-label="Appointment date" type="date" value={date} onChange={(_, data) => setDate(data.value)} /><Button appearance="subtle" onClick={() => { setDoctor(""); setDepartment(""); setLocation(""); setStatus(""); setDate(""); }}>Clear filters</Button></section>
    <section className="appointment-records">
      <div className="appointment-record-head appointment-record-grid"><span>Patient</span><span>Appointment</span><span>Visit status</span><span>Payment</span><span>Actions</span></div>
      {filtered.map(item => <article className="appointment-record appointment-record-grid" key={item.id}>
        <div className="appointment-patient"><span className="patient-avatar">{item.patient_name.charAt(0).toUpperCase()}</span><div><strong>{item.patient_name}</strong><span>{item.phone_e164}</span><small>Booked by {item.booker_name} · {item.booking_reference}</small></div></div>
        <div className="appointment-schedule"><strong>{formatDateTime(item.scheduled_at)}</strong><span>{item.doctor_name} · {item.department_name}</span><small>{item.location_name}{item.token_number ? ` · Token ${item.token_number}` : ""}</small></div>
        <div className="appointment-state"><Badge appearance="tint" color={item.status === "CONFIRMED" ? "success" : item.status === "COMPLETED" ? "brand" : "important"}>{item.status.replaceAll("_", " ")}</Badge><span>{item.queue_status?.replaceAll("_", " ") ?? "Not arrived"}</span></div>
        <div className="appointment-payment"><strong>{item.payment_method?.replaceAll("_", " ") ?? "Legacy"}</strong><span>{item.payment_status === "DUE_AT_CLINIC" ? "Due at clinic" : item.payment_status === "SIMULATED_SUCCESS" ? "Recorded" : item.payment_status?.replaceAll("_", " ") ?? "Not recorded"}</span><small>{formatMoney(item.fee_minor ?? 0, item.currency ?? "INR")}</small></div>
        <div className="appointment-actions">{item.status === "CONFIRMED" ? <><Button size="small" appearance="primary" disabled={updating === item.id} onClick={() => visit(item, "CHECKED_IN")}>Check in</Button><Button size="small" disabled={updating === item.id} onClick={() => visit(item, "SERVED")}>Complete</Button><Button size="small" appearance="subtle" onClick={() => props.onReschedule(item)}>Reschedule</Button><Button size="small" appearance="subtle" disabled={updating === item.id} onClick={() => visit(item, "SKIPPED")}>No-show</Button><Button size="small" appearance="subtle" onClick={() => props.onCancel(item)}>Cancel</Button></> : <span className="no-actions">No action required</span>}</div>
      </article>)}
      {!filtered.length && <div className="empty-panel">No appointments match this view and its filters.</div>}
    </section>
  </div>;
}
