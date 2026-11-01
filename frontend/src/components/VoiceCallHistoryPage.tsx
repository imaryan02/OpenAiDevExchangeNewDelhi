import { useEffect, useMemo, useRef, useState } from "react";
import { Badge, Button, Input, Select, Spinner, Title2 } from "@fluentui/react-components";
import { ArrowLeftRegular, ArrowSyncRegular } from "@fluentui/react-icons";
import { authenticatedFetch } from "../lib/supabaseAuth";
import { operationOutcome, relativeTime, type CallEvent, type CallOperation } from "../lib/callReview";

import { CollectionStatus, ConversationTraceLink, InvestigationViews, investigationTabs, type InvestigationTab, type UsageRecord, type CollectionHealth } from "./CallInvestigation";

type CallRecord = { caller_number: string | null; caller_number_source: string | null; caller_call_count?: number | null; id: string; engine: "CHAINED" | "REALTIME"; status: string; started_at: string; duration_ms: number | null; event_count: number; events_complete: boolean; capture_policy?: { transcripts?: boolean }; committed_count?: number; failed_count?: number };
type Detail = { call: CallRecord; events: CallEvent[]; operations: CallOperation[]; usage: UsageRecord[]; collection_health?: CollectionHealth; events_next_sequence: number | null; trace_available: boolean; runtime_session_status: string | null };
type Message = { source_id?: string; sequence: number; speaker: "caller" | "assistant"; content: string; evidence: string; elapsed_ms: number; truncated: boolean };
type Conversation = { messages: Message[]; status: string; next_sequence: number | null };
type Attempt = { id: string; status: string; occurred_at: string };
const tabs = investigationTabs;
type Tab = InvestigationTab;
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const localTime = (value: string) => new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(value));
const duration = (value: number | null) => value == null ? "Not measured" : `${Math.floor(value / 60000)}m ${Math.floor(value % 60000 / 1000)}s`;
const callOutcome = (call: CallRecord) => call.committed_count && call.failed_count ? "Mixed action outcomes" : call.committed_count ? `${call.committed_count} committed actions` : call.failed_count ? `${call.failed_count} failed actions` : "Not established";
const conversationStates: Record<string, string> = { capture_disabled: "Conversation text was not captured for this call. Enable text capture for future approved calls to see them here.", migration_required: "Conversation storage is not installed. Apply the call review migration before enabling capture.", unavailable: "No unexpired conversation text is available. Messages may not have been captured, or their retention period may have ended." };

export function VoiceCallHistoryPage({ organizationId, accessToken, selectedCallId, onSelectCall }: { organizationId: string; accessToken: string; selectedCallId: string | null; onSelectCall: (callId: string | null) => void }) {
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [detailIdentity, setDetailIdentity] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [attemptStatus, setAttemptStatus] = useState("loading");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [engine, setEngine] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [day, setDay] = useState("");
  const [search, setSearch] = useState("");
  const [querySearch, setQuerySearch] = useState("");
  const [phoneSearch, setPhoneSearch] = useState("");
  const [phoneQuery, setPhoneQuery] = useState("");
  const [callerFilter, setCallerFilter] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [chatRevision, setChatRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const requestKey = `${organizationId}:${accessToken}:${selectedCallId}:${querySearch}:${phoneQuery}:${callerFilter}:${engine}:${status}:${day}:${revision}`;
  const latestRequestKey = useRef(requestKey);
  latestRequestKey.current = requestKey;
  const events = detail?.events ?? [];
  const [traceFocus, setTraceFocus] = useState<number[] | null>(null);
  function navigate(view: Tab, focus: number[] | null = null) { setTraceFocus(focus); setTab(view); }
  const operations = detail?.operations ?? [];
  const loadedDelays = events.flatMap(event => typeof event.metadata.ingestion_delay_ms === "number" && Number.isFinite(event.metadata.ingestion_delay_ms) && event.metadata.ingestion_delay_ms >= 0 ? [event.metadata.ingestion_delay_ms] : []);
  const collectionHealth = detail?.collection_health ? { ...detail.collection_health, max_loaded_ingestion_delay_ms: loadedDelays.length ? Math.max(...loadedDelays) : detail.collection_health.max_loaded_ingestion_delay_ms } : undefined;
  const selected = selectedCallId;
  const token = { access_token: accessToken, refresh_token: "", user: {} };
  const query = useMemo(() => {
    const params = new URLSearchParams({ organization_id: organizationId, limit: "50" });
    if (engine !== "ALL") params.set("engine", engine);
    if (status !== "ALL") params.set("status", status);
    if (querySearch) params.set("search", querySearch);
    if (phoneQuery) params.set("phone_search", phoneQuery);
    if (callerFilter) params.set("caller_number", callerFilter);
    if (day) {
      const start = new Date(`${day}T00:00:00+05:30`);
      params.set("started_from", start.toISOString());
      params.set("started_before", new Date(start.getTime() + 86400000).toISOString());
    }
    return params.toString();
  }, [organizationId, engine, status, day, querySearch, phoneQuery, callerFilter]);

  async function read<T>(path: string, signal?: AbortSignal, body?: object): Promise<T> {
    const response = await authenticatedFetch(`${apiBaseUrl}${path}`, token, { signal, ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
    if (!response.ok) throw new Error(response.status === 422 ? "Use 4 to 15 digits for caller search and a valid call ID." : "Call information could not be loaded. Check your access and try again.");
    return response.json() as Promise<T>;
  }

  function callFilters(offset = 0) {
    const filters: Record<string, string | number> = { offset };
    new URLSearchParams(query).forEach((value, key) => {
      if (key !== "organization_id") filters[key] = key === "limit" ? Number(value) : value;
    });
    return filters;
  }
  function viewCaller(number: string) {
    setCallerFilter(number); setPhoneSearch(""); setPhoneQuery("");
    setSearch(""); setQuerySearch(""); setDay(""); setEngine("ALL"); setStatus("ALL");
    onSelectCall(null);
  }
  function clearFilters() {
    setCallerFilter(null); setPhoneSearch(""); setPhoneQuery("");
    setSearch(""); setQuerySearch(""); setDay(""); setEngine("ALL"); setStatus("ALL");
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null); setCalls([]); setHasMore(false);
    read<{ calls: CallRecord[] }>(`/v1/voice/calls/search?organization_id=${organizationId}`, controller.signal, callFilters())
      .then(payload => { if (!controller.signal.aborted) { setCalls(payload.calls); setHasMore(payload.calls.length === 50); } })
      .catch(reason => { if (!controller.signal.aborted) setError(String(reason.message ?? reason)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, accessToken, revision]);

  useEffect(() => {
    const controller = new AbortController();
    setAttemptStatus("loading"); setAttempts([]);
    read<{ attempts: Attempt[]; status: string }>(`/v1/voice/connection-attempts?organization_id=${organizationId}`, controller.signal)
      .then(payload => { if (!controller.signal.aborted) { setAttempts(payload.attempts); setAttemptStatus(payload.status); } })
      .catch(() => { if (!controller.signal.aborted) setAttemptStatus("unavailable"); });
    return () => controller.abort();
  }, [organizationId, accessToken, revision]);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setConversation(null); setTraceFocus(null); setTab("Overview"); setError(null);
    if (!selected) return;
    setDetailLoading(true);
    read<Detail>(`/v1/voice/calls/${selected}?organization_id=${organizationId}`, controller.signal)
      .then(payload => { if (!controller.signal.aborted) { setDetail(payload); setDetailIdentity(`${organizationId}:${accessToken}:${selected}`); } })
      .catch(reason => { if (!controller.signal.aborted) setError(String(reason.message ?? reason)); })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [selected, organizationId, accessToken, revision]);

  useEffect(() => {
    if (!selected || tab !== "Conversation") return;
    const controller = new AbortController();
    setChatLoading(true); setChatError(null); setConversation(null);
    read<Conversation>(`/v1/voice/calls/${selected}/conversation?organization_id=${organizationId}`, controller.signal)
      .then(payload => { if (!controller.signal.aborted) setConversation(payload); })
      .catch(reason => { if (!controller.signal.aborted) setChatError(String(reason.message ?? reason)); })
      .finally(() => { if (!controller.signal.aborted) setChatLoading(false); });
    return () => controller.abort();
  }, [selected, organizationId, accessToken, tab, chatRevision]);

  async function loadMore(kind: "calls" | "events" | "messages") {
    setBusy(true);
    const keyAtRequest = requestKey;
    try {
      if (kind === "calls") {
        const payload = await read<{ calls: CallRecord[] }>(`/v1/voice/calls/search?organization_id=${organizationId}`, undefined, callFilters(calls.length));
        if (latestRequestKey.current !== keyAtRequest) return;
        setCalls(current => [...current, ...payload.calls]); setHasMore(payload.calls.length === 50);
      } else if (kind === "events" && detail?.events_next_sequence) {
        const payload = await read<Detail>(`/v1/voice/calls/${selected}?organization_id=${organizationId}&after_sequence=${detail.events_next_sequence}`);
        if (latestRequestKey.current !== keyAtRequest) return;
        setDetail(current => current?.call.id === payload.call.id ? { ...payload, events: [...current.events, ...payload.events] } : current);
      } else if (kind === "messages" && conversation?.next_sequence) {
        const payload = await read<Conversation>(`/v1/voice/calls/${selected}/conversation?organization_id=${organizationId}&after_sequence=${conversation.next_sequence}`);
        if (latestRequestKey.current === keyAtRequest) setConversation(current => current ? { ...payload, messages: [...current.messages, ...payload.messages] } : current);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load more information."); }
    finally { setBusy(false); }
  }

  const refresh = <Button appearance="secondary" icon={<ArrowSyncRegular />} disabled={loading || detailLoading || busy} onClick={() => setRevision(value => value + 1)}>Refresh</Button>;
  const errorBanner = error && <div className="alert-banner error" role="alert">{error}</div>;
  const moreEvents = detail?.events_next_sequence && <div className="review-notice">Showing part of this call's event history. Groups may be incomplete. <Button disabled={busy} onClick={() => void loadMore("events")}>Load more events</Button></div>;

  if (selected) {
    const call = detail?.call;
    return <div className="page-stack call-review">
      <div className="review-toolbar"><Button appearance="subtle" icon={<ArrowLeftRegular />} onClick={() => onSelectCall(null)}>{callerFilter ? "Back to caller history" : "All calls"}</Button>{refresh}</div>
      {errorBanner}
      {!detail || detailIdentity !== `${organizationId}:${accessToken}:${selected}` ? <div className="empty-panel">{detailLoading ? <Spinner label="Loading call details" /> : "Call details are unavailable."}</div> : <>
        <section className="review-header"><div><Title2>{localTime(call!.started_at)}</Title2><p>{call!.caller_number ?? "Caller number not captured"}{call!.caller_number && <> · <Button appearance="subtle" onClick={() => viewCaller(call!.caller_number!)}>View caller history</Button></>}</p><p>{call!.engine === "REALTIME" ? "Realtime" : "Chained"} · {duration(call!.duration_ms)} · Call {call!.id.slice(0, 8)}</p></div><div><Badge appearance="tint" color={call!.status === "FAILED" || call!.status === "INTERRUPTED" ? "warning" : "informative"}>{call!.status.toLowerCase()}</Badge><p>{operationOutcome(operations)}</p></div></section>
        {!call!.events_complete && <div className="review-notice">Capture reported gaps. Missing events do not prove an action did not happen.</div>}
        <nav className="review-tabs" aria-label="Call detail views">{tabs.map(item => <Button key={item} appearance={tab === item ? "primary" : "subtle"} aria-current={tab === item ? "page" : undefined} onClick={() => navigate(item)}>{item}</Button>)}</nav>
        {moreEvents}
        <CollectionStatus health={collectionHealth} complete={call!.events_complete} partial={Boolean(detail.events_next_sequence)} runtime={detail.runtime_session_status} />
        {tab === "Diagnostics" && <p className="muted-copy">Call ID: <code>{call!.id}</code> · {detail.trace_available ? "Trace identifier captured; export delivery not verified" : "No exported trace identifier linked"}</p>}
        <InvestigationViews key={call!.id} tab={tab} events={events} operations={operations} usage={detail.usage} focus={traceFocus} navigate={navigate} />
        {tab === "Conversation" && <section className="review-panel"><div className="review-toolbar"><h3>Conversation</h3><Button disabled={chatLoading} onClick={() => setChatRevision(value => value + 1)}>Refresh conversation</Button></div><p className="muted-copy">Caller messages are speech transcriptions; agent messages are generated text. Recognition errors or interrupted playback can differ from the actual audio. No recording is available.</p>{chatError && <div role="alert" className="alert-banner error">{chatError}</div>}{chatLoading ? <Spinner label="Loading conversation" /> : conversation?.messages.length ? <div className="conversation-log" role="log" aria-label="Call conversation">{conversation.messages.map(message => <article key={message.sequence} className={`conversation-message ${message.speaker}`}><header><strong>{message.speaker === "caller" ? "Caller" : "Voice agent"}</strong><time>{relativeTime(message.elapsed_ms)}</time></header><p>{message.content}</p><small>{message.evidence === "transcription" ? "Speech transcription" : message.evidence === "generated_audio_transcript" ? "Generated audio transcript · playback not verified" : "Prepared speech text · playback not verified"}{message.truncated && " · Text truncated"}</small><ConversationTraceLink sourceId={message.source_id} events={events} inspect={sequences => navigate("Execution trace", sequences)} /></article>)}</div> : <div className="review-empty">{conversationStates[conversation?.status ?? ""] ?? "Conversation text is unavailable."}</div>}{conversation?.next_sequence && <Button disabled={busy} onClick={() => void loadMore("messages")}>Load more messages</Button>}</section>}
      </>}
    </div>;
  }

  return <div className="page-stack call-review"><section className="review-panel"><div className="review-toolbar"><div><Title2>{callerFilter ? "Caller history" : "Calls"}</Title2><p className="muted-copy">{callerFilter ? `${callerFilter} · ${calls[0]?.caller_call_count == null ? "History within this clinic" : `${calls[0].caller_call_count} total recorded calls in this clinic`}` : "Find a call by number or ID, then review its conversation and outcome."}</p></div>{refresh}</div><div className="review-filters"><label>Engine<Select value={engine} onChange={(_, data) => setEngine(data.value)}><option value="ALL">All engines</option><option value="CHAINED">Chained</option><option value="REALTIME">Realtime</option></Select></label><label>Call status<Select value={status} onChange={(_, data) => setStatus(data.value)}>{["ALL", "ACTIVE", "ENDED", "INTERRUPTED", "FAILED", "UNKNOWN"].map(value => <option key={value} value={value}>{value === "ALL" ? "All statuses" : value.toLowerCase()}</option>)}</Select></label><label>Date · Asia/Kolkata<input type="date" value={day} onChange={event => setDay(event.target.value)} /></label><form onSubmit={event => { event.preventDefault(); setQuerySearch(search.trim()); setPhoneQuery(phoneSearch.trim()); if (phoneSearch.trim()) setCallerFilter(null); }}><label>Call ID<Input value={search} onChange={(_, data) => setSearch(data.value)} placeholder="Full or partial call ID" /></label><label>Caller number<Input value={phoneSearch} onChange={(_, data) => setPhoneSearch(data.value)} placeholder="Number or last 4+ digits" type="tel" /></label><Button type="submit">Search</Button></form><Button onClick={clearFilters}>All calls / clear filters</Button></div></section>{errorBanner}{loading ? <div className="empty-panel"><Spinner label="Loading calls" /></div> : calls.length ? <div className="review-table-scroll"><table className="review-table review-calls"><thead><tr><th>Started / call</th><th>Caller</th><th>Engine</th><th>Duration</th><th>Call status</th><th>Business outcome</th><th>Review</th></tr></thead><tbody>{calls.map(call => <tr key={call.id}><td><strong>{localTime(call.started_at)}</strong><small>{call.id.slice(0, 8)}{!call.events_complete && " · Capture gaps reported"}</small></td><td>{call.caller_number ? <><Button appearance="subtle" className="caller-history-link" onClick={() => viewCaller(call.caller_number!)}>{call.caller_number}</Button><small>{call.caller_call_count ?? "Unknown"} call{call.caller_call_count === 1 ? "" : "s"} in this clinic</small></> : "Not captured"}</td><td>{call.engine === "REALTIME" ? "Realtime" : "Chained"}</td><td>{duration(call.duration_ms)}</td><td><Badge appearance="tint" color={call.status === "FAILED" || call.status === "INTERRUPTED" ? "warning" : "informative"}>{call.status.toLowerCase()}</Badge></td><td>{callOutcome(call)}</td><td><Button appearance="secondary" onClick={() => onSelectCall(call.id)}>Open call</Button></td></tr>)}</tbody></table></div> : <div className="review-empty">No calls match these filters. Place an approved test call, then refresh to review its evidence.</div>}{hasMore && <Button disabled={busy} onClick={() => void loadMore("calls")}>Load older calls</Button>}<details className="review-panel"><summary>Connection attempts · last 50</summary><p className="muted-copy">Includes rejected connections that never became a call. These attempts contain no caller text or token values.</p>{attemptStatus === "migration_required" ? <p>Apply the call review migration to retain connection attempts.</p> : attemptStatus === "unavailable" ? <p>Connection attempt history is unavailable.</p> : attempts.length ? <table className="review-table"><thead><tr><th>Time</th><th>Result</th></tr></thead><tbody>{attempts.map(attempt => <tr key={attempt.id}><td>{localTime(attempt.occurred_at)}</td><td>{attempt.status === "CONFIGURATION_INCOMPLETE" ? "Rejected: required voice settings missing" : attempt.status === "INVALID_TOKEN" ? "Rejected: VoiceLink authentication failed" : attempt.status === "FAILED" ? "Gateway failed after connection" : "Connection accepted"}</td></tr>)}</tbody></table> : <p>{attemptStatus === "loading" ? "Loading attempts…" : "No connection attempts recorded yet."}</p>}</details></div>;
}
