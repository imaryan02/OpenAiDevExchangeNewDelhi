import { useMemo, useState } from "react";
import { Badge, Button } from "@fluentui/react-components";
import { AddRegular, CalendarMonthRegular, PeopleTeamRegular } from "@fluentui/react-icons";

import type { Configuration } from "./AdminSettingsPage";

type Slot = { id: string; starts_at: string; ends_at: string };
type Option = { id: string; assignment_id: string; booking_mode: "EXACT_TIME" | "SESSION_TOKEN"; starts_at: string; ends_at: string; max_patients: number | null; occupied: number; doctor_name: string; location_name: string; slots: Slot[] };
type Appointment = { id: string; status: string; assignment_id: string; scheduled_at: string; patient_name: string; token_number: number | null };

const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const dateKey = (value: string | Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date(value));
const formatDay = (value: Date) => new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Kolkata" }).format(value);
const formatTime = (value: string) => new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(new Date(value));
const formatDateTime = (value: string) => new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(value));

export function AvailabilityPage({ days, options, appointments, configuration, offset, onOffset, onBooking }: { days: Date[]; options: Option[]; appointments: Appointment[]; configuration: Configuration | null; offset: number; onOffset: (value: number) => void; onBooking: () => void }) {
  const [view, setView] = useState<"doctors" | "week">("doctors");
  const today = dateKey(new Date());
  const confirmed = appointments.filter((item) => item.status === "CONFIRMED");
  const departments = useMemo(() => configuration?.departments.filter((item) => item.active) ?? [], [configuration]);

  return <div className="page-stack availability-page">
    <section className="availability-toolbar">
      <div><h2>Doctor availability</h2><p>See who is available, their capacity, and today’s patient load.</p></div>
      <div className="availability-actions"><div className="view-switch"><button className={view === "doctors" ? "active" : ""} onClick={() => setView("doctors")}><PeopleTeamRegular /> Doctors</button><button className={view === "week" ? "active" : ""} onClick={() => setView("week")}><CalendarMonthRegular /> Week</button></div><Button appearance="primary" icon={<AddRegular />} onClick={onBooking}>New booking</Button></div>
    </section>

    {view === "doctors" && <div className="department-availability">
      {departments.map((department) => {
        const doctors = configuration?.assignments.filter((doctor) => doctor.department_id === department.id) ?? [];
        if (!doctors.length) return null;
        return <section className="availability-group" key={department.id}>
          <div className="availability-group-heading"><div><h3>{department.name}</h3><span>{doctors.length} {doctors.length === 1 ? "doctor" : "doctors"}</span></div></div>
          <div className="doctor-tile-grid">{doctors.map((doctor) => {
            const doctorOptions = options.filter((option) => option.assignment_id === doctor.id);
            const todayOptions = doctorOptions.filter((option) => dateKey(option.starts_at) === today);
            const todayBookings = confirmed.filter((item) => item.assignment_id === doctor.id && dateKey(item.scheduled_at) === today).length;
            const next = doctorOptions[0];
            const rules = configuration?.schedule_rules.filter((rule) => rule.assignment_id === doctor.id && rule.active) ?? [];
            return <article className={`availability-doctor-card ${doctor.active ? "" : "paused"}`} key={doctor.id}>
              <header><div className="availability-avatar">{doctor.display_name.replace(/^Dr\.?\s*/i, "").charAt(0).toUpperCase()}</div><div><strong>{doctor.display_name}</strong><span>{doctor.location_name}</span></div><Badge appearance="tint" color={doctor.active ? "success" : "important"}>{doctor.active ? (todayOptions.length ? "Available today" : "Active") : "Paused"}</Badge></header>
              <div className="doctor-load"><div><strong>{todayBookings}</strong><span>Today’s bookings</span></div><div><strong>{todayOptions.reduce((sum, item) => sum + (item.booking_mode === "SESSION_TOKEN" ? (item.max_patients ?? 0) : item.slots.length + item.occupied), 0)}</strong><span>Today’s capacity</span></div></div>
              <div className="next-session"><span>Next availability</span><strong>{next ? `${formatDateTime(next.starts_at)}–${formatTime(next.ends_at)}` : "No upcoming session"}</strong>{next && <small>{next.booking_mode === "SESSION_TOKEN" ? `${next.occupied}/${next.max_patients} booked` : `${next.slots.length} places available`}</small>}</div>
              <div className="mini-week">{weekdays.map((day, index) => <div className={rules.some((rule) => rule.weekday === index) ? "open" : "closed"} key={day}><span>{day}</span><i /></div>)}</div>
              <Button appearance="secondary" onClick={onBooking} disabled={!doctor.active || !next}>Book appointment</Button>
            </article>;
          })}</div>
        </section>;
      })}
      {!configuration?.assignments.length && <div className="empty-panel surface">Add doctors and weekly schedules to see availability here.</div>}
    </div>}

    {view === "week" && <>
      <section className="week-navigation"><div><strong>Weekly schedule</strong><span>Generated sessions and confirmed patients</span></div><div><Button onClick={() => onOffset(offset - 1)}>Previous</Button><Button onClick={() => onOffset(0)}>Today</Button><Button onClick={() => onOffset(offset + 1)}>Next</Button></div></section>
      <section className="operations-calendar">{days.map((day) => {
        const key = dateKey(day);
        const sessions = options.filter((item) => dateKey(item.starts_at) === key);
        const bookings = confirmed.filter((item) => dateKey(item.scheduled_at) === key);
        return <article className={key === today ? "operations-day today" : "operations-day"} key={key}>
          <header><strong>{formatDay(day)}</strong>{key === today && <Badge appearance="tint" color="brand">Today</Badge>}</header>
          <div className="day-counts"><span>{sessions.length} sessions</span><span>{bookings.length} bookings</span></div>
          <div className="day-sessions">{sessions.map((item) => <div className="session-block" key={item.id}><span>{formatTime(item.starts_at)}–{formatTime(item.ends_at)}</span><strong>{item.doctor_name}</strong><small>{item.booking_mode === "SESSION_TOKEN" ? `${item.occupied}/${item.max_patients} booked` : `${item.slots.length} places open`}</small></div>)}{!sessions.length && <div className="closed-day">No availability</div>}</div>
        </article>;
      })}</section>
    </>}
  </div>;
}
