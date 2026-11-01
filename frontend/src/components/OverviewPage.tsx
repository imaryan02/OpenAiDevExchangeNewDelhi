import { useState } from 'react';
import { Badge, Button } from '@fluentui/react-components';
import { authenticatedFetch, type AuthSession } from '../lib/supabaseAuth';
import {
  AddRegular,
  ArrowRightRegular,
  CalendarClockRegular,
  CalendarMonthRegular,
  CheckmarkCircleRegular,
  ClockRegular,
  PeopleRegular,
  PhoneRegular,
  WarningRegular,
} from '@fluentui/react-icons';

type AppointmentRecord = {
  id: string;
  booking_reference: string;
  status: string;
  queue_status: string | null;
  token_number: number | null;
  patient_name: string;
  booker_name: string;
  scheduled_at: string;
  doctor_name: string;
  department_name: string;
  location_name: string;
  source: string;
};

type BookingOption = {
  id: string;
  booking_mode: 'EXACT_TIME' | 'SESSION_TOKEN';
  starts_at: string;
  ends_at: string;
  max_patients: number | null;
  occupied: number;
  doctor_name: string;
  location_name: string;
  slots: { id: string }[];
};

type OverviewTarget = 'calendar' | 'appointments' | 'booking';

type OverviewPageProps = {
  session: AuthSession;
  appointments: AppointmentRecord[];
  options: BookingOption[];
  clinicName: string;
  locationName: string;
  onPage: (page: OverviewTarget) => void;
};

const dateKey = (value: string | Date) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date(value));
const formatTime = (value: string) => new Intl.DateTimeFormat('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: 'Asia/Kolkata' }).format(new Date(value));
const formatDate = (value: string | Date) => new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'Asia/Kolkata' }).format(new Date(value));
const formatShortDate = (value: string) => new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' }).format(new Date(value));
const normalizedSource = (source: string) => source.toUpperCase().includes('VOICE') || source.toUpperCase().includes('AI') ? 'Voice AI' : 'Reception';

function openPlaces(option: BookingOption) {
  return option.booking_mode === 'SESSION_TOKEN'
    ? Math.max(0, (option.max_patients ?? 0) - option.occupied)
    : option.slots.length;
}

function relativeArrival(value: string, now: number) {
  const minutes = Math.round((new Date(value).getTime() - now) / 60000);
  if (minutes < -15) return 'Earlier';
  if (minutes <= 15 && minutes >= -15) return 'Due now';
  if (minutes < 60) return `In ${minutes} min`;
  return formatTime(value);
}

export function OverviewPage({ session, appointments, options, clinicName, locationName, onPage }: OverviewPageProps) {
  const [calling, setCalling] = useState(false);
  const [callStatus, setCallStatus] = useState('');
  async function callReceptionist() {
    if (calling) return;
    setCalling(true);
    setCallStatus('');
    try {
      const base = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');
      const response = await authenticatedFetch(`${base}/v1/twilio/test-call`, session, { method: 'POST' });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof result?.message === 'string' ? result.message : 'Could not start the call.');
      setCallStatus('Twilio accepted the call. Your registered phone should ring shortly.');
    } catch (error) {
      setCallStatus(error instanceof Error ? error.message : 'Could not start the call.');
    } finally {
      setCalling(false);
    }
  }
  const now = Date.now();
  const todayKey = dateKey(new Date(now));
  const confirmed = appointments
    .filter((item) => ['CONFIRMED', 'COMPLETED'].includes(item.status))
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime());
  const today = confirmed.filter((item) => dateKey(item.scheduled_at) === todayKey);
  const remainingToday = today.filter((item) => item.status === 'CONFIRMED' && new Date(item.scheduled_at).getTime() >= now - 15 * 60000);
  const upcoming = confirmed.filter((item) => item.status === 'CONFIRMED' && new Date(item.scheduled_at).getTime() >= now);
  const next = upcoming[0] ?? null;
  const todayOptions = options.filter((item) => dateKey(item.starts_at) === todayKey);
  const availableToday = todayOptions.reduce((sum, option) => sum + openPlaces(option), 0);
  const checkedIn = today.filter((item) => ['ARRIVED', 'WAITING', 'CHECKED_IN'].includes((item.queue_status ?? '').toUpperCase())).length;
  const completed = appointments.filter((item) => item.status === 'COMPLETED' && dateKey(item.scheduled_at) === todayKey).length;
  const needsReview = appointments.filter((item) => item.status.toUpperCase() === 'PAYMENT_PENDING');
  const voiceBookings = upcoming.filter((item) => normalizedSource(item.source) === 'Voice AI').length;
  const receptionBookings = upcoming.length - voiceBookings;

  const doctorCapacity = Array.from(todayOptions.reduce((map, option) => {
    const current = map.get(option.doctor_name) ?? { doctor: option.doctor_name, location: option.location_name, sessions: 0, open: 0, startsAt: option.starts_at, endsAt: option.ends_at };
    current.sessions += 1;
    current.open += openPlaces(option);
    if (new Date(option.starts_at) < new Date(current.startsAt)) current.startsAt = option.starts_at;
    if (new Date(option.ends_at) > new Date(current.endsAt)) current.endsAt = option.ends_at;
    map.set(option.doctor_name, current);
    return map;
  }, new Map<string, { doctor: string; location: string; sessions: number; open: number; startsAt: string; endsAt: string }>()).values())
    .sort((a, b) => a.doctor.localeCompare(b.doctor));

  const brief = remainingToday.length
    ? `${remainingToday.length} confirmed visit${remainingToday.length === 1 ? '' : 's'} still ahead today.`
    : today.length
      ? 'Today’s confirmed schedule is complete.'
      : 'No confirmed visits are scheduled today.';

  return <div className="overview-page">
    <section className="operations-brief" aria-labelledby="operations-title">
      <div className="brief-copy">
        <span className="brief-date">{formatDate(new Date(now))}</span>
        <h2 id="operations-title">{brief}</h2>
        <p>{clinicName}{locationName ? `, ${locationName}` : ''} · Live records refresh automatically.</p>
        <div className="brief-actions">
          <Button appearance="primary" icon={<CalendarMonthRegular />} onClick={() => onPage('calendar')}>Open today’s calendar</Button>
          <Button appearance="secondary" icon={<AddRegular />} onClick={() => onPage('booking')}>Add appointment</Button>
          <Button appearance="secondary" icon={<PhoneRegular />} disabled={calling} onClick={() => void callReceptionist()}>{calling ? 'Calling…' : 'Call me with AI receptionist'}</Button>
        </div>
        {callStatus && <p role="status">{callStatus}</p>}
      </div>
      <div className="next-arrival" aria-label="Next confirmed appointment">
        <span><CalendarClockRegular /> Next confirmed</span>
        {next ? <>
          <strong>{next.patient_name}</strong>
          <p>{formatShortDate(next.scheduled_at)} · {formatTime(next.scheduled_at)}</p>
          <small>{next.doctor_name} · {next.department_name || next.location_name}</small>
          <Button appearance="subtle" size="small" icon={<ArrowRightRegular />} iconPosition="after" onClick={() => onPage('appointments')}>Open record</Button>
        </> : <>
          <strong>Schedule clear</strong>
          <p>No future confirmed appointment was found.</p>
        </>}
      </div>
    </section>

    <section className="operations-metrics" aria-label="Today’s operational summary">
      <Metric icon={<PeopleRegular />} label="Scheduled today" value={String(today.length)} detail={`${remainingToday.length} still ahead`} tone="blue" />
      <Metric icon={<ClockRegular />} label="Checked in" value={String(checkedIn)} detail={`${completed} completed`} tone="teal" />
      <Metric icon={<CalendarClockRegular />} label="Places open today" value={String(availableToday)} detail={`${todayOptions.length} active schedule${todayOptions.length === 1 ? '' : 's'}`} tone="violet" />
      <Metric icon={needsReview.length ? <WarningRegular /> : <CheckmarkCircleRegular />} label="Needs review" value={String(needsReview.length)} detail={needsReview.length ? 'Open holds or pending records' : 'No open holds'} tone={needsReview.length ? 'amber' : 'green'} />
    </section>

    <div className="overview-primary-grid">
      <section className="overview-panel patient-flow" aria-labelledby="patient-flow-title">
        <header className="panel-heading">
          <div><h3 id="patient-flow-title">Today’s patient flow</h3><p>Confirmed visits in arrival order</p></div>
          <Button appearance="subtle" size="small" onClick={() => onPage('appointments')}>View all records</Button>
        </header>
        {today.length ? <div className="patient-flow-list">
          {today.slice(0, 6).map((appointment) => {
            const timing = relativeArrival(appointment.scheduled_at, now);
            const isCurrent = timing === 'Due now';
            return <article className={`patient-flow-row${isCurrent ? ' current' : ''}`} key={appointment.id}>
              <time dateTime={appointment.scheduled_at}>{formatTime(appointment.scheduled_at)}</time>
              <span className="flow-marker" aria-hidden="true" />
              <div className="flow-patient"><strong>{appointment.patient_name}</strong><span>{appointment.doctor_name} · {appointment.department_name || appointment.location_name}</span></div>
              <div className="flow-meta"><Badge appearance="tint" color={isCurrent ? 'brand' : 'informative'}>{timing}</Badge><small>{appointment.token_number ? `Token ${appointment.token_number}` : normalizedSource(appointment.source)}</small></div>
            </article>;
          })}
          {today.length > 6 && <button className="inline-disclosure" onClick={() => onPage('appointments')}>Show {today.length - 6} more visits <ArrowRightRegular /></button>}
        </div> : <div className="overview-empty"><CalendarMonthRegular /><div><strong>The day is open</strong><p>Add a booking or review availability before the next call.</p></div><Button appearance="secondary" size="small" onClick={() => onPage('booking')}>New booking</Button></div>}
      </section>

      <section className="overview-panel capacity-panel" aria-labelledby="capacity-title">
        <header className="panel-heading"><div><h3 id="capacity-title">Today’s clinical capacity</h3><p>Bookable places by clinician</p></div><span className="panel-total">{availableToday} open</span></header>
        {doctorCapacity.length ? <div className="capacity-list">{doctorCapacity.map((item) => <article className="capacity-row" key={item.doctor}>
          <div className="capacity-avatar" aria-hidden="true">{item.doctor.replace(/^Dr\.?\s*/i, '').slice(0, 2).toUpperCase()}</div>
          <div><strong>{item.doctor}</strong><span>{formatTime(item.startsAt)} to {formatTime(item.endsAt)} · {item.location}</span></div>
          <div className="capacity-value"><strong>{item.open}</strong><span>places</span></div>
        </article>)}</div> : <div className="overview-empty compact"><CalendarClockRegular /><div><strong>No schedule today</strong><p>Open Availability to configure clinical capacity.</p></div></div>}
        <Button className="panel-action" appearance="secondary" onClick={() => onPage('calendar')}>Review availability</Button>
      </section>
    </div>

    <div className="overview-secondary-grid">
      <section className="overview-panel upcoming-panel" aria-labelledby="upcoming-title">
        <header className="panel-heading"><div><h3 id="upcoming-title">Coming up</h3><p>The next confirmed visits after now</p></div></header>
        {upcoming.length ? <div className="upcoming-list">{upcoming.slice(0, 4).map((appointment) => <article key={appointment.id}>
          <div className="upcoming-date"><strong>{formatShortDate(appointment.scheduled_at)}</strong><span>{formatTime(appointment.scheduled_at)}</span></div>
          <div><strong>{appointment.patient_name}</strong><span>{appointment.doctor_name}</span></div>
          <small>{appointment.token_number ? `Token ${appointment.token_number}` : appointment.booking_reference}</small>
        </article>)}</div> : <p className="panel-empty-copy">No future confirmed visits yet.</p>}
      </section>

      <section className="overview-panel channel-panel" aria-labelledby="channel-title">
        <header className="panel-heading"><div><h3 id="channel-title">Booking channels</h3><p>Source of future confirmed appointments</p></div></header>
        <div className="channel-split">
          <div><span className="channel-icon voice"><PhoneRegular /></span><strong>{voiceBookings}</strong><span>Voice AI</span></div>
          <div><span className="channel-icon staff"><PeopleRegular /></span><strong>{receptionBookings}</strong><span>Reception</span></div>
        </div>
        <p className="channel-note">{upcoming.length ? `${Math.round((voiceBookings / upcoming.length) * 100)}% of upcoming bookings were assisted by voice.` : 'Channel activity will appear after the first confirmed booking.'}</p>
      </section>

      <section className={`overview-panel attention-panel${needsReview.length ? ' has-attention' : ''}`} aria-labelledby="attention-title">
        <header className="panel-heading"><div><h3 id="attention-title">Reception attention</h3><p>Records that may need a decision</p></div></header>
        {needsReview.length ? <>
          <div className="attention-count"><WarningRegular /><div><strong>{needsReview.length} open record{needsReview.length === 1 ? '' : 's'}</strong><span>Review holds before offering those places again.</span></div></div>
          <Button appearance="secondary" onClick={() => onPage('appointments')}>Review records</Button>
        </> : <div className="attention-clear"><CheckmarkCircleRegular /><div><strong>No immediate follow-up</strong><span>Confirmed schedules and open holds are clear.</span></div></div>}
      </section>
    </div>
  </div>;
}

function Metric({ icon, label, value, detail, tone }: { icon: React.ReactNode; label: string; value: string; detail: string; tone: 'blue' | 'teal' | 'violet' | 'amber' | 'green' }) {
  return <article className={`operations-metric ${tone}`}><span className="metric-icon">{icon}</span><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></article>;
}
