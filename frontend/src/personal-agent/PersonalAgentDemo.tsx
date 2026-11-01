import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { clearStoredSession, restoreSession, signInWithPassword, type AuthSession } from "../lib/supabaseAuth";
import { PersonalApiError, personalRequest } from "./api";
import { activeFollowups, countdown } from "./state";
import type { Activity, Followup, Memory, Profile, Readiness, Snapshot, Task } from "./types";
import "./styles.css";

const errorText = (error: unknown) => error instanceof Error ? error.message : "Something went wrong.";
const clock = (time: string, timezone = "Asia/Kolkata") => new Intl.DateTimeFormat("en-IN", {
  hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: timezone,
}).format(new Date(time));

export default function PersonalAgentDemo() {
  useEffect(() => {
    const previous = document.title;
    document.title = "Friday · Personal AI";
    return () => { document.title = previous; };
  }, []);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [needProfile, setNeedProfile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [freshAt, setFreshAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const [activeSection, setActiveSection] = useState("pa-today");
  const serverOffset = useRef(0);
  const loading = useRef(false);
  const requestEpoch = useRef(0);

  useEffect(() => {
    let stopped = false;
    restoreSession().then(saved => { if (!stopped) setSession(saved); })
      .catch(caught => { if (!stopped) setError(errorText(caught)); })
      .finally(() => { if (!stopped) setRestoring(false); });
    return () => { stopped = true; };
  }, []);

  const refresh = useCallback(async () => {
    if (!session || loading.current) return;
    loading.current = true;
    const epoch = requestEpoch.current;
    try {
      const ready = await personalRequest<Readiness>(session, "/readiness");
      if (epoch !== requestEpoch.current) return;
      setReadiness(ready);
      if (!ready.enabled || !ready.owner_configured) return;
      const next = await personalRequest<Snapshot>(session, "/snapshot");
      if (epoch !== requestEpoch.current) return;
      serverOffset.current = Date.parse(next.server_time) - Date.now();
      setSnapshot(next); setNeedProfile(false); setFreshAt(Date.now()); setError("");
    } catch (caught) {
      if (epoch !== requestEpoch.current) return;
      if (caught instanceof PersonalApiError && caught.code === "PERSONAL_PROFILE_REQUIRED") setNeedProfile(true);
      else setError(errorText(caught));
    } finally { if (epoch === requestEpoch.current) loading.current = false; }
  }, [session]);

  useEffect(() => {
    if (!session) return;
    void refresh();
    const poll = setInterval(() => { if (!document.hidden) void refresh(); }, 2000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const focus = () => void refresh();
    window.addEventListener("focus", focus);
    return () => { clearInterval(poll); clearInterval(tick); window.removeEventListener("focus", focus); };
  }, [session, refresh]);

  async function mutate(path: string, method: string, body?: unknown, success = "Saved") {
    if (!session || busy) return false;
    setBusy(true); setError(""); setNotice("");
    const epoch = requestEpoch.current;
    try {
      await personalRequest(session, path, method, body);
      if (epoch !== requestEpoch.current) return false;
      setNotice(success);
      // Ignore any poll that began before this mutation committed.
      requestEpoch.current += 1;
      loading.current = false;
      await refresh();
      return true;
    } catch (caught) { if (epoch === requestEpoch.current) setError(errorText(caught)); return false; }
    finally { setBusy(false); }
  }

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const saved = await signInWithPassword(email, password); setSession(saved); setPassword(""); }
    catch (caught) { setError(errorText(caught)); }
    finally { setBusy(false); }
  }

  function logout() {
    requestEpoch.current += 1; loading.current = false;
    clearStoredSession(); setSession(null); setSnapshot(null); setReadiness(null);
    setError(""); setNotice(""); setFreshAt(null); setNeedProfile(false);
  }

  const header = <header className="pa-header"><a className="pa-brand" href="/demo/personal-agent"><span className="pa-monogram">F</span><span>Friday<small>Personal AI workspace</small></span></a><nav aria-label="Workspace"><a href="/">Receptionist</a>{session && <button className="pa-button pa-subtle" onClick={logout}>Sign out</button>}</nav></header>;
  if (restoring) return <div className="pa-root">{header}<main className="pa-loading" aria-busy="true">Restoring your workspace…</main></div>;
  if (!session) return <div className="pa-root">{header}<main className="pa-login"><div><h1>A little continuity<br />for a busy day.</h1><p>Your tasks, recent conversations and unfinished work, together in one personal workspace.</p></div><form onSubmit={login}><h2>Sign in</h2><p>Use your existing application account.</p><label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>{error && <p role="alert" className="pa-error">{error}</p>}<button className="pa-button pa-primary" disabled={busy}>{busy ? "Signing in…" : "Open personal workspace"}</button></form></main></div>;

  const personal = snapshot?.profile.mode === "personal_agent";
  const followups = activeFollowups(snapshot?.followups ?? []);
  const latestMessage = snapshot?.messages[0];
  const canConfigure = readiness?.enabled && readiness.owner_configured;
  const pendingTasks = snapshot?.tasks.filter(task => task.status === "pending").length ?? 0;
  const dateLabel = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long", timeZone: snapshot?.profile.timezone ?? "Asia/Kolkata" }).format(new Date(now));
  const callbackReady = Boolean(readiness?.callback_implemented && readiness.scheduler_enabled && readiness.outbound_enabled && readiness.callback_configured);
  return <div className="pa-root">{header}<div className="pa-shell"><aside className="pa-rail" aria-label="Friday navigation"><div className="pa-rail-title">PERSONAL SPACE</div><nav>{[{ id: "pa-today", label: "Today" }, { id: "pa-tasks", label: "Tasks", count: pendingTasks }, { id: "pa-followups", label: "Follow-ups", count: followups.length }, { id: "pa-activity", label: "Activity" }, { id: "pa-settings", label: "Preferences" }].map(item => <a key={item.id} href={`#${item.id}`} aria-current={activeSection === item.id ? "location" : undefined} onClick={() => { setActiveSection(item.id); if (item.id === "pa-settings") openDetails("pa-settings"); }}><span className="pa-nav-label"><WorkspaceIcon kind={item.id} />{item.label}</span>{item.count !== undefined && <span>{item.count}</span>}</a>)}</nav><div className="pa-rail-note"><span className="pa-rail-avatar"><FridayMark /></span><strong>More headspace.<br />Less keeping track.</strong><p>Your day, with a little help from Friday.</p></div></aside><main className="pa-main" id="pa-today">
    <section className="pa-heading"><div><p className="pa-date">{dateLabel}</p><h1>A little more<br /><em>headspace.</em></h1><p>{pendingTasks ? `${pendingTasks} task${pendingTasks === 1 ? "" : "s"} on your list. Let’s take the day one thing at a time.` : "A clear list. Add something you’d like Friday to remember."}</p></div><div className="pa-connection"><span className={`pa-dot ${freshAt && now - freshAt < 10000 ? "pa-good" : ""}`} /><span>{freshAt ? now - freshAt < 10000 ? "Updates connected" : "Updates delayed" : error ? "Connection unavailable" : "Connecting"}</span><button className="pa-button pa-subtle" onClick={() => void refresh()} disabled={busy}>Refresh</button></div></section>
    {error && <div className="pa-error pa-banner" role="alert">{error}<button className="pa-button pa-subtle" onClick={() => setError("")}>Dismiss</button></div>}
    {notice && <p className="pa-notice" role="status">{notice}</p>}
    {readiness && (!readiness.enabled || !readiness.owner_configured) && <section className="pa-setup"><h2>Connect your personal workspace</h2><p>Your login is ready. The backend needs the Personal AI feature enabled and your user ID assigned as its demo owner.</p><p>User ID: <code>{readiness.current_user_id}</code></p><p className="pa-muted">Setup instructions are in the module runbook. Receptionist calls continue as usual.</p></section>}
    {canConfigure && <>
      <section className="pa-mode"><span className="pa-mode-icon"><WorkspaceIcon kind="pa-followups" /></span><div><h2>Your next call</h2><p>Choose who answers calls from your registered number.</p></div><div className="pa-mode-buttons" role="group" aria-label="Agent mode"><button className="pa-button" aria-pressed={!personal} disabled={busy || !snapshot} onClick={() => void mutate("/mode", "PUT", { mode: "receptionist" }, "Receptionist selected")}>AI Receptionist</button><button className="pa-button" aria-pressed={personal} disabled={busy || !snapshot || !readiness.voice_routing_implemented || !readiness.voice_configured} onClick={() => void mutate("/mode", "PUT", { mode: "personal_agent" }, "Personal AI selected")}>Friday · Personal AI</button></div></section>
      {!callbackReady && <p className="pa-stage-note">Automatic callbacks are disabled. You can save follow-ups now; they will not dial until the callback provider and worker are enabled.</p>}
      {latestMessage && <p className="pa-notice" role="status">{["sent", "delivered", "read"].includes(latestMessage.status) ? "WhatsApp update sent ✓" : ["failed", "undelivered"].includes(latestMessage.status) ? "WhatsApp delivery failed" : latestMessage.status === "unknown" ? "WhatsApp status needs review" : "WhatsApp update submitted · awaiting delivery status"}</p>}
      {(needProfile || snapshot) && <ProfileForm key={snapshot?.profile.owner_id ?? "new"} profile={snapshot?.profile ?? null} defaultPhone={readiness.registered_phone} initialOpen={needProfile} busy={busy} onSave={body => mutate("/profile", "PUT", body, "Personal profile saved")} />}
      {snapshot && <div className="pa-workspace"><div className="pa-primary-column">
        <div className="pa-day-summary"><span><strong>{String(pendingTasks).padStart(2, "0")}</strong> tasks to do</span><span><strong>{String(followups.filter(item => item.next_action_at).length).padStart(2, "0")}</strong> upcoming follow-ups</span><a href="#pa-followups" onClick={() => openDetails("pa-reminder")}>Schedule a nudge <span aria-hidden="true">↗</span></a></div><TaskSection tasks={snapshot.tasks} busy={busy} onAction={mutate} />
        <FollowupsSection followups={followups} now={now + serverOffset.current} busy={busy} executable={callbackReady} onAction={mutate} />
      </div><aside className="pa-secondary-column">
        <section className="pa-companion"><div className="pa-companion-top"><span>YOUR PERSONAL AI</span><span className="pa-companion-state">{personal ? "Selected" : "On standby"}</span></div><FridayMark /><h2>Meet your<br />second memory.</h2><p>Call Friday to add a task, think out loud, or pick up where you left off.</p><span className="pa-companion-caption">For calls from your registered number</span><a className="pa-companion-link" href="#pa-settings" onClick={() => openDetails("pa-settings")}>Your call preferences <span aria-hidden="true">↗</span></a></section><section className="pa-section pa-connections"><div className="pa-section-head"><h2>Friday’s connections</h2><span className="pa-muted">Channels</span></div><ul className="pa-readiness"><li><span>Voice</span><span>{readiness.voice_routing_implemented && readiness.voice_configured ? "VoiceLink · configured" : "Setup pending"}</span></li><li><span>Callbacks</span><span>{callbackReady ? `${readiness.callback_provider === "twilio" ? "Twilio" : "VoiceLink"} · enabled` : "Callback setup pending"}</span></li><li><span>WhatsApp</span><span>{readiness.whatsapp_configured && readiness.whatsapp_enabled ? readiness.whatsapp_fallback_configured ? "Template configured" : readiness.whatsapp_sandbox ? "Sandbox · configured" : "Enabled · template pending" : readiness.whatsapp_configured ? "Configured · disabled" : "Not configured"}</span></li></ul></section>
        <ActivitySection key={snapshot.profile.generation} events={snapshot.events} timezone={snapshot.profile.timezone} session={session} />
        <MemorySection key={snapshot.profile.generation} session={session} timezone={snapshot.profile.timezone} />
        <details className="pa-section"><summary>Call and message attempts</summary>{snapshot.attempts.length || snapshot.messages.length ? <ul className="pa-attempts">{[...snapshot.attempts.map(row => ({ ...row, channel: "Call" })), ...snapshot.messages.map(row => ({ ...row, channel: "WhatsApp" }))].map(row => <li key={row.id}><span>{row.channel}</span><strong>{row.status}</strong></li>)}</ul> : <p className="pa-muted">Attempts will appear here when provider execution is connected.</p>}</details>
      </aside></div>}
      {snapshot && <details className="pa-demo-panel"><summary>Demo tools <span>Sample tasks and workspace reset</span></summary><section className="pa-demo-controls"><div><h2>Rehearsal controls</h2><p>These controls affect only your Personal AI data.</p></div><button className="pa-button" disabled={busy || !readiness.demo_controls_enabled} onClick={() => void mutate("/demo/seed", "POST", undefined, "Rehearsal tasks added")}>Seed tasks</button><button className="pa-button pa-danger" disabled={busy || !readiness.demo_controls_enabled} onClick={() => { if (window.confirm("Cancel personal follow-ups, clear recent memory and remove personal demo tasks?")) void mutate("/demo/reset", "POST", undefined, "Personal demo reset"); }}>Reset demo</button></section></details>}
    </>}
  </main></div><footer className="pa-footer">Friday · Your personal workspace <span>A little less to remember.</span></footer></div>;
}

type Mutate = (path: string, method: string, body?: unknown, success?: string) => Promise<boolean>;
function ProfileForm({ profile, defaultPhone, initialOpen, busy, onSave }: { profile: Profile | null; defaultPhone: string | null; initialOpen: boolean; busy: boolean; onSave: (body: unknown) => Promise<boolean> }) {
  const [phone, setPhone] = useState(profile?.phone_e164 ?? defaultPhone ?? "+91");
  const [timezone, setTimezone] = useState(profile?.timezone ?? "Asia/Kolkata");
  const [language, setLanguage] = useState(profile?.language ?? "adaptive");
  const [fallback, setFallback] = useState(profile?.whatsapp_fallback ?? false);
  return <details id="pa-settings" className="pa-profile" open={initialOpen || undefined}><summary>{profile ? `Preferences · ${profile.phone_e164}` : "Register your personal phone"}</summary><form onSubmit={e => { e.preventDefault(); void onSave({ phone_e164: phone, timezone, language, whatsapp_fallback: fallback }); }}><label>Phone number<input type="tel" autoComplete="tel" required pattern="\+[1-9][0-9]{7,14}" value={phone} onChange={e => setPhone(e.target.value)} /></label><label>Timezone<input required value={timezone} onChange={e => setTimezone(e.target.value)} /></label><label>Language<select value={language} onChange={e => setLanguage(e.target.value as Profile["language"])}><option value="adaptive">Follow my language</option><option value="english">English</option><option value="hinglish">Hindi / Hinglish</option></select></label><label className="pa-check"><input type="checkbox" checked={fallback} onChange={e => setFallback(e.target.checked)} />Allow WhatsApp fallback after missed callbacks</label><button className="pa-button pa-primary" disabled={busy}>Save profile</button></form></details>;
}

function TaskSection({ tasks, busy, onAction }: { tasks: Task[]; busy: boolean; onAction: Mutate }) {
  const [title, setTitle] = useState("");
  const [filter, setFilter] = useState<"pending" | "completed" | "all">("pending");
  const shown = tasks.filter(task => filter === "all" || task.status === filter);
  const completed = tasks.filter(task => task.status === "completed").length;
  const [editing, setEditing] = useState<Task | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [description, setDescription] = useState("");
  const update = (task: Task, changes: Partial<Task>) => onAction(`/tasks/${task.id}`, "PUT", {
    title: task.title, description: task.description, due_at: task.due_at, status: task.status,
    version: task.version, ...changes,
  }, "Task updated");
  return <section className="pa-section pa-tasks" id="pa-tasks"><div className="pa-section-head"><div><h2>On your mind</h2><p className="pa-section-description">Make a little space. Put it here.</p></div><span className="pa-muted">{tasks.filter(task => task.status === "pending").length} pending</span></div><div className="pa-task-toolbar"><div className="pa-filters" role="group" aria-label="Filter tasks">{(["pending", "completed", "all"] as const).map(value => <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{value === "pending" ? "To do" : value === "completed" ? "Completed" : "All"} <span>{value === "all" ? tasks.length : value === "completed" ? completed : tasks.length - completed}</span></button>)}</div>{tasks.length > 0 && <span className="pa-muted">{completed} of {tasks.length} done</span>}</div><form className="pa-task-add" onSubmit={e => { e.preventDefault(); if (title.trim()) void onAction("/tasks", "POST", { title: title.trim() }, "Task added").then(saved => { if (saved) setTitle(""); }); }}><label className="pa-visually-hidden" htmlFor="pa-new-task">New task</label><input id="pa-new-task" placeholder="What would you like to get done?" maxLength={200} value={title} onChange={e => setTitle(e.target.value)} required /><button className="pa-button pa-primary" disabled={busy}><span aria-hidden="true">＋</span> Add task</button></form>{shown.length ? <ul className="pa-task-list">{shown.map(task => <li key={task.id}><label className="pa-task-check"><input type="checkbox" checked={task.status === "completed"} disabled={busy} onChange={() => void update(task, { status: task.status === "pending" ? "completed" : "pending" })} /><span className={task.status === "completed" ? "pa-done" : ""}>{task.title}{task.description && <small>{task.description}</small>}</span></label><button className="pa-button pa-subtle" disabled={busy} onClick={() => { setEditing(task); setEditTitle(task.title); setDescription(task.description); }}>Edit</button><button className="pa-button pa-subtle pa-danger" disabled={busy} aria-label={`Delete ${task.title}`} onClick={() => { if (window.confirm(`Remove “${task.title}”?`)) void onAction(`/tasks/${task.id}?version=${task.version}`, "DELETE", undefined, "Task removed"); }}>Remove</button></li>)}</ul> : <p className="pa-empty">{filter === "completed" ? "Completed tasks will live here. One step at a time." : tasks.length ? "You’re all caught up. Enjoy a little breathing room." : "Start with one thing. Add a task above or ask Friday on your next call."}</p>}{editing && <form className="pa-inline-edit" onSubmit={e => { e.preventDefault(); void update(editing, { title: editTitle, description }).then(saved => { if (saved) setEditing(null); }); }}><label>Task title<input required maxLength={200} value={editTitle} onChange={e => setEditTitle(e.target.value)} /></label><label>Details<textarea maxLength={1000} value={description} onChange={e => setDescription(e.target.value)} /></label><div><button className="pa-button pa-primary" disabled={busy}>Save changes</button><button type="button" className="pa-button pa-subtle" onClick={() => setEditing(null)}>Cancel</button></div></form>}{tasks.length === 200 && <p className="pa-muted">Showing the first 200 tasks.</p>}</section>;
}

function ReminderForm({ busy, onSave }: { busy: boolean; onSave: (body: unknown) => Promise<boolean> }) {
  const [title, setTitle] = useState("Pending task update");
  const [context, setContext] = useState("");
  const [seconds, setSeconds] = useState(60);
  return <details className="pa-reminder-form" id="pa-reminder"><summary>＋ Schedule a follow-up</summary><form onSubmit={e => { e.preventDefault(); void onSave({ title, context, delay_seconds: seconds }); }}><label>What should Friday follow up on?<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} /></label><label>Context<textarea maxLength={1000} value={context} onChange={e => setContext(e.target.value)} placeholder="What should Friday remember?" /></label><div className="pa-delay-presets" role="group" aria-label="Quick reminder delay">{[{ label: "1 minute", value: 60 }, { label: "5 minutes", value: 300 }, { label: "15 minutes", value: 900 }, { label: "1 hour", value: 3600 }].map(option => <button type="button" className="pa-button" key={option.value} aria-pressed={seconds === option.value} onClick={() => setSeconds(option.value)}>{option.label}</button>)}</div><label>Call me after (seconds)<input type="number" min={10} max={86400} required value={seconds} onChange={e => setSeconds(Number(e.target.value))} /></label><button className="pa-button pa-primary" disabled={busy}>Save follow-up</button></form></details>;
}

function FollowupRow({ item, now, busy, executable, onAction }: { item: Followup; now: number; busy: boolean; executable: boolean; onAction: Mutate }) {
  const [rescheduling, setRescheduling] = useState(false);
  const [delay, setDelay] = useState(300);
  const act = (action: string, delay_seconds?: number) => onAction(`/followups/${item.id}/action`, "POST", { action, version: item.version, ...(delay_seconds === undefined ? {} : { delay_seconds }) }, "Follow-up updated");
  return <article className="pa-followup"><div><strong>{item.title}</strong><p>{item.context || "Today's pending tasks are saved with this update."}</p><span className={`pa-status pa-status-${item.status}`}>{executable ? followupLabel(item.status) : "Saved · calling paused"}</span></div><div className="pa-timer"><time>{item.next_action_at ? countdown(item.next_action_at, now) : item.status === "awaiting_acknowledgment" ? "Your turn" : item.status === "in_progress" ? "Calling" : "Paused"}</time><small>{item.next_action_at ? "until next action" : item.status === "awaiting_acknowledgment" ? "Confirm or reschedule" : "Choose a new time"}</small></div><div className="pa-followup-actions"><button className="pa-button pa-subtle" disabled={busy} onClick={() => void act("acknowledge")}>Mark resolved</button><button className="pa-button pa-subtle" disabled={busy} onClick={() => setRescheduling(!rescheduling)}>Reschedule</button><button className="pa-button pa-subtle pa-danger" disabled={busy} onClick={() => void act("cancel")}>Cancel</button></div>{rescheduling && <form className="pa-reschedule" onSubmit={e => { e.preventDefault(); void act("reschedule", delay).then(saved => { if (saved) setRescheduling(false); }); }}><label>Call after seconds<input type="number" min={10} max={86400} required value={delay} onChange={e => setDelay(Number(e.target.value))} /></label><button className="pa-button" disabled={busy}>Save new time</button></form>}</article>;
}

function ActivitySection({ events, timezone, session }: { events: Activity[]; timezone: string; session: AuthSession }) {
  const [older, setOlder] = useState<Activity[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rows = [...events, ...older].filter((row, index, all) => all.findIndex(value => value.id === row.id) === index);
  const visibleRows = rows.filter(row => row.event_type !== "tool_completed");
  async function loadMore() {
    const before = cursor ?? rows.at(-1)?.id;
    if (!before) return;
    setBusy(true); setError("");
    try { const next = await personalRequest<{ events: Activity[]; next_before: number | null }>(session, `/events?before=${before}`); setOlder(current => [...current, ...next.events]); setCursor(next.next_before ?? -1); }
    catch (caught) { setError(errorText(caught)); } finally { setBusy(false); }
  }
  return <section className="pa-section pa-activity-section" id="pa-activity"><div className="pa-section-head"><h2>Recent activity</h2><span className="pa-muted">Latest updates</span></div>{visibleRows.length ? <ol className="pa-activity">{visibleRows.map(row => <li key={row.id}><time>{clock(row.created_at, timezone)}</time><span>{row.description}</span></li>)}</ol> : <p className="pa-muted">Your task changes and follow-ups will appear here.</p>}{error && <p role="alert" className="pa-error">{error}</p>}{rows.length >= 50 && cursor !== -1 && <button className="pa-button pa-subtle" disabled={busy} onClick={() => void loadMore()}>{busy ? "Loading…" : "Older activity"}</button>}</section>;
}

function MemorySection({ session, timezone }: { session: AuthSession; timezone: string }) {
  const [rows, setRows] = useState<Memory[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    setBusy(true); setError("");
    try { const next = await personalRequest<{ memory: Memory[] }>(session, "/memory"); setRows(next.memory); }
    catch (caught) { setError(errorText(caught)); } finally { setBusy(false); }
  }
  return <details className="pa-section"><summary>Recent conversation memory</summary><p className="pa-muted">Review retained exchanges. Pending follow-ups are remembered separately.</p><button className="pa-button" disabled={busy} onClick={() => void load()}>{busy ? "Loading…" : "Review recent memory"}</button>{error && <p className="pa-error" role="alert">{error}</p>}{rows && (rows.length ? <ul className="pa-memory">{rows.map(row => <li key={row.id}><strong>{row.speaker} · {clock(row.created_at, timezone)}</strong><p>{row.content}</p></li>)}</ul> : <p className="pa-muted">No unexpired personal conversation memory yet.</p>)}</details>;
}


function openDetails(id: string) {
  const element = document.getElementById(id);
  if (element instanceof HTMLDetailsElement) element.open = true;
}

function followupLabel(status: string): string {
  return ({ scheduled: "Scheduled", pending: "Pending", in_progress: "Call in progress", awaiting_acknowledgment: "Waiting for your confirmation", needs_attention: "Needs review" } as Record<string, string>)[status] ?? status.replaceAll("_", " ");
}

function FollowupsSection({ followups, now, busy, executable, onAction }: { followups: Followup[]; now: number; busy: boolean; executable: boolean; onAction: Mutate }) {
  const attention = followups.filter(item => item.status === "needs_attention");
  const current = followups.filter(item => item.status !== "needs_attention");
  return <section className="pa-section pa-queue" id="pa-followups">
    <div className="pa-section-head"><div><h2>A nudge from Friday</h2><p className="pa-section-description">Pick up where you left off.</p></div><span className="pa-count">{current.length} active</span></div>
    {current.length ? <div className="pa-followups">{current.map(item => <FollowupRow key={item.id} item={item} now={now} busy={busy} executable={executable} onAction={onAction} />)}</div> : <div className="pa-empty"><strong>You’re clear for now.</strong><p>Save a follow-up for the next thing you want to remember.</p></div>}
    <ReminderForm busy={busy} onSave={body => onAction("/followups", "POST", body, executable ? "Follow-up scheduled" : "Follow-up saved; calling is paused")} />
    {attention.length > 0 && <details className="pa-review"><summary><span className="pa-review-dot" aria-hidden="true" />{attention.length} {attention.length === 1 ? "follow-up needs" : "follow-ups need"} review<span>Review</span></summary><p className="pa-muted">These follow-ups have stopped. Choose a new time, mark them resolved, or cancel them.</p>{attention.map(item => <FollowupRow key={item.id} item={item} now={now} busy={busy} executable={executable} onAction={onAction} />)}</details>}
  </section>;
}

function FridayMark() {
  return <svg className="pa-friday-mark" viewBox="0 0 80 80" fill="none" aria-hidden="true"><path d="M40 8c3 21 11 29 32 32-21 3-29 11-32 32-3-21-11-29-32-32C29 37 37 29 40 8Z" fill="currentColor" /><path d="M65 4c1 7 4 10 11 11-7 1-10 4-11 11-1-7-4-10-11-11C61 14 64 11 65 4Z" fill="currentColor" /></svg>;
}

function WorkspaceIcon({ kind }: { kind: string }) {
  const paths: Record<string, string> = {
    "pa-today": "m3 10 9-7 9 7v10H3V10Zm6 10v-7h6v7",
    "pa-tasks": "M9 5h12M9 12h12M9 19h12M3 5l1 1 2-2M3 12l1 1 2-2M3 19l1 1 2-2",
    "pa-followups": "M5 3h14v18H5V3Zm0 5h14M8 1v4M16 1v4M9 12h6M9 16h3",
    "pa-activity": "M3 12h4l3-8 4 16 3-8h4",
    "pa-settings": "M3 6h18M3 12h18M3 18h18M8 3v6M16 9v6M8 15v6",
  };
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[kind] ?? paths["pa-today"]} /></svg>;
}
