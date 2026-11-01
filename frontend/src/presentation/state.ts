import { readEventStream, type TraceEvent } from './trace';

export function liveEventDwell(event?: TraceEvent, backlog = 0) {
  if (!event) return 0;
  const semanticDwell: Record<string, number> = {
    dialogue: event.speaker === 'caller' ? 1800 : 1500,
    tool_selected: 1700,
    tool_started: 1300,
    database_started: 850,
    database_completed: 1300,
    tool_completed: 1500,
    result_transmitted: 1100,
    committed: 1900,
    identity_received: 900,
    identity_resolved: 1200,
    call_started: 900,
    call_ended: 1400,
  };
  const base = semanticDwell[event.kind] ?? (['audio_transferred', 'response_fragment'].includes(event.kind) ? 380 : 700);
  const transient = ['audio_transferred', 'response_fragment'].includes(event.kind);
  if (backlog > 24) return transient ? 70 : Math.min(520, base);
  if (backlog > 10) return transient ? 120 : Math.min(760, base);
  return backlog > 5 ? Math.max(260, Math.round(base * .55)) : backlog > 2 ? Math.max(420, Math.round(base * .76)) : base;
}

export function appointmentState(events: TraceEvent[]) {
  let details: Record<string, string | number> = {};
  let outcome = 'No booking committed';
  for (const event of events) {
    if (event.tool === 'prepare_booking_offer' && event.kind === 'tool_completed') {
      details = { ...event.details }; outcome = 'Awaiting confirmation';
    } else if (event.details) details = { ...details, ...event.details };
    if (['tool_failed', 'error', 'database_failed'].includes(event.kind)) outcome = 'Operation failed';
    if (event.kind === 'mutation_started') outcome = 'Committing transaction';
    if (event.kind === 'mutation_failed') outcome = 'Commit outcome uncertain';
    if (event.kind === 'committed') {
      outcome = event.tool === 'cancel_appointment' || event.details?.status === 'CANCELLED'
        ? 'Cancelled' : event.tool === 'reschedule_appointment' ? 'Rescheduled'
        : event.tool === 'confirm_booking_offer' && event.details?.status === 'CONFIRMED' ? 'Confirmed' : 'Transaction completed';
    }
  }
  return { details, outcome };
}

// Routes describe observed boundaries. No inferred DB reads or agent reasoning.
export function signalFor(event?: TraceEvent): { route: string; state: string; node: string } {
  if (!event) return { route: '', state: 'idle', node: '' };
  if (event.kind === 'identity_received' || event.kind === 'identity_resolved') return { route: 'identity', state: 'active', node: 'identity' };
  if (event.kind === 'database_started' || event.kind === 'mutation_started') return { route: 'dbRequest', state: 'active', node: 'database' };
  if (event.kind === 'database_completed') return { route: 'dbResult', state: 'active', node: 'database' };
  if (event.kind === 'database_failed' || event.kind === 'mutation_failed') return { route: 'dbResult', state: 'failed', node: 'database' };
  if (event.kind === 'tool_selected') return { route: 'selection', state: 'active', node: 'agent' };
  if (event.kind === 'approval_granted') return { route: 'approval', state: 'active', node: 'guard' };
  if (event.kind === 'greeting') return { route: 'greeting', state: 'active', node: 'gateway' };
  if (event.kind === 'speech_stopped') return { route: '', state: 'waiting', node: 'agent' };
  if (event.kind === 'tools_available') return { route: '', state: 'idle', node: 'agent' };
  if (event.kind === 'call_started') return { route: 'transport', state: 'active', node: 'carrier' };
  if (event.kind === 'audio_transferred') return event.direction === 'output'
    ? { route: 'outbound', state: 'active', node: 'speech' }
    : { route: 'inbound', state: 'active', node: event.details?.boundary === 'gateway' ? 'gateway' : 'agent' };
  if (event.kind === 'playback_interrupted') return { route: 'inbound', state: 'interrupted', node: 'caller' };
  if (event.kind === 'correction') return { route: 'inbound', state: 'correction', node: 'guard' };
  if (event.kind === 'tool_failed' || event.kind === 'error') return { route: 'result', state: 'failed', node: 'tools' };
  if (event.kind === 'committed') return { route: 'commit', state: event.tool === 'cancel_appointment' ? 'cancelled' : 'committed', node: 'database' };
  if (event.kind === 'tool_started') return { route: 'request', state: 'active', node: 'tools' };
  if (event.kind === 'tool_completed') return { route: 'result', state: 'active', node: 'agent' };
  if (event.kind === 'result_transmitted') return { route: 'result', state: 'active', node: 'agent' };
  if (event.kind === 'response_fragment') return { route: 'speech', state: 'active', node: 'speech' };
  if (event.stage === 'consent') return { route: 'guard', state: 'waiting', node: 'guard' };
  if (event.kind === 'call_ended') return { route: '', state: 'ended', node: '' };
  if (event.kind === 'playback_acknowledged') return { route: 'outbound', state: 'active', node: 'caller' };
  if (event.kind === 'generation_completed' || (event.kind === 'generation_started' && event.title !== 'Agent processing caller turn')) return { route: 'speech', state: 'active', node: 'speech' };
  if (event.kind === 'dialogue' && event.speaker === 'assistant') return { route: 'speech', state: 'active', node: 'speech' };
  if (event.kind === 'dialogue' && event.speaker === 'caller') return { route: 'transcript', state: 'active', node: 'agent' };
  if (event.kind === 'generation_started') return { route: '', state: 'active', node: 'agent' };
  return { route: 'inbound', state: 'active', node: 'transcription' };
}

export async function followStream(url: string, token: string, signal: AbortSignal,
  onEvent: (event: TraceEvent) => void, onStatus: (status: string) => void,
  request: (url: string, init?: RequestInit) => Promise<Response> = fetch) {
  let cursor = 0;
  while (!signal.aborted) {
    try {
      const response = await request(`${url}&after=${cursor}`, { headers: { Authorization: `Bearer ${token}` }, signal, cache: 'no-store' });
      if (!response.ok) {
        if ([401, 403, 404].includes(response.status)) { onStatus('Live observer unavailable. Refresh access or select another call.'); return; }
        throw new Error('Connection interrupted');
      }
      onStatus('Connected · observing backend events');
      const complete = await readEventStream(response, event => {
        if (signal.aborted || event.sequence <= cursor) return;
        cursor = event.sequence; onEvent(event);
      }, onStatus);
      if (complete) return;
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof Error && error.message.includes('expired')) { onStatus(error.message); return; }
    }
    if (signal.aborted) return;
    onStatus('Reconnecting · retaining event cursor');
    await new Promise<void>(resolve => {
      const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); };
      const timer = setTimeout(finish, 1200); signal.addEventListener('abort', finish, { once: true });
    });
  }
}
