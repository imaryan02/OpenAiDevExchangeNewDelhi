import { FormEvent, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Avatar, Badge, Button, Input, Select, Spinner, Text, Title1, Title2 } from "@fluentui/react-components";
import { ArrowLeftRegular, ArrowRightRegular, AddRegular, BuildingRegular, CalendarMonthRegular, ChatRegular, ClipboardTaskRegular, HomeRegular, PeopleRegular, PeopleTeamRegular, SearchRegular, SettingsRegular, SignOutRegular } from "@fluentui/react-icons";

import { authenticatedFetch, clearStoredSession, restoreSession, signInWithPassword, type AuthSession } from "./lib/supabaseAuth";
import { AdminSettingsPage as SettingsPage } from "./components/AdminSettingsPage";
import { AppointmentsManager as AppointmentsPage } from "./components/AppointmentsManager";
import { AvailabilityPage } from "./components/AvailabilityPage";
import { BookingPage } from "./components/BookingPage";
import { PatientsPage } from "./components/PatientsPage";
import { AiAssistantPage } from "./components/AiAssistantPage";
import { PresentationPage } from "./components/PresentationPage";
import { OverviewPage } from "./components/OverviewPage";
import { ReceptionistToggle } from "./personal-agent/ReceptionistToggle";
import { VoiceCallHistoryPage } from "./components/VoiceCallHistoryPage";

import { createWorkspaceNavigation, type WorkspacePage as Page } from "./lib/workspaceNavigation";
type Membership = { organization_id: string; role: "ORG_ADMIN" | "RECEPTIONIST" | "VIEWER" };
type MeResponse = { user_id: string; memberships: Membership[] };
type BookingSlot = { id: string; starts_at: string; ends_at: string };
type BookingOption = { id: string; assignment_id: string; booking_mode: "EXACT_TIME" | "SESSION_TOKEN"; starts_at: string; ends_at: string; max_patients: number | null; occupied: number; doctor_name: string; location_name: string; slots: BookingSlot[] };
type Intake = { contact_id: string; phone_id: string; patient_id: string };
type Hold = { appointment_id: string; booking_reference: string };
type Confirmation = { booking_reference: string; token_number: number | null };
type AppointmentRecord = { id: string; organization_id: string; booking_reference: string; status: string; queue_status: string | null; version: number; token_number: number | null; patient_name: string; booker_name: string; phone_e164: string; booking_mode: "EXACT_TIME" | "SESSION_TOKEN"; scheduled_at: string; doctor_name: string; assignment_id: string; department_name: string; location_name: string; fee_minor: number; currency: string; source: string; payment_method: string | null; payment_status: string | null };
type Configuration = { organization: { id: string; name: string; organization_type: "CLINIC" | "HOSPITAL"; timezone: string; status: string }; locations: { id: string; name: string; address: string; timezone: string; active: boolean }[]; departments: { id: string; name: string; active: boolean }[]; assignments: { id: string; display_name: string; doctor_name: string; location_id: string; department_id: string; location_name: string; department_name: string; fee_minor: number; currency: string; active: boolean }[]; schedule_rules: { id: string; assignment_id: string; weekday: number; local_starts_at: string; local_ends_at: string; booking_mode: "EXACT_TIME" | "SESSION_TOKEN"; slot_minutes: number | null; max_patients: number | null; active: boolean }[]; schedule_exceptions?: { id: string; assignment_id: string; local_date: string; exception_type: string; reason: string }[] };

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const optionWindow = (weekOffset = 0) => {
  const from = new Date(Date.now() + weekOffset * 7 * 86400000);
  return { from: from.toISOString(), to: new Date(from.getTime() + 14 * 86400000).toISOString() };
};
const formatDateTime = (value: string) => new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(value));
const formatDay = (value: Date) => new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Kolkata" }).format(value);
const dateKey = (value: string | Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(value));
const appointmentPageSize = 250;

export function App() {
  const conferencePreview = new URLSearchParams(window.location.search).has("conference");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [options, setOptions] = useState<BookingOption[]>([]);
  const [appointments, setAppointments] = useState<AppointmentRecord[]>([]);
  const [configuration, setConfiguration] = useState<Configuration | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [selectedSlotId, setSelectedSlotId] = useState("");
  const [bookerName, setBookerName] = useState("");
  const [phone, setPhone] = useState("+91");
  const [patientName, setPatientName] = useState("");
  const [relationship, setRelationship] = useState("SELF");
  const [paymentMethod, setPaymentMethod] = useState<"CASH" | "UPI" | "CARD">("CASH");
  const [appointmentSearch, setAppointmentSearch] = useState("");
  const [navigation] = useState(() => createWorkspaceNavigation(window));
  const route = useSyncExternalStore(navigation.subscribe, navigation.getSnapshot);
  const activePage = route.page;
  const [calendarOffset, setCalendarOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const selectedSessionIdRef = useRef(selectedSessionId);
  const appointmentSearchRef = useRef(appointmentSearch);
  const activeMembership = useMemo(() => me?.memberships[0] ?? null, [me]);
  const selectedSession = options.find((option) => option.id === selectedSessionId) ?? null;

  useEffect(() => { selectedSessionIdRef.current = selectedSessionId; }, [selectedSessionId]);
  useEffect(() => { appointmentSearchRef.current = appointmentSearch; }, [appointmentSearch]);

  async function apiFetch<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
    const response = await authenticatedFetch(`${apiBaseUrl}${path}`, session ?? { access_token: accessToken, refresh_token: "", user: {} }, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
    const payload = (await response.json().catch(() => null)) as { message?: string; detail?: Array<{ msg?: string }> } | T | null;
    if (!response.ok) { const failure = payload as { message?: string; detail?: Array<{ msg?: string }> } | null; throw new Error(failure?.message ?? failure?.detail?.[0]?.msg ?? "The backend could not complete this request."); }
    return payload as T;
  }

  async function loadWorkspace(activeSession: AuthSession) {
    const workspace = await apiFetch<MeResponse>("/v1/me", activeSession.access_token);
    if (!workspace.memberships.length) throw new Error("Your account does not have access to a reception workspace.");
    setMe(workspace); return workspace;
  }
  async function loadBookingOptions(activeSession: AuthSession, organizationId: string, weekOffset = calendarOffset) {
    const window = optionWindow(weekOffset);
    const records = await apiFetch<BookingOption[]>(`/v1/booking-options?${new URLSearchParams({ organization_id: organizationId, from: window.from, to: window.to })}`, activeSession.access_token);
    setOptions(records);
    if (!records.some((item) => item.id === selectedSessionIdRef.current)) { setSelectedSessionId(records[0]?.id ?? ""); setSelectedSlotId(records[0]?.slots[0]?.id ?? ""); }
  }
  async function loadAppointments(activeSession: AuthSession, organizationId: string, search = "") {
    const records: AppointmentRecord[] = [];
    for (let offset = 0; ; offset += appointmentPageSize) {
      const page = await apiFetch<AppointmentRecord[]>(`/v1/appointments?${new URLSearchParams({ organization_id: organizationId, query: search.trim(), limit: String(appointmentPageSize), offset: String(offset) })}`, activeSession.access_token);
      records.push(...page);
      if (page.length < appointmentPageSize) break;
    }
    setAppointments(records);
  }
  async function loadConfiguration(activeSession: AuthSession, organizationId: string) { setConfiguration(await apiFetch<Configuration>(`/v1/configuration?${new URLSearchParams({ organization_id: organizationId })}`, activeSession.access_token)); }
  async function loadAll(activeSession: AuthSession, organizationId: string) { await Promise.all([loadBookingOptions(activeSession, organizationId), loadAppointments(activeSession, organizationId), loadConfiguration(activeSession, organizationId)]); }
  async function refreshAgentChanges() { if (!session || !activeMembership) return; await Promise.all([loadBookingOptions(session, activeMembership.organization_id), loadAppointments(session, activeMembership.organization_id)]); }
  function changeCalendarOffset(nextOffset: number) {
    setCalendarOffset(nextOffset);
    if (!session || !activeMembership) return;
    void loadBookingOptions(session, activeMembership.organization_id, nextOffset).catch((caught) =>
      setError(caught instanceof Error ? caught.message : "Could not load calendar availability."),
    );
  }
  function navigateTo(page: Page) { navigation.navigate(page); if (!session || !activeMembership || !["overview", "calendar", "appointments"].includes(page)) return; void Promise.all([loadBookingOptions(session, activeMembership.organization_id), loadAppointments(session, activeMembership.organization_id)]).catch((caught) => setError(caught instanceof Error ? caught.message : "Could not refresh clinic records.")); }

  useEffect(() => { const initialize = async () => { const saved = await restoreSession(); if (!saved) { setLoading(false); return; } try { setSession(saved); const workspace = await loadWorkspace(saved); await loadAll(saved, workspace.memberships[0].organization_id); } catch (caught) { clearStoredSession(); setSession(null); setMe(null); setError(caught instanceof Error ? caught.message : "Could not restore your session."); } finally { setLoading(false); } }; void initialize(); }, []);

  useEffect(() => {
    if (!session || !activeMembership) return;
    const interval = setInterval(() => {
      void Promise.all([
        loadBookingOptions(session, activeMembership.organization_id),
        loadAppointments(session, activeMembership.organization_id, appointmentSearchRef.current),
      ]).catch(() => undefined);
    }, 6000);
    const handleFocus = () => {
      void Promise.all([
        loadBookingOptions(session, activeMembership.organization_id),
        loadAppointments(session, activeMembership.organization_id, appointmentSearchRef.current),
      ]).catch(() => undefined);
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener("focus", handleFocus);
    };
  }, [session, activeMembership, calendarOffset]);

  async function handleSignIn(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setError(null); setSubmitting(true); try { const next = await signInWithPassword(email, password); setSession(next); const workspace = await loadWorkspace(next); await loadAll(next, workspace.memberships[0].organization_id); setPassword(""); } catch (caught) { clearStoredSession(); setSession(null); setMe(null); setError(caught instanceof Error ? caught.message : "Sign-in failed."); } finally { setSubmitting(false); } }
  async function handleBooking(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!session || !activeMembership || !selectedSession) return; if (selectedSession.booking_mode === "EXACT_TIME" && !selectedSlotId) { setError("Choose an available exact-time slot."); return; } setError(null); setMessage(null); setSubmitting(true); try { const intake = await apiFetch<Intake>("/v1/booking-intake", session.access_token, { method: "POST", body: JSON.stringify({ organization_id: activeMembership.organization_id, booker_name: bookerName, phone_e164: phone.replace(/[\s()\-]/g, ""), patient_name: patientName, relationship }) }); const key = crypto.randomUUID(); const hold = await apiFetch<Hold>("/v1/appointments/holds", session.access_token, { method: "POST", body: JSON.stringify({ organization_id: activeMembership.organization_id, patient_id: intake.patient_id, contact_id: intake.contact_id, notification_phone_id: intake.phone_id, assignment_id: selectedSession.assignment_id, session_id: selectedSession.id, slot_id: selectedSession.booking_mode === "EXACT_TIME" ? selectedSlotId : null, source: "STAFF", idempotency_key: key, request_hash: key.replaceAll("-", ""), consent_confirmed: true, consent_language: "en", consent_channel: "STAFF_UI" }) }); const confirmation = await apiFetch<Confirmation>(`/v1/appointments/${hold.appointment_id}/confirm?organization_id=${activeMembership.organization_id}`, session.access_token, { method: "POST", body: JSON.stringify({ payment_method: paymentMethod }) }); setMessage(`Appointment ${confirmation.booking_reference} confirmed for ${patientName}.${confirmation.token_number ? ` Token number: ${confirmation.token_number}.` : ""} Payment: ${paymentMethod === "CASH" ? "due at clinic" : paymentMethod}.`); setPatientName(""); await loadAll(session, activeMembership.organization_id); navigation.navigate("appointments"); } catch (caught) { setError(caught instanceof Error ? caught.message : "The appointment could not be booked."); } finally { setSubmitting(false); } }
  async function searchAppointments(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!session || !activeMembership) return; setSubmitting(true); try { await loadAppointments(session, activeMembership.organization_id, appointmentSearch); } catch (caught) { setError(caught instanceof Error ? caught.message : "Search failed."); } finally { setSubmitting(false); } }
  async function cancelAppointment(appointment: AppointmentRecord) { if (!session || !activeMembership || !window.confirm(`Cancel appointment ${appointment.booking_reference} for ${appointment.patient_name}?`)) return; setSubmitting(true); try { await apiFetch(`/v1/appointments/${appointment.id}/cancel`, session.access_token, { method: "POST", body: JSON.stringify({ organization_id: activeMembership.organization_id, expected_version: appointment.version, reason: "Cancelled by reception staff" }) }); setMessage(`Appointment ${appointment.booking_reference} was cancelled.`); await loadAll(session, activeMembership.organization_id); } catch (caught) { setError(caught instanceof Error ? caught.message : "Cancellation failed."); } finally { setSubmitting(false); } }
  async function rescheduleAppointment(appointment: AppointmentRecord) { if (!session || !activeMembership || !selectedSession || !window.confirm(`Move ${appointment.booking_reference} to the selected calendar availability?`)) return; setSubmitting(true); try { const replacement = await apiFetch<{ replacement_reference: string; replacement_token: number | null }>(`/v1/appointments/${appointment.id}/reschedule`, session.access_token, { method: "POST", body: JSON.stringify({ organization_id: activeMembership.organization_id, expected_version: appointment.version, new_session_id: selectedSession.id, new_slot_id: selectedSession.booking_mode === "EXACT_TIME" ? selectedSlotId : null }) }); setMessage(`Appointment moved to ${replacement.replacement_reference}.${replacement.replacement_token ? ` Token ${replacement.replacement_token}.` : ""}`); await loadAll(session, activeMembership.organization_id); } catch (caught) { setError(caught instanceof Error ? caught.message : "Rescheduling failed."); } finally { setSubmitting(false); } }
  function selectSession(id: string) { const option = options.find((item) => item.id === id); setSelectedSessionId(id); setSelectedSlotId(option?.slots[0]?.id ?? ""); }
  function signOut() { clearStoredSession(); setSession(null); setMe(null); setOptions([]); setAppointments([]); }

  if (conferencePreview) {
    if (loading) return <main className="app-loading"><Spinner size="large" label="Loading conference access" /></main>;
    if (!session || !me || !activeMembership) return <SignInScreen email={email} password={password} error={error} loading={submitting} onEmail={setEmail} onPassword={setPassword} onSubmit={handleSignIn} />;
    return <main className="conference-preview"><PresentationPage organizationId={activeMembership.organization_id} accessToken={session.access_token} apiBaseUrl={apiBaseUrl} clinicName={configuration?.organization.name ?? "Geeta Medicine"} allowLive /></main>;
  }
  if (loading) return <main className="app-loading"><Spinner size="large" label="Loading reception workspace" /></main>;
  if (!session || !me || !activeMembership) return <SignInScreen email={email} password={password} error={error} loading={submitting} onEmail={setEmail} onPassword={setPassword} onSubmit={handleSignIn} />;
  return <Dashboard navigation={navigation} route={route} activePage={activePage} onPage={navigateTo} session={session} membership={activeMembership} options={options} appointments={appointments} configuration={configuration} onConfigurationChange={setConfiguration} selectedSession={selectedSession} selectedSessionId={selectedSessionId} selectedSlotId={selectedSlotId} onSession={selectSession} onSlot={setSelectedSlotId} bookerName={bookerName} phone={phone} patientName={patientName} relationship={relationship} paymentMethod={paymentMethod} onBooker={setBookerName} onPhone={setPhone} onPatient={setPatientName} onRelationship={setRelationship} onPaymentMethod={setPaymentMethod} onBooking={handleBooking} appointmentSearch={appointmentSearch} onSearch={setAppointmentSearch} onSearchSubmit={searchAppointments} onCancel={cancelAppointment} onReschedule={rescheduleAppointment} onAgentDataChange={refreshAgentChanges} onSignOut={signOut} onBookingPage={() => navigateTo("booking")} error={error} message={message} loading={submitting} calendarOffset={calendarOffset} onCalendarOffset={changeCalendarOffset} />;
}

function SignInScreen({ email, password, error, loading, onEmail, onPassword, onSubmit }: { email: string; password: string; error: string | null; loading: boolean; onEmail: (value: string) => void; onPassword: (value: string) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) { return <main className="sign-in"><section className="sign-in-brand"><span className="brand-mark">GM</span><Text>GEETA MEDICINE</Text><Title1>Reception, made effortless.</Title1><p>Appointments, queues, and patient coordination in one protected workspace.</p></section><section className="sign-in-card"><Text className="section-kicker">STAFF ACCESS</Text><Title2>Welcome back</Title2><p>Sign in to manage today’s care.</p><form onSubmit={onSubmit}><label>Email address<Input value={email} onChange={(_, data) => onEmail(data.value)} type="email" required /></label><label>Password<Input value={password} onChange={(_, data) => onPassword(data.value)} type="password" required /></label>{error && <p className="form-error">{error}</p>}<Button appearance="primary" type="submit" disabled={loading}>{loading ? "Signing in…" : "Sign in"}</Button></form></section></main>; }

function Dashboard(props: any) {
  const days = Array.from({ length: 7 }, (_, index) => new Date(Date.now() + (props.calendarOffset * 7 + index) * 86400000));
  const nav = [
    { id: "overview", label: "Overview", icon: HomeRegular },
    { id: "calendar", label: "Availability", icon: CalendarMonthRegular },
    { id: "appointments", label: "Appointments", icon: ClipboardTaskRegular },
    { id: "patients", label: "Patients", icon: PeopleRegular },
    { id: "booking", label: "New booking", icon: AddRegular },
    { id: "assistant", label: "AI assistant", icon: ChatRegular },
    { id: "presentation", label: "Inside the call", icon: ChatRegular },
    { id: "calls", label: "Voice call history", icon: ChatRegular },
    { id: "departments", label: "Departments", icon: BuildingRegular },
    { id: "doctors", label: "Doctors", icon: PeopleTeamRegular },
    { id: "settings", label: "Clinic settings", icon: SettingsRegular },
  ] as const;
  return <div className="dashboard-shell">
    <aside className="sidebar"><div className="sidebar-brand"><span className="brand-mark">GM</span><span>{props.configuration?.organization.name ?? "Geeta Medicine"}</span></div><ReceptionistToggle session={props.session} /><nav>{nav.filter(item => item.id !== "calls" || props.membership.role !== "VIEWER").map((item) => { const Icon = item.icon; return <button key={item.id} className={props.activePage === item.id ? "nav-item active" : "nav-item"} onClick={() => props.onPage(item.id)}><Icon /><span>{item.label}</span></button>; })}<a className="nav-item" href="/demo/personal-agent" aria-label="Friday / Personal AI" title="Open Friday Personal AI"><ChatRegular /><span>Friday / Personal AI</span></a></nav><div className="sidebar-footer"><button className="nav-item"><PeopleRegular /><span>Support</span></button></div></aside>
    <main className="dashboard-main"><header className="topbar"><div><Text className="section-kicker">{props.configuration ? `${props.configuration.organization.name.toUpperCase()} · ${props.configuration.locations[0]?.name.toUpperCase() ?? ""}` : "RECEPTION WORKSPACE"}</Text><Title1>{pageTitle(props.activePage)}</Title1></div><div className="topbar-actions"><div className="workspace-history" role="group" aria-label="Page navigation"><Button appearance="subtle" icon={<ArrowLeftRegular />} disabled={!props.route.canGoBack} onClick={props.navigation.back} aria-label="Go back" title="Go back" /><Button appearance="subtle" icon={<ArrowRightRegular />} disabled={!props.route.canGoForward} onClick={props.navigation.forward} aria-label="Go forward" title="Go forward" /></div><Button appearance="primary" icon={<AddRegular />} onClick={props.onBookingPage}>New appointment</Button><Avatar name={props.session.user.email ?? "Staff"} size={36} /><Button appearance="subtle" icon={<SignOutRegular />} onClick={props.onSignOut}>Sign out</Button></div></header>
      {props.error && <div className="alert-banner error">{props.error}</div>}{props.message && <div className="alert-banner success">{props.message}</div>}
      {props.activePage === "overview" && <OverviewPage appointments={props.appointments} options={props.options} clinicName={props.configuration?.organization.name ?? "Geeta Medicine"} locationName={props.configuration?.locations[0]?.name ?? ""} onPage={props.onPage} />}
      {props.activePage === "calendar" && <AvailabilityPage days={days} options={props.options} appointments={props.appointments} configuration={props.configuration} offset={props.calendarOffset} onOffset={props.onCalendarOffset} onBooking={props.onBookingPage} />}
      {props.activePage === "appointments" && <AppointmentsPage appointments={props.appointments} search={props.appointmentSearch} onSearch={props.onSearch} onSubmit={props.onSearchSubmit} onCancel={props.onCancel} onReschedule={props.onReschedule} loading={props.loading} onRefresh={props.onAgentDataChange} />}
      {props.activePage === "patients" && <PatientsPage organizationId={props.membership.organization_id} />}
      {props.activePage === "booking" && <BookingPage {...props} />}
      {props.activePage === "assistant" && <AiAssistantPage organizationId={props.membership.organization_id} onDataChange={props.onAgentDataChange} />}
      {props.activePage === "presentation" && <PresentationPage onExit={() => props.onPage("overview")} organizationId={props.membership.organization_id} accessToken={props.session.access_token} apiBaseUrl={apiBaseUrl} clinicName={props.configuration?.organization.name ?? "Geeta Medicine"} allowLive />}
      {props.activePage === "calls" && <VoiceCallHistoryPage organizationId={props.membership.organization_id} accessToken={props.session.access_token} selectedCallId={props.route.callId} onSelectCall={(callId: string | null) => props.navigation.navigate("calls", callId)} />}
      {props.activePage === "departments" && <SettingsPage configuration={props.configuration} focus="departments" onConfigurationChange={props.onConfigurationChange} />}
      {props.activePage === "doctors" && <SettingsPage configuration={props.configuration} focus="doctors" onConfigurationChange={props.onConfigurationChange} />}
      {props.activePage === "settings" && <SettingsPage configuration={props.configuration} focus="settings" onConfigurationChange={props.onConfigurationChange} />}
    </main>
  </div>;
}

function CalendarPage({ days, options, appointments, offset, onOffset, onBooking }: { days: Date[]; options: BookingOption[]; appointments: AppointmentRecord[]; offset: number; onOffset: (value: number) => void; onBooking: () => void }) { return <div className="page-stack"><section className="calendar-toolbar"><div><Title2>Weekly calendar</Title2><p>Asia/Kolkata · generated availability and confirmed patient bookings</p></div><div className="calendar-controls"><Button appearance="secondary" onClick={() => onOffset(offset - 1)}>Previous</Button><Button appearance="secondary" onClick={() => onOffset(0)}>Today</Button><Button appearance="secondary" onClick={() => onOffset(offset + 1)}>Next</Button><Button appearance="primary" icon={<AddRegular />} onClick={onBooking}>New booking</Button></div></section><section className="calendar-grid">{days.map((day) => { const key = dateKey(day); const sessions = options.filter((item) => dateKey(item.starts_at) === key); const bookings = appointments.filter((item) => dateKey(item.scheduled_at) === key && item.status === "CONFIRMED"); return <article className={key === dateKey(new Date()) ? "calendar-day today" : "calendar-day"} key={key}><header><span>{formatDay(day)}</span>{key === dateKey(new Date()) && <Badge appearance="tint" color="brand">Today</Badge>}</header><div className="calendar-events">{sessions.map((item) => <div className="calendar-session" key={item.id}><strong>{item.booking_mode === "EXACT_TIME" ? "Exact appointments" : "Token session"}</strong><span>{formatDateTime(item.starts_at).split(", ")[1]} · {item.doctor_name}</span><small>{item.booking_mode === "SESSION_TOKEN" ? `${item.occupied}/${item.max_patients} booked` : `${item.slots.length} slots open`}</small></div>)}{bookings.map((item) => <div className="calendar-booking" key={item.id}><strong>{item.patient_name}</strong><span>{item.token_number ? `Token ${item.token_number}` : formatDateTime(item.scheduled_at).split(", ")[1]}</span></div>)}{!sessions.length && !bookings.length && <p className="calendar-empty">No schedule</p>}</div></article>; })}</section></div>; }
function LegacyAppointmentsPage({ appointments, search, onSearch, onSubmit, onCancel, onReschedule, loading }: { appointments: AppointmentRecord[]; search: string; onSearch: (value: string) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void; onCancel: (appointment: AppointmentRecord) => void; onReschedule: (appointment: AppointmentRecord) => void; loading: boolean }) {
  const [doctorFilter, setDoctorFilter] = useState("");
  const doctors = Array.from(new Set(appointments.map((item) => item.doctor_name))).sort();
  const filtered = doctorFilter ? appointments.filter((item) => item.doctor_name === doctorFilter) : appointments;
  const confirmedCount = filtered.filter((item) => item.status === "CONFIRMED").length;
  return <div className="page-stack"><section className="list-toolbar"><div><Title2>Appointment list</Title2><p>{doctorFilter ? `${confirmedCount} confirmed appointment${confirmedCount === 1 ? "" : "s"} for ${doctorFilter}.` : "Search by reference, patient, caller, or mobile number."}</p></div><form onSubmit={onSubmit}><Select value={doctorFilter} onChange={(_, data) => setDoctorFilter(data.value)}><option value="">All doctors</option>{doctors.map((doctor) => <option key={doctor} value={doctor}>{doctor}</option>)}</Select><Input value={search} onChange={(_, data) => onSearch(data.value)} contentBefore={<SearchRegular />} placeholder="Search appointments"/><Button type="submit" appearance="primary" disabled={loading}>Search</Button></form></section><section className="appointment-table"><div className="table-head"><span>Patient</span><span>Schedule</span><span>Booking</span><span>Actions</span></div>{filtered.length ? filtered.map((item) => <article className="table-row" key={item.id}><div><strong>{item.patient_name}</strong><span>{item.phone_e164} · {item.booker_name}</span></div><div><strong>{formatDateTime(item.scheduled_at)}</strong><span>{item.doctor_name} · {item.location_name}{item.token_number ? ` · Token ${item.token_number}` : ""}</span></div><div><Badge appearance="tint" color={item.status === "CONFIRMED" ? "success" : "important"}>{item.status.replace("_", " ")}</Badge><span>{item.booking_reference}</span></div><div className="table-actions">{item.status === "CONFIRMED" && <><Button appearance="secondary" size="small" disabled={loading} onClick={() => onReschedule(item)}>Reschedule</Button><Button appearance="subtle" size="small" disabled={loading} onClick={() => onCancel(item)}>Cancel</Button></>}</div></article>) : <div className="empty-panel">No matching appointment records.</div>}</section></div>;
}
function LegacySettingsPage({ configuration }: { configuration: Configuration | null }) {
  const [departmentName, setDepartmentName] = useState("");
  const [doctorName, setDoctorName] = useState("");
  const [locationId, setLocationId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [assignmentId, setAssignmentId] = useState("");
  const [weekday, setWeekday] = useState("1");
  const [bookingMode, setBookingMode] = useState<"SESSION_TOKEN">("SESSION_TOKEN");
  const [saving, setSaving] = useState(false);
  const [setupMessage, setSetupMessage] = useState<string | null>(null);
  if (!configuration) return <div className="empty-panel">Loading clinic configuration…</div>;
  const organizationId = configuration.organization.id;
  const weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  async function save(path: string, payload: object) { const saved = await restoreSession(); if (!saved) throw new Error("Your session has expired. Sign in again."); const response = await fetch(`${apiBaseUrl}/v1/configuration/${path}?${new URLSearchParams({ organization_id: organizationId })}`, { method: "POST", headers: { Authorization: `Bearer ${saved.access_token}`, "Content-Type": "application/json" }, body: JSON.stringify(payload) }); if (!response.ok) { const failure = await response.json().catch(() => null); throw new Error(failure?.message ?? "The setup change could not be saved."); } }
  async function submitDepartment(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setSaving(true); setSetupMessage(null); try { await save("departments", { name: departmentName }); setDepartmentName(""); setSetupMessage("Department added. Refresh the page to see it in the new-doctor list."); } catch (error) { setSetupMessage(error instanceof Error ? error.message : "Could not add department."); } finally { setSaving(false); } }
  async function submitDoctor(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setSaving(true); setSetupMessage(null); try { await save("assignments", { doctor_name: doctorName, qualifications: [], location_id: locationId, department_id: departmentId, display_name: doctorName, fee_minor: 0, currency: "INR" }); setDoctorName(""); setSetupMessage("Doctor added. Refresh the page to configure the weekly schedule."); } catch (error) { setSetupMessage(error instanceof Error ? error.message : "Could not add doctor."); } finally { setSaving(false); } }
  async function submitSchedule(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setSaving(true); setSetupMessage(null); try { await save("schedule-rules", { assignment_id: assignmentId, weekday: Number(weekday), local_starts_at: "10:00", local_ends_at: "12:00", booking_mode: bookingMode, slot_minutes: null, max_patients: 30, effective_from: new Date().toISOString().slice(0, 10), effective_until: null, booking_cutoff_minutes: 30 }); setSetupMessage("Weekly availability added. Refresh the page to view it."); } catch (error) { setSetupMessage(error instanceof Error ? error.message : "Could not add the schedule."); } finally { setSaving(false); } }
  return <div className="settings-page">
    <section className="surface"><Text className="section-kicker">CLINIC PROFILE</Text><Title2>{configuration.organization.name}</Title2><div className="settings-grid"><Setting label="Organization type" value={configuration.organization.organization_type === "HOSPITAL" ? "Hospital" : "Clinic"} /><Setting label="Locations" value={`${configuration.locations.length} configured`} /><Setting label="Timezone" value={configuration.organization.timezone} /><Setting label="Departments" value={`${configuration.departments.length} configured`} /></div></section>
    <section className="surface"><Text className="section-kicker">DEPARTMENTS</Text><Title2>Clinical sections</Title2><div className="configuration-list">{configuration.departments.map((department) => <div key={department.id} className="configuration-row"><div><strong>{department.name}</strong><span>{department.active ? "Available for booking" : "Inactive"}</span></div><Badge appearance="tint" color={department.active ? "success" : "important"}>{department.active ? "Active" : "Paused"}</Badge></div>)}{!configuration.departments.length && <p className="muted-copy">No departments have been configured yet.</p>}</div></section>
    <section className="surface"><Text className="section-kicker">ADD CLINIC SETUP</Text><Title2>Departments, doctors, and weekly availability</Title2><div className="setup-forms"><form onSubmit={submitDepartment}><Input value={departmentName} onChange={(_, data) => setDepartmentName(data.value)} placeholder="Department name" required /><Button appearance="secondary" type="submit" disabled={saving}>Add department</Button></form><form onSubmit={submitDoctor}><Input value={doctorName} onChange={(_, data) => setDoctorName(data.value)} placeholder="Doctor name" required /><Select value={departmentId} onChange={(_, data) => setDepartmentId(data.value)} required><option value="">Department</option>{configuration.departments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</Select><Select value={locationId} onChange={(_, data) => setLocationId(data.value)} required><option value="">Location</option>{configuration.locations.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</Select><Button appearance="secondary" type="submit" disabled={saving || !locationId || !departmentId}>Add doctor</Button></form><form onSubmit={submitSchedule}><Select value={assignmentId} onChange={(_, data) => setAssignmentId(data.value)} required><option value="">Doctor</option>{configuration.assignments.map((item) => <option value={item.id} key={item.id}>{item.display_name}</option>)}</Select><Select value={weekday} onChange={(_, data) => setWeekday(data.value)}>{weekdays.map((day, index) => <option value={String(index)} key={day}>{day}</option>)}</Select><Select value={bookingMode} onChange={() => setBookingMode("SESSION_TOKEN")}><option value="SESSION_TOKEN">Availability window, capacity 30</option></Select><Button appearance="primary" type="submit" disabled={saving || !assignmentId}>Add weekly availability</Button></form></div>{setupMessage && <p className="setup-message">{setupMessage}</p>}</section>
    <section className="surface"><Text className="section-kicker">DOCTORS AND AVAILABILITY</Text><Title2>Weekly schedules</Title2><div className="configuration-list">{configuration.assignments.map((assignment) => { const rules = configuration.schedule_rules.filter((rule) => rule.assignment_id === assignment.id); return <div key={assignment.id} className="doctor-schedule"><div className="configuration-row"><div><strong>{assignment.display_name}</strong><span>{assignment.department_name} · {assignment.location_name} · {assignment.currency} {assignment.fee_minor}</span></div><Badge appearance="tint" color={assignment.active ? "success" : "important"}>{assignment.active ? "Available" : "Paused"}</Badge></div><div className="schedule-rule-list">{rules.map((rule) => <span key={rule.id}>{weekdays[rule.weekday]} · {String(rule.local_starts_at).slice(0, 5)}–{String(rule.local_ends_at).slice(0, 5)} · {rule.booking_mode === "SESSION_TOKEN" ? `Token capacity ${rule.max_patients}` : `${rule.slot_minutes}-minute slots`}</span>)}{!rules.length && <span>No weekly availability configured.</span>}</div></div>; })}{!configuration.assignments.length && <p className="muted-copy">Add a doctor assignment to begin configuring availability.</p>}</div></section>
  </div>;
}
function Setting({ label, value }: { label: string; value: string }) { return <div className="setting"><span>{label}</span><strong>{value}</strong></div>; }
function pageTitle(page: Page) { return ({ overview: "Overview", calendar: "Availability", appointments: "Appointments", patients: "Patients", booking: "New appointment", assistant: "AI assistant", presentation: "Inside the call", calls: "Voice call history", departments: "Departments", doctors: "Doctors", settings: "Clinic settings" } as Record<Page, string>)[page]; }
