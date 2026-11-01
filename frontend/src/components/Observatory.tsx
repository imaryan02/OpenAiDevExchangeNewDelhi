import {
  ArrowRightRegular,
  ArrowSyncRegular,
  BrainCircuitRegular,
  CallRegular,
  CheckmarkCircleFilled,
  DatabaseRegular,
  MicRegular,
  PersonRegular,
  ServerRegular,
  Speaker2Regular,
  WrenchRegular,
} from '@fluentui/react-icons';
import type { TraceEvent } from '../presentation/trace';
import { appointmentState, signalFor } from '../presentation/state';

export const technicalDetails: Record<string, string> = {
  caller: 'The telephone caller. Audio arrives through authenticated VoiceLink metadata.',
  carrier: 'VoiceLink carries telephone audio to and from the voice service.',
  gateway: 'FastAPI owns the call session, routing, and tool-validation boundary.',
  identity: 'Caller context is resolved from authenticated mobile-linked records.',
  agent: 'The selected voice engine understands the request, chooses declared tools, and prepares the response.',
  transcription: 'Chained mode converts observed caller audio into text before the agent receives it.',
  speech: 'Chained mode converts the final assistant text into audio returned through VoiceLink.',
  tools: 'FastAPI validates a declared tool before it can access clinic data.',
  database: 'Supabase contains clinic schedules and committed appointments.',
};

export function displayEvent(events: TraceEvent[]) {
  return [...events].reverse().find(event => event.kind !== 'tools_available') ?? events.at(-1);
}

function observedValues(events: TraceEvent[], details: Record<string, string | number>) {
  const observed = (key: string) => {
    const value = details[key] ?? [...events].reverse().find(event => event.details?.[key] !== undefined)?.details?.[key];
    return value === undefined || value === null ? '' : String(value).replace(' · rehearsal', '').trim();
  };
  return {
    doctor: observed('doctor_name'),
    day: observed('session_date'),
    time: observed('session_time'),
  };
}

function resultLabel(event: TraceEvent | undefined, committed: boolean, failed: boolean) {
  if (committed) return 'CONFIRMED ✓';
  if (failed) return event?.tool && ['confirm_booking_offer', 'cancel_appointment', 'reschedule_appointment'].includes(event.tool) ? 'NOT COMMITTED' : 'FAILED';
  if (!event) return 'WAITING';
  if (event.kind === 'tool_completed' || event.kind === 'database_completed' || event.kind === 'result_transmitted') {
    return event.tool === 'search_availability' ? 'AVAILABLE ✓' : 'RESULT READY ✓';
  }
  if (['tool_started', 'tool_selected', 'database_started', 'mutation_started'].includes(event.kind)) return 'EXECUTING…';
  return 'OBSERVED';
}

function StepArrow({ label, active, reverse = false, pulseKey }: { label: string; active: boolean; reverse?: boolean; pulseKey?: number }) {
  return <div className={`step-arrow ${active ? 'active' : ''} ${reverse ? 'reverse' : ''}`}><span>{label}</span><div><i />{active && <b className="signal-packet" key={pulseKey} />}<ArrowRightRegular /></div></div>;
}

export function Observatory({ events, engine = 'realtime', inspect, paused }: { events: TraceEvent[]; engine?: string; inspect: (id: string) => void; paused: boolean }) {
  const current = displayEvent(events);
  const signal = signalFor(current);
  const state = appointmentState(events);
  const activeToolEvent = [...events].reverse().find(event => event.tool);
  const activeTool = activeToolEvent?.tool;
  const activeOperation = activeToolEvent?.operation_id;
  const operationStart = events.reduce((found, event, index) =>
    event.tool === activeTool && ['tool_selected', 'tool_started'].includes(event.kind) ? index : found, -1);
  const operationEvents = activeOperation
    ? events.filter(event => event.operation_id === activeOperation)
    : operationStart >= 0 ? events.slice(operationStart).filter(event => !event.tool || event.tool === activeTool) : [];
  const callStarted = events.some(event => event.kind === 'call_started');
  const identityResolved = events.some(event => event.kind === 'identity_resolved');
  const identityEvent = [...events].reverse().find(event => ['identity_received', 'identity_resolved'].includes(event.kind));
  const identityStatus = String(identityEvent?.details?.identity_status ?? (identityResolved ? 'Caller recognized' : callStarted ? 'Lookup pending' : 'Awaiting call'));
  const mobileLabel = String([...events].reverse().find(event => event.details?.mobile)?.details?.mobile ?? (callStarted ? 'Enrolled caller · identity protected' : 'No caller connected'));
  const failed = operationEvents.some(event => ['tool_failed', 'database_failed', 'mutation_failed', 'error'].includes(event.kind));
  const committed = operationEvents.some(event => event.kind === 'committed' && event.details?.status === 'CONFIRMED');
  const resultReturned = operationEvents.some(event => ['tool_completed', 'database_completed', 'result_transmitted', 'committed'].includes(event.kind));
  const operationDetails = operationEvents.reduce<Record<string, string | number>>((all, event) => ({ ...all, ...event.details }), {});
  const info = observedValues(operationEvents, operationDetails);
  const argumentsObserved = [info.doctor, info.day, info.time].filter(Boolean);
  const bookingObserved = Boolean(activeTool && ['search_availability', 'prepare_booking_offer', 'confirm_booking_offer'].includes(activeTool));
  const understanding = [bookingObserved ? 'BOOKING' : activeTool ? 'TOOL CALL' : '', info.doctor, [info.day, info.time].filter(Boolean).join(' ')].filter(Boolean);
  const label = resultLabel(activeToolEvent, committed, failed);
  const isRealtime = engine !== 'chained';
  const selectedToolActive = Boolean(activeTool) && current?.kind === 'tool_selected';
  const backendActive = Boolean(activeTool) && current?.kind === 'tool_started';
  const dbActive = signal.node === 'database' || ['database_started', 'database_completed', 'committed'].includes(current?.kind ?? '');
  const currentDuration = current?.details?.duration_ms;
  const recentEvents = events.filter(event => event.kind !== 'tools_available').slice(-3);
  const inbound = ['transport', 'inbound', 'transcript'].includes(signal.route);
  const outbound = ['speech', 'outbound'].includes(signal.route);

  return (
    <section className={`observatory route-${signal.route || 'idle'} signal-${signal.state} ${paused ? 'is-paused' : ''}`} aria-label="Live call architecture">
      <div className="primary-flow">
        <button className={`identity-node ${identityResolved ? 'resolved' : ''} ${signal.node === 'identity' ? 'active' : ''}`} onClick={() => inspect('identity')}>
          <PersonRegular /><span><strong>Mobile identity</strong><small>{identityResolved ? 'Caller + family resolved' : 'Lookup pending'}</small></span>
        </button>
        <button className={`path-card caller-card ${signal.node === 'caller' ? 'active' : ''}`} onClick={() => inspect('caller')}>
          <span className="step-number">1</span><span className="path-icon"><PersonRegular /></span>
          <strong>Caller / Patient</strong><small>Phone call</small><b>{mobileLabel}</b>
        </button>
        <StepArrow label={outbound ? 'Voice response' : 'Caller audio'} active={inbound || outbound} reverse={outbound} pulseKey={current?.sequence} />
        <button className={`path-card voicelink-card ${signal.node === 'carrier' ? 'active' : ''}`} onClick={() => inspect('carrier')}>
          <span className="step-number">2</span><span className="path-icon"><CallRegular /></span>
          <strong>VoiceLink</strong><small>Telephony platform</small><b>Audio in / out</b>
        </button>
        <StepArrow label="Authenticated stream" active={inbound || outbound} reverse={outbound} pulseKey={current?.sequence} />
        <button className={`path-card fastapi-card ${signal.node === 'gateway' ? 'active' : ''}`} onClick={() => inspect('gateway')}>
          <span className="step-number">3</span><span className="path-icon"><ServerRegular /></span>
          <strong>FastAPI</strong><small>Voice gateway</small><b>Auth · routing · session</b>
        </button>
        <StepArrow label={outbound ? 'Audio out' : 'Audio + events'} active={inbound || outbound || signal.route === 'selection'} reverse={outbound} pulseKey={current?.sequence} />
        {isRealtime ? <button className={`path-card realtime-card ${signal.node === 'agent' ? 'active' : ''}`} onClick={() => inspect('agent')}>
          <span className="step-number">4</span><span className="path-icon"><BrainCircuitRegular /></span>
          <div><strong>OpenAI Realtime</strong><small>Audio in → understands → audio out</small></div>
          <span className="capability-row"><em>Listens</em><em>Calls tools</em><em>Speaks</em></span>
        </button> : <div className="chained-lane" aria-label="Chained voice engine">
          <span className="step-number">4</span><span className="lane-title">Chained · transcribe → agent → speak</span>
          <button className={signal.node === 'transcription' ? 'active' : ''} onClick={() => inspect('transcription')}><MicRegular /><span><b>Transcribe</b><small>Audio → text</small></span></button>
          <ArrowRightRegular />
          <button className={signal.node === 'agent' || signal.node === 'tools' ? 'active' : ''} onClick={() => inspect('agent')}><BrainCircuitRegular /><span><b>Agent</b><small>Text + tools</small></span></button>
          <ArrowRightRegular />
          <button className={signal.node === 'speech' ? 'active' : ''} onClick={() => inspect('speech')}><Speaker2Regular /><span><b>Speak</b><small>Text → audio</small></span></button>
        </div>}
        <StepArrow label="Voice response" active={outbound} pulseKey={current?.sequence} />
        <button className={`path-card response-card ${signal.node === 'speech' ? 'active' : ''}`} onClick={() => inspect('caller')}>
          <span className="step-number">5</span><span className="path-icon"><Speaker2Regular /></span>
          <strong>Voice to caller</strong><small>Natural response</small><b>Audio playback</b>
        </button>
        <div className="response-return"><ArrowSyncRegular /><span>Response audio returns through FastAPI and VoiceLink</span></div>
      </div>

      <div className="call-summary">
        <button className={`context-chip ${identityResolved ? 'resolved' : ''}`} onClick={() => inspect('identity')}>
          {identityResolved ? <CheckmarkCircleFilled /> : <PersonRegular />}<span>{identityStatus}</span>
        </button>
        <div className={`now-playing signal-${signal.state}`}>
          <span>NOW</span><b>{current?.title ?? 'Waiting for authenticated call activity'}</b>
          {currentDuration !== undefined && <em>{currentDuration} ms</em>}
        </div>
        <div className={`understanding ${understanding.length ? '' : 'waiting'}`}>
          <span className="understanding-label">{understanding.length ? 'Understood' : 'Listening'}</span>
          {understanding.length ? understanding.map((value, index) => <span className="understanding-value" key={`${value}-${index}`}>{index > 0 && <i>·</i>}<b>{value.toUpperCase()}</b></span>) : <b>Waiting for observed caller intent</b>}
        </div>
        <div className="event-trail" aria-label="Recent observed events">
          {recentEvents.map((event, index) => <span className={index === recentEvents.length - 1 ? 'current' : ''} key={event.sequence}><i />{event.title}</span>)}
        </div>
      </div>

      <section className="tool-workbench" aria-label="Live tool calling">
        <div className="workbench-title"><span>Tool calling</span><small>Observed agent actions only</small></div>
        <div className="engine-drop"><BrainCircuitRegular /><b>{isRealtime ? 'OpenAI Realtime' : 'Agent / LLM'}</b><i />{signal.route === 'selection' && <em className="drop-packet" key={current?.sequence} />}<span>Function request + arguments</span></div>
        <div className="tool-grid">
          <button className={`execution-card context-card ${signal.node === 'identity' ? 'active' : ''}`} onClick={() => inspect('identity')}>
            <span className="execution-icon"><PersonRegular /></span><div><small>Caller context</small><strong>{identityStatus}</strong><p>{mobileLabel}</p></div>
          </button>
          <div className="mini-arrow"><i />{signal.route === 'identity' && <b className="signal-packet" key={current?.sequence} />}<ArrowRightRegular /></div>
          <button className={`execution-card selected-tool-card ${activeTool ? 'chosen' : ''} ${selectedToolActive ? 'active' : ''}`} onClick={() => inspect('tools')}>
            <span className="execution-icon"><WrenchRegular /></span><div><small>Active tool</small>{activeTool && <span className="chosen-flag"><CheckmarkCircleFilled /> Chosen by engine</span>}<strong>{activeTool ?? 'Waiting for tool call'}</strong><div className="argument-chips">{activeTool && argumentsObserved.map(value => <span key={value}>{value}</span>)}</div>{activeTool && !argumentsObserved.length && <p>Arguments protected until returned by the backend</p>}</div>
          </button>
          <div className="mini-arrow"><i />{signal.route === 'request' && <b className="signal-packet" key={current?.sequence} />}<ArrowRightRegular /></div>
          <button className={`execution-card backend-card ${backendActive ? 'active' : ''}`} onClick={() => inspect('tools')}>
            <span className="execution-icon"><ServerRegular /></span><div><small>FastAPI backend</small><strong>Validate & execute</strong><p>{activeTool ? activeTool.replaceAll('_', ' ') : 'Awaiting request'}</p></div>
          </button>
          <div className="mini-arrow"><i />{['dbRequest', 'dbResult'].includes(signal.route) && <b className={`signal-packet ${signal.route === 'dbResult' ? 'reverse' : ''}`} key={current?.sequence} />}<ArrowRightRegular /></div>
          <button className={`execution-card database-card ${dbActive ? 'active' : ''} ${failed ? 'failed' : ''}`} onClick={() => inspect('database')}>
            <span className="execution-icon"><DatabaseRegular /></span><div><small>Supabase · clinic data</small><strong>{committed ? 'Booking committed' : resultReturned ? 'Verified backend result' : activeTool ? 'Query in progress' : 'No query observed'}</strong><p>{committed ? `Reference ${state.details.booking_reference ?? 'confirmed by backend'}` : resultReturned ? argumentsObserved.join(' · ') || 'Result returned to FastAPI' : 'Awaiting an observed backend result'}</p></div><em>{label}</em>
          </button>
        </div>
        <div className={`result-return ${failed ? 'failed' : committed ? 'confirmed' : ''}`}><ArrowSyncRegular /><span>{resultReturned || failed ? <><b>{label}</b> returned to {isRealtime ? 'OpenAI Realtime' : 'Agent / LLM'}</> : <><b>{label}</b> · No tool result returned yet</>}</span></div>
      </section>
    </section>
  );
}
