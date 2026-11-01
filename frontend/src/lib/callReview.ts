export type CallEvent = { sequence: number; event_type: string; stage: string; occurred_at: string; duration_ms: number | null; metadata: Record<string, string | number | boolean> };
export type CallOperation = { operation_id: string; operation_type: string; status: string; created_at: string; committed_at: string | null };
export type ReviewSpan = { id: string; label: string; stage: string; start: number | null; duration: number | null; status: "Completed" | "Failed" | "Completion not captured"; parentId: string | null; events: CallEvent[] };

const names: Record<string, string> = {
  lookup_caller_family: "Look up caller profile", search_availability: "Check availability",
  get_clinic_information: "Read clinic information", suggest_department: "Find department",
  prepare_booking_offer: "Prepare appointment offer", confirm_booking_offer: "Confirm appointment",
  cancel_appointment: "Cancel appointment", reschedule_appointment: "Reschedule appointment",
  start_phone_verification: "Start phone verification", verify_phone_code: "Verify phone code",
};
export const readableTool = (name: string) => names[name] ?? name.replaceAll("_", " ");
export function elapsed(event: CallEvent): number | null {
  const value = event.metadata.elapsed_ms;
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}
export const relativeTime = (ms: number | null) => ms === null ? "Time not measured" : `+${(ms / 1000).toFixed(3)}s`;
export function eventLabel(event: CallEvent): string {
  if (event.event_type === "audio_transferred") return event.metadata.direction === "input" ? "Caller audio received / forwarded" : event.metadata.direction === "output" ? "Agent audio sent to carrier" : "Audio activity (direction unavailable)";
  if (event.event_type === "dialogue") return event.metadata.speaker === "caller" ? "Caller transcription available to agent" : "Agent response text prepared";
  const labels: Record<string, string> = { call_started: "Call connected", call_ended: "Call ended", greeting: "Greeting prepared", identity_received: "Caller identity received", identity_resolved: "Caller profile lookup finished", tools_available: "Agent tools configured", speech_started: "Caller started speaking", speech_stopped: "Caller stopped speaking", playback_acknowledged: "Carrier acknowledged playback", playback_interrupted: "Playback interrupted", awaiting_confirmation: "Waiting for caller approval" };
  return labels[event.event_type] ?? event.event_type.replaceAll("_", " ");
}

/** Pair only correlated start/end events; never guess durations for legacy records. */
export function buildSpans(events: CallEvent[]): ReviewSpan[] {
  const spans: ReviewSpan[] = [];
  const pending = new Map<string, ReviewSpan>();
  for (const event of events) {
    const match = /^(tool|database|transcription|agent)_(started|completed|failed)$/.exec(event.event_type);
    if (!match) continue;
    const [, stage, action] = match;
    const correlation = stage === "database" ? event.metadata.query_id : stage === "tool" ? event.metadata.tool_invocation_id : event.metadata.caller_turn_id;
    const key = correlation === undefined ? null : `${stage}:${correlation}`;
    const label = stage === "tool" ? readableTool(String(event.metadata.tool ?? "controlled_tool")) : stage === "database" ? "Database query" : stage === "transcription" ? "Speech recognition" : "Agent processing";
    if (action === "started") {
      const span: ReviewSpan = { id: key ?? `${stage}:event-${event.sequence}`, label, stage, start: elapsed(event), duration: null, status: "Completion not captured", parentId: stage === "database" && event.metadata.tool_invocation_id ? `tool:${event.metadata.tool_invocation_id}` : null, events: [event] };
      spans.push(span);
      if (key) pending.set(key, span);
    } else {
      const span = key ? pending.get(key) : undefined;
      const duration = event.duration_ms ?? (typeof event.metadata.duration_ms === "number" ? event.metadata.duration_ms : null);
      if (span) {
        span.events.push(event); span.duration = duration;
        span.status = action === "failed" ? "Failed" : "Completed";
        if (key) pending.delete(key);
      } else {
        const end = elapsed(event);
        spans.push({ id: `${stage}:event-${event.sequence}`, label, stage, start: end !== null && duration !== null ? Math.max(0, end - duration) : null, duration, status: action === "failed" ? "Failed" : "Completed", parentId: stage === "database" && event.metadata.tool_invocation_id ? `tool:${event.metadata.tool_invocation_id}` : null, events: [event] });
      }
    }
  }
  return spans;
}

export function operationOutcome(operations: CallOperation[]): string {
  if (!operations.length) return "Task outcome not established";
  const committed = operations.filter(operation => operation.status === "COMMITTED").length;
  const failed = operations.filter(operation => operation.status === "FAILED").length;
  if (committed && failed) return `${committed} committed · ${failed} failed`;
  if (failed) return `${failed} failed action${failed === 1 ? "" : "s"}`;
  if (committed) return `${committed} committed action${committed === 1 ? "" : "s"}`;
  return "No committed action linked";
}

export const correlationKeys = ['caller_turn_id', 'caller_item_id', 'assistant_item_id', 'response_id', 'provider_tool_call_id', 'tool_invocation_id', 'query_id', 'message_source_id', 'durable_operation_id', 'playback_segment_id', 'generation_id'] as const;
export function linkedEvents(events: CallEvent[], sourceId: string): CallEvent[] {
  // One hop through exact captured identifiers. Never infer a causal link by time.
  const anchors = events.filter(event => event.metadata.message_source_id === sourceId);
  const identities = new Map<string, Set<string | number | boolean>>();
  for (const key of correlationKeys) identities.set(key, new Set(anchors.map(event => event.metadata[key]).filter(value => value !== undefined && value !== '')));
  return events.filter(event => anchors.includes(event) || correlationKeys.some(key => identities.get(key)!.has(event.metadata[key])));
}
export function eventIssue(event: CallEvent): boolean {
  return /failed|rejected|timeout|interrupted|error/.test(event.event_type) || Boolean(event.metadata.error_code || event.metadata.failure_type);
}
export function diagnosticGroups(events: CallEvent[]): CallEvent[][] {
  const groups: CallEvent[][] = [];
  const noisy = new Set(['playback_started', 'audio_transferred', 'response_fragment']);
  for (const event of events) {
    const previous = groups.at(-1);
    const last = previous?.at(-1);
    if (last && noisy.has(event.event_type) && last.event_type === event.event_type && last.stage === event.stage && correlationKeys.every(key => last.metadata[key] === event.metadata[key]) && last.metadata.direction === event.metadata.direction) previous!.push(event);
    else groups.push([event]);
  }
  return groups;
}
