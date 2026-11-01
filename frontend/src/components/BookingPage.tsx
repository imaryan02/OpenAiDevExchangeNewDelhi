import { FormEvent, useMemo, useState } from "react";
import { Badge, Button, Input, Select } from "@fluentui/react-components";
import { CalendarMonthRegular, CheckmarkCircleRegular, ClockRegular, PeopleRegular, PersonRegular } from "@fluentui/react-icons";

type BookingSlot = { id: string; starts_at: string; ends_at: string };
type BookingOption = {
  id: string;
  assignment_id: string;
  booking_mode: "EXACT_TIME" | "SESSION_TOKEN";
  starts_at: string;
  ends_at: string;
  max_patients: number | null;
  occupied: number;
  doctor_name: string;
  location_name: string;
  slots: BookingSlot[];
};

type BookingPageProps = {
  options: BookingOption[];
  selectedSession: BookingOption | null;
  selectedSessionId: string;
  selectedSlotId: string;
  onSession: (id: string) => void;
  onSlot: (id: string) => void;
  bookerName: string;
  phone: string;
  patientName: string;
  relationship: string;
  paymentMethod: "CASH" | "UPI" | "CARD";
  onBooker: (value: string) => void;
  onPhone: (value: string) => void;
  onPatient: (value: string) => void;
  onRelationship: (value: string) => void;
  onPaymentMethod: (value: "CASH" | "UPI" | "CARD") => void;
  onBooking: (event: FormEvent<HTMLFormElement>) => void;
  loading: boolean;
};

const dateKey = (value: string) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(value));
const formatDate = (value: string) => new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Kolkata" }).format(new Date(value));
const formatTime = (value: string) => new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(new Date(value));

export function BookingPage(props: BookingPageProps) {
  const [doctor, setDoctor] = useState("");
  const [date, setDate] = useState("");
  const doctors = useMemo(() => Array.from(new Set(props.options.map((item) => item.doctor_name))).sort(), [props.options]);
  const visibleOptions = props.options.filter((item) => (!doctor || item.doctor_name === doctor) && (!date || dateKey(item.starts_at) === date));
  const remaining = props.selectedSession?.booking_mode === "SESSION_TOKEN"
    ? Math.max(0, (props.selectedSession.max_patients ?? 0) - props.selectedSession.occupied)
    : props.selectedSession?.slots.length ?? 0;

  return <div className="booking-workspace">
    <div className="booking-progress" aria-label="Booking progress">
      <div className="complete"><span><CheckmarkCircleRegular /></span><div><strong>Choose availability</strong><small>Doctor and session</small></div></div>
      <i />
      <div className={props.selectedSession ? "current" : ""}><span>2</span><div><strong>Patient details</strong><small>Caller and patient</small></div></div>
      <i />
      <div><span>3</span><div><strong>Confirmation</strong><small>Review and book</small></div></div>
    </div>

    <div className="booking-layout">
      <section className="booking-availability-panel">
        <header><div><span className="booking-step-label">Step 1</span><h2>Choose an appointment</h2><p>Select a doctor session from the next 14 days.</p></div><Badge appearance="tint" color="success">{props.options.length} sessions</Badge></header>
        <div className="booking-filters">
          <Select aria-label="Filter doctor" value={doctor} onChange={(_, data) => setDoctor(data.value)}><option value="">All doctors</option>{doctors.map((name) => <option value={name} key={name}>{name}</option>)}</Select>
          <Input aria-label="Filter date" type="date" value={date} onChange={(_, data) => setDate(data.value)} />
          {(doctor || date) && <Button appearance="subtle" onClick={() => { setDoctor(""); setDate(""); }}>Clear</Button>}
        </div>
        <div className="booking-session-list">
          {visibleOptions.map((session) => {
            const active = session.id === props.selectedSessionId;
            const sessionRemaining = session.booking_mode === "SESSION_TOKEN" ? Math.max(0, (session.max_patients ?? 0) - session.occupied) : session.slots.length;
            return <button className={active ? "booking-session selected" : "booking-session"} type="button" key={session.id} onClick={() => props.onSession(session.id)}>
              <div className="session-date"><strong>{formatDate(session.starts_at)}</strong><span>{formatTime(session.starts_at)}–{formatTime(session.ends_at)}</span></div>
              <div className="session-doctor"><span className="session-avatar">{session.doctor_name.replace(/^Dr\.?\s*/i, "").charAt(0).toUpperCase()}</span><div><strong>{session.doctor_name}</strong><span>{session.location_name}</span></div></div>
              <div className="session-availability"><Badge appearance="tint" color={sessionRemaining ? "success" : "important"}>Available window</Badge><span>{sessionRemaining} places left</span></div>
              <span className="session-radio">{active && <CheckmarkCircleRegular />}</span>
            </button>;
          })}
          {!visibleOptions.length && <div className="booking-empty"><CalendarMonthRegular /><strong>No availability found</strong><span>Try another date or doctor.</span></div>}
        </div>
      </section>

      <section className="booking-details-panel">
        <header><span className="booking-step-label">Step 2</span><h2>Patient and caller</h2><p>Keep the caller separate when they book for a family member.</p></header>
        {props.selectedSession ? <div className="selected-booking-summary">
          <div><CalendarMonthRegular /><span><small>Appointment window</small><strong>{formatDate(props.selectedSession.starts_at)}, {formatTime(props.selectedSession.starts_at)}–{formatTime(props.selectedSession.ends_at)}</strong></span></div>
          <div><PersonRegular /><span><small>Doctor</small><strong>{props.selectedSession.doctor_name}</strong></span></div>
          <div><ClockRegular /><span><small>Availability</small><strong>{remaining} places left</strong></span></div>
        </div> : <div className="select-session-prompt"><CalendarMonthRegular /><span>Select a session to continue</span></div>}

        <form className="guided-booking-form" onSubmit={props.onBooking}>
          <fieldset>
            <legend><PeopleRegular /> Caller details</legend>
            <div className="booking-field-grid"><label>Caller / booker name<Input value={props.bookerName} onChange={(_, data) => props.onBooker(data.value)} placeholder="e.g. Aryan Gupta" required /></label><label>Mobile number<Input value={props.phone} onChange={(_, data) => props.onPhone(data.value)} placeholder="+91 98…" required /></label></div>
          </fieldset>
          <fieldset>
            <legend><PersonRegular /> Patient details</legend>
            <div className="booking-field-grid"><label>Patient name<Input value={props.patientName} onChange={(_, data) => props.onPatient(data.value)} placeholder="Who is the appointment for?" required /></label><label>Relationship to caller<Select value={props.relationship} onChange={(_, data) => props.onRelationship(data.value)}><option value="SELF">Self</option><option value="MOTHER">Mother</option><option value="FATHER">Father</option><option value="SPOUSE">Spouse</option><option value="CHILD">Child</option><option value="OTHER">Other</option></Select></label></div>
          </fieldset>
          <fieldset>
            <legend>Payment method</legend>
            <div className="payment-method-grid">
              {([
                ["CASH", "Cash", "Pay at clinic"],
                ["UPI", "UPI", "Simulated payment"],
                ["CARD", "Card", "Simulated payment"],
              ] as const).map(([value, label, note]) => <button className={props.paymentMethod === value ? "selected" : ""} type="button" key={value} onClick={() => props.onPaymentMethod(value)}><span className="payment-choice-mark">{props.paymentMethod === value && <CheckmarkCircleRegular />}</span><strong>{label}</strong><small>{note}</small></button>)}
            </div>
          </fieldset>
          <div className="booking-confirmation"><div><strong>Ready to confirm</strong><span>{props.paymentMethod === "CASH" ? "Payment will be collected at the clinic." : `${props.paymentMethod} will be recorded as a simulated payment.`}</span></div><Button appearance="primary" size="large" type="submit" disabled={props.loading || !props.selectedSession}>{props.loading ? "Confirming…" : "Confirm appointment"}</Button></div>
        </form>
      </section>
    </div>
  </div>;
}
