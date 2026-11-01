import { useEffect, useMemo, useRef, useState } from 'react';
import { CallRegular, ArrowSyncRegular } from '@fluentui/react-icons';
import { type Call, type TraceEvent, rehearsal } from '../presentation/trace';
import { appointmentState, followStream, liveEventDwell, signalFor } from '../presentation/state';
import './PresentationPage.css';
import './PresentationPolish.css';
import './PresentationTruth.css';
import './PresentationCinematic.css';
import { Observatory, displayEvent, technicalDetails } from './Observatory';
import { authenticatedFetch } from '../lib/supabaseAuth';

type Props = {
  organizationId: string;
  accessToken: string;
  apiBaseUrl: string;
  clinicName?: string;
  allowLive?: boolean;
  onExit?: () => void;
};

export function PresentationPage({ organizationId, accessToken, apiBaseUrl, clinicName = 'Geeta Medicine', allowLive = true, onExit }: Props) {
  const [mode, setMode] = useState<'rehearsal' | 'live'>('rehearsal');
  const [scenario, setScenario] = useState('booking');
  const [engine, setEngine] = useState('realtime');
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [presentedCount, setPresentedCount] = useState(0);
  const [calls, setCalls] = useState<Call[]>([]);
  const [selectedCall, setSelectedCall] = useState('');
  const [followedCall, setFollowedCall] = useState<Call>();
  const [status, setStatus] = useState('Synthetic events · no telephone call');
  const [collapsed, setCollapsed] = useState(false);
  const [inspect, setInspect] = useState('');
  const [full, setFull] = useState(false);
  const [reduced, setReduced] = useState(false);
  const [revision, setRevision] = useState(0);

  const root = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController>();

  const story = useMemo(() => rehearsal(scenario, engine), [scenario, engine]);
  const duration = story.at(-1)?.at_ms ?? 1;
  const visible = mode === 'rehearsal' ? story.filter(e => e.at_ms <= cursor) : events.slice(0, presentedCount);
  const liveBacklog = mode === 'live' ? Math.max(0, events.length - presentedCount) : 0;
  const liveHealth = status.startsWith('Connected') ? 'connected'
    : status.startsWith('Reconnecting') ? 'reconnecting'
    : status.includes('unavailable') || status.startsWith('LIVE ') ? 'disconnected'
    : 'waiting';
  const active = displayEvent(visible);
  const outcome = appointmentState(visible);
  const activeEngine = mode === 'live' ? followedCall?.engine : engine;

  // Find recent caller and assistant utterances for subtitle strip
  const callerTurn = [...visible].reverse().find(e => e.speaker === 'caller' && e.text);
  const assistantTurn = [...visible].reverse().find(e => e.speaker === 'assistant' && e.text);
  const callerInputInFlight = Boolean(callerTurn && (!assistantTurn || callerTurn.at_ms > assistantTurn.at_ms));

  useEffect(() => {
    setCursor(0);
    setPlaying(true);
    setRevision(v => v + 1);
  }, [scenario, engine]);

  useEffect(() => {
    if (mode !== 'rehearsal' || !playing || cursor >= duration) return;
    const timer = setTimeout(() => setCursor(v => Math.min(duration, v + 100)), 100);
    return () => clearTimeout(timer);
  }, [mode, playing, cursor, duration]);

  useEffect(() => {
    if (mode !== 'live' || presentedCount >= events.length) return;
    const previous = presentedCount > 0 ? events[presentedCount - 1] : undefined;
    const delay = presentedCount === 0 ? 0 : liveEventDwell(previous, events.length - presentedCount);
    const timer = window.setTimeout(() => setPresentedCount(count => Math.min(count + 1, events.length)), delay);
    return () => window.clearTimeout(timer);
  }, [mode, events, presentedCount]);

  useEffect(() => () => abort.current?.abort(), []);

  useEffect(() => {
    const update = () => setFull(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', update);
    return () => document.removeEventListener('fullscreenchange', update);
  }, []);

  async function loadCalls() {
    setStatus('Looking for enrolled calls');
    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/v1/presentation/calls?organization_id=${organizationId}`, {
        access_token: accessToken, refresh_token: '', user: {},
      }, {
        cache: 'no-store',
      });
      if (!response.ok) {
        const failure = await response.json().catch(() => null) as { code?: string; message?: string } | null;
        throw new Error(`LIVE ${response.status} · ${failure?.code ?? failure?.message ?? 'observer unavailable'}`);
      }
      const body = (await response.json()) as {
        calls: Call[];
        observer?: {
          capture_enabled: boolean;
          enrolled_caller_count: number;
          voice_organization_matches: boolean;
        };
      };
      const activeCalls = body.calls.filter(call => !call.ended);
      setCalls(body.calls);
      setSelectedCall(current => body.calls.some(call => call.id === current) ? current : activeCalls[0]?.id ?? '');
      if (body.observer?.voice_organization_matches === false) {
        setStatus('LIVE configuration mismatch · VOICE_ORGANIZATION_ID is not this clinic');
      } else if (body.observer?.enrolled_caller_count === 0) {
        setStatus('LIVE has no enrolled caller · check PRESENTATION_DEMO_CALLERS');
      } else {
        setStatus(activeCalls.length
          ? 'Call found · connecting to observed events'
          : body.calls.length
            ? 'Listening for a new telephone call · ended calls are available for replay'
            : 'Listening for an enrolled telephone call');
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Could not load calls');
    }
  }

  function switchMode(next: 'rehearsal' | 'live') {
    if (next === 'live' && !allowLive) {
      setStatus('Sign in to the reception dashboard first, then reopen the conference view for authenticated LIVE calls.');
      return;
    }
    abort.current?.abort();
    setMode(next);
    setEvents([]);
    setPresentedCount(0);
    setSelectedCall('');
    setFollowedCall(undefined);
    setInspect('');
    setStatus(next === 'rehearsal' ? 'Synthetic events · no telephone call' : 'Waiting for a call');
  }

  useEffect(() => {
    if (mode !== 'live' || followedCall) return;
    void loadCalls();
    const timer = window.setInterval(() => void loadCalls(), 2500);
    return () => window.clearInterval(timer);
  }, [mode, followedCall, organizationId, accessToken, apiBaseUrl]);

  useEffect(() => {
    if (mode !== 'live' || followedCall || !selectedCall || !calls.some(call => call.id === selectedCall && !call.ended)) return;
    follow();
  }, [mode, followedCall, selectedCall, calls]);

  function follow() {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setEvents([]);
    setPresentedCount(0);
    setFollowedCall(calls.find(c => c.id === selectedCall));
    void followStream(
      `${apiBaseUrl}/v1/presentation/calls/${selectedCall}/events?organization_id=${organizationId}`,
      accessToken,
      controller.signal,
      e => setEvents(previous => [...previous, e]),
      message => {
        if (!controller.signal.aborted) setStatus(message);
      },
      (url, init) => authenticatedFetch(url, { access_token: accessToken, refresh_token: '', user: {} }, init)
    );
  }

  function replay() {
    setCursor(0);
    setPlaying(true);
    setRevision(v => v + 1);
  }

  async function fullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await root.current?.requestFullscreen();
    } catch {
      setStatus('Fullscreen unavailable in this browser');
    }
  }

  return (
    <div
      ref={root}
      className={`system-stage ${reduced ? 'motion-reduced' : ''} ${!playing && mode === 'rehearsal' ? 'is-paused' : ''}`}
    >
      {/* 1. COMPACT HEADER (~7-8vh) */}
      <header className="system-header">
        <div className="title-left">
          <span className="system-mark"><CallRegular /></span>
          <div className="title-text">
            <h1>AI Receptionist <span>| Live Call Processing</span></h1>
            <p className="title-context-meta">Natural conversations. Real-time AI. Real appointments.</p>
          </div>
        </div>
        <div className="clinic-identity"><strong>{clinicName}</strong><span>AI-assisted patient access</span></div>

        <div className="header-badges">
          <span className={`engine-badge-tag ${activeEngine}`}>
            {activeEngine === 'chained' ? 'CHAINED ENGINE' : 'OPENAI REALTIME'}
          </span>
          <div className={`mode-indicator ${mode}`}>
            <i />
            {mode === 'rehearsal' ? 'REHEARSAL · SYNTHETIC' : 'LIVE CALL · REAL EVENTS'}
          </div>
        </div>
      </header>

      {/* 2. ARCHITECTURE CANVAS (~62-65vh) */}
      <div className="system-canvas">
        <Observatory
          key={revision}
          events={visible}
          engine={activeEngine}
          inspect={setInspect}
          paused={!playing && mode === 'rehearsal'}
        />
      </div>

      {/* 3. INSPECTOR DRAWER (Collapsible Side Sheet) */}
      {inspect && (
        <aside className="system-inspector">
          <button className="inspector-close" aria-label="Close details" onClick={() => setInspect('')}>
            ×
          </button>
          <h2>
            {inspect === 'database'
              ? 'Supabase / Clinic Records'
              : inspect === 'guard'
              ? 'Confirmation Guard'
              : inspect === 'agent' && activeEngine === 'realtime'
              ? 'OpenAI Realtime Voice Engine'
              : inspect.charAt(0).toUpperCase() + inspect.slice(1)}
          </h2>
          <p>
            {technicalDetails[inspect] ??
              (inspect.startsWith('tool:')
                ? `Declared function: ${inspect.slice(
                    5
                  )}. The selected engine requests this tool; FastAPI validates and executes it against Supabase.`
                : '')}
          </p>
          {inspect === 'database' && (
            <>
              <strong data-testid="outcome">{outcome.outcome}</strong>
              <dl>
                {Object.entries(outcome.details)
                  .filter(([key]) =>
                    ['doctor_name', 'session_date', 'session_time', 'booking_reference', 'token_number'].includes(key)
                  )
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll('_', ' ')}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
              </dl>
            </>
          )}
          {inspect === 'guard' && (outcome.details.doctor_name || outcome.outcome !== 'No booking committed') && (
            <dl>
              {outcome.details.doctor_name && (
                <div>
                  <dt>Guarded proposal</dt>
                  <dd>
                    {outcome.details.doctor_name} · {outcome.details.session_time}
                  </dd>
                </div>
              )}
              <div>
                <dt>Guard state</dt>
                <dd>
                  <strong data-testid="guard-state">{outcome.outcome}</strong>
                </dd>
              </div>
            </dl>
          )}
          {inspect === 'agent' && active?.text && <p>{active.text}</p>}
        </aside>
      )}

      {/* 4. CONVERSATION STRIP: SUBTITLE-STYLE (~13-15vh) */}
      <section className={`conversation-strip speaker-${signalFor(active).node} ${callerInputInFlight ? 'input-in-flight' : ''}`} aria-label="Live Call Transcript">
        {/* Caller Speech Subtitle */}
        <div className="strip-bubble caller-bubble">
          <div className="bubble-tag caller-tag">CALLER {callerInputInFlight && <span className="input-status">HEARD · PROCESSING</span>}</div>
          <p className="bubble-quote">
            {callerTurn?.text ? (
              `“${callerTurn.text}”`
            ) : (
              <span className="bubble-placeholder">Waiting for caller utterance…</span>
            )}
          </p>
        </div>

        {/* AI Assistant Speech Subtitle */}
        <div className="strip-bubble receptionist-bubble">
          <div className="bubble-tag receptionist-tag">RECEPTIONIST</div>
          <p className="bubble-quote">
            {assistantTurn?.text ? (
              `“${assistantTurn.text}”`
            ) : (
              <span className="bubble-placeholder">Assistant response will appear here…</span>
            )}
          </p>
        </div>
      </section>

      {/* 5. FOOTER & CONTROLS BAR (~7-8vh) */}
      <footer className="system-footer">
        {/* Slim Action Event Bar */}
        <div className={`action-event-bar ${signalFor(active).state}`}>
          <span className="event-step-badge">
            {mode === 'rehearsal' ? `${String(visible.length).padStart(2, '0')} / ${story.length}` : 'OBSERVED'}
          </span>
          <p className="event-narrative">
            {active?.title ?? status}
            {active?.kind === 'committed' && <strong> · {outcome.outcome}</strong>}
          </p>
          <span className="event-timestamp">{((active?.at_ms ?? 0) / 1000).toFixed(1)}s</span>
          {liveBacklog > 0 && <span className="live-buffer">{liveBacklog} SIGNAL{liveBacklog === 1 ? '' : 'S'} QUEUED</span>}
          {mode === 'live' && <span className={`live-health ${liveHealth}`}><i />{status}</span>}
        </div>

        {/* Controls Row */}
        <div className={`system-controls ${collapsed ? 'collapsed' : ''}`}>
          <button
            className="collapse-toggle-btn"
            aria-label={collapsed ? 'Expand controls' : 'Collapse controls'}
            onClick={() => setCollapsed(v => !v)}
          >
            {collapsed ? 'Controls ↑' : '↓'}
          </button>
          {!collapsed && (
            <>
              {onExit && <button onClick={onExit}>Dashboard</button>}
              <div className="mode-switch">
                <button aria-pressed={mode === 'rehearsal'} onClick={() => switchMode('rehearsal')}>
                  Rehearsal
                </button>
                <button
                  aria-pressed={mode === 'live'}
                  aria-disabled={!allowLive}
                  title={allowLive ? 'Follow authenticated real-call events' : 'Live mode requires authenticated clinic access'}
                  onClick={() => switchMode('live')}
                >
                  Live
                </button>
              </div>

              {mode === 'rehearsal' ? (
                <>
                  <select aria-label="Scenario" value={scenario} onChange={e => setScenario(e.target.value)}>
                    <option value="booking">Successful booking</option>
                    <option value="correction">Correction</option>
                    <option value="failure">Failure</option>
                    <option value="interruption">Interruption</option>
                  </select>
                  <select aria-label="Voice engine" value={engine} onChange={e => setEngine(e.target.value)}>
                    <option value="realtime">Realtime</option>
                    <option value="chained">Chained</option>
                  </select>
                  <button
                    className="control-primary"
                    onClick={() => (cursor >= duration ? replay() : setPlaying(v => !v))}
                  >
                    {cursor >= duration ? 'Replay' : playing ? 'Pause' : 'Play'}
                  </button>
                  <button aria-label="Restart rehearsal" onClick={replay} title="Restart Replay">
                    <ArrowSyncRegular />
                  </button>
                  <input
                    aria-label="Rehearsal position"
                    type="range"
                    min="0"
                    max={duration}
                    value={cursor}
                    onChange={e => {
                      setCursor(Number(e.target.value));
                      setPlaying(false);
                    }}
                  />
                </>
              ) : (
                <>
                  <button onClick={() => void loadCalls()}>Refresh calls</button>
                  <select
                    aria-label="Enrolled call"
                    value={selectedCall}
                    onChange={e => setSelectedCall(e.target.value)}
                  >
                    <option value="">Select call</option>
                    {calls.map(call => (
                      <option value={call.id} key={call.id}>
                        {call.engine} · {call.ended ? 'ended' : 'active'}
                      </option>
                    ))}
                  </select>
                  <button disabled={!selectedCall} onClick={follow}>
                    {calls.find(call => call.id === selectedCall)?.ended ? 'Replay call' : 'Follow call'}
                  </button>
                </>
              )}

              <button aria-pressed={reduced} onClick={() => setReduced(v => !v)}>
                Reduce motion
              </button>
              <button onClick={() => void fullscreen()}>{full ? 'Exit fullscreen' : 'Fullscreen'}</button>
            </>
          )}
        </div>
      </footer>
    </div>
  );
}
