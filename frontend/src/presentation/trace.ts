export type Stage = "caller" | "carrier" | "transcription" | "voice" | "tools" | "consent" | "database" | "identity" | "gateway";
export type TraceEvent = { sequence: number; at_ms: number; kind: string; stage: Stage; title: string; speaker?: string; text?: string; tools?: string[]; origin?: string; direction?: string; tool?: string; operation_id?: string; details?: Record<string, string | number> };
export type Call = { id: string; engine: "chained" | "realtime"; started_at: number; ended: boolean };

// Authored rehearsal, never executed against business tools or presented as a real call.
export function rehearsal(scenario: string, engine = "realtime"): TraceEvent[] {
  const events: Omit<TraceEvent, "sequence">[] = [
    { at_ms: 0, kind: "call_started", stage: "carrier", title: "Authenticated call connected" },
    { at_ms: 1800, kind: "dialogue", stage: "voice", title: "Assistant response", speaker: "assistant", text: "Namaste. Main aapki appointment mein kaise madad kar sakti hoon?" },
    { at_ms: 5000, kind: "dialogue", stage: "caller", title: "Caller transcript", speaker: "caller", text: "Kal Dr Amit ke paas mere liye appointment book kar dijiye." },
    { at_ms: 6800, kind: "generation_started", stage: "voice", title: "Agent processing caller turn" },
    { at_ms: 8300, kind: "tool_started", stage: "tools", title: "Checking available sessions", tool: "search_availability" },
    { at_ms: 10300, kind: "tool_completed", stage: "tools", title: "Two sessions available", tool: "search_availability", details: { result_count: 2 } },
    { at_ms: 12400, kind: "dialogue", stage: "voice", title: "Assistant response", speaker: "assistant", text: "Dr Amit ka kal 9 se 12 baje ka session available hai. Kya yeh theek rahega?" },
    { at_ms: 16200, kind: "dialogue", stage: "caller", title: "Caller transcript", speaker: "caller", text: "Haan, subah wala session theek hai." },
    { at_ms: 18100, kind: "tool_started", stage: "tools", title: "Preparing appointment details", tool: "prepare_booking_offer" },
    { at_ms: 19800, kind: "tool_completed", stage: "tools", title: "Appointment details prepared", tool: "prepare_booking_offer", details: { doctor_name: "Dr Amit Kumar", session_date: "Tomorrow · rehearsal", session_time: "9:00 AM – 12:00 PM", fee_minor: 50000, currency: "INR" } },
    { at_ms: 20700, kind: "proposal", stage: "consent", title: "Appointment proposed; confirmation required" },
    { at_ms: 22500, kind: "dialogue", stage: "voice", title: "Appointment readback", speaker: "assistant", text: "Aapke liye Dr Amit Kumar, kal 9 se 12 baje ka session. Fee 500 rupaye clinic par deni hogi. Kya main confirm kar doon?" },
    { at_ms: 27000, kind: "awaiting_confirmation", stage: "consent", title: "Readback acknowledged; awaiting approval" },
  ];
  if (scenario === "correction") events.push(
    { at_ms: 29500, kind: "correction", stage: "caller", title: "Caller correction", speaker: "caller", text: "Nahi, kal nahi. Parso ke liye chahiye." },
    { at_ms: 30800, kind: "playback_interrupted", stage: "consent", title: "Previous proposal superseded" },
    { at_ms: 32300, kind: "tool_started", stage: "tools", title: "Checking a different day", tool: "search_availability" },
    { at_ms: 34200, kind: "tool_completed", stage: "tools", title: "Replacement session found", tool: "search_availability", details: { result_count: 1 } },
    { at_ms: 36800, kind: "tool_completed", stage: "tools", title: "Fresh appointment details prepared", tool: "prepare_booking_offer", details: { doctor_name: "Dr Amit Kumar", session_date: "Day after tomorrow · rehearsal", session_time: "5:00 PM – 7:00 PM", fee_minor: 50000, currency: "INR" } },
    { at_ms: 38000, kind: "proposal", stage: "consent", title: "Fresh approval required" },
    { at_ms: 39500, kind: "dialogue", stage: "voice", title: "Updated readback", speaker: "assistant", text: "Parso 5 se 7 baje, Dr Amit ke saath. Fee 500 rupaye clinic par. Kya ise confirm kar doon?" },
  );
  const offset = scenario === "correction" ? 14500 : 0;
  events.push(
    { at_ms: 30000 + offset, kind: "dialogue", stage: "caller", title: "Caller transcript", speaker: "caller", text: "Haan ji, confirm kar dijiye." },
    { at_ms: 32300 + offset, kind: "tool_started", stage: "tools", title: "Confirming the appointment", tool: "confirm_booking_offer" },
    scenario === "failure"
      ? { at_ms: 34700 + offset, kind: "tool_failed", stage: "tools", title: "Session filled before confirmation", tool: "confirm_booking_offer" }
      : { at_ms: 34700 + offset, kind: "committed", stage: "database", title: "Appointment transaction committed", tool: "confirm_booking_offer", details: { booking_reference: "DEMO-1042", token_number: 2, status: "CONFIRMED", payment_status: "DUE_AT_CLINIC" } },
    { at_ms: 37000 + offset, kind: "dialogue", stage: "voice", title: "Assistant response", speaker: "assistant", text: scenario === "failure" ? "Maaf kijiye, yeh session ab full hai. Appointment book nahi hui. Kya main doosra session check karoon?" : "Aapka appointment confirm ho gaya hai. Token number 2 hai. Fee clinic par deni hogi." },
    { at_ms: 41800 + offset, kind: "call_ended", stage: "caller", title: "Call ended" },
  );
  if (scenario === "interruption") events.push({ at_ms: 3500, kind: "playback_interrupted", stage: "caller", title: "Caller interrupted playback" });
  events.push({ at_ms: 39500 + offset, kind: "playback_acknowledged", stage: "voice", title: "Carrier acknowledged playback" });
  const configured = engine === 'realtime'
    ? ['get_clinic_information', 'search_availability', 'suggest_department', 'list_upcoming_appointments', 'prepare_booking_offer', 'prepare_cancel_appointment', 'prepare_reschedule_appointment']
    : ['get_clinic_information', 'search_availability', 'suggest_department', 'lookup_caller_family', 'start_phone_verification', 'verify_phone_code', 'list_upcoming_appointments', 'prepare_booking_offer', 'confirm_booking_offer', 'cancel_appointment', 'reschedule_appointment'];
  const greeting = engine === 'realtime' ? 4500 : 1100;
  const expanded: Omit<TraceEvent, 'sequence'>[] = [
    { at_ms: 0, kind: 'call_started', stage: 'carrier', title: 'VoiceLink authenticated the incoming call' },
    { at_ms: 400, kind: 'identity_received', stage: 'identity', title: 'Mobile identity received from VoiceLink', details: {mobile: 'Demo mobile · •••• 1042', source: 'Authenticated carrier metadata'} },
    { at_ms: 800, kind: 'tool_started', stage: 'tools', title: 'Backend looks up the mobile-linked caller', tool: 'lookup_caller_family', origin: 'backend' },
    { at_ms: 1700, kind: 'database_started', stage: 'database', title: 'Backend query sent to Supabase', tool: 'lookup_caller_family', origin: 'backend' },
    { at_ms: 3100, kind: 'database_completed', stage: 'database', title: 'Supabase returned the caller context', tool: 'lookup_caller_family', origin: 'backend' },
    { at_ms: 3500, kind: 'identity_resolved', stage: 'identity', title: 'Mobile profile lookup completed', details: {identity_status: 'Recognized caller'} },
    { at_ms: engine === 'realtime' ? 4000 : 11200, kind: 'tools_available', stage: 'voice', title: 'Voice engine tools configured', tools: configured },
    { at_ms: greeting, kind: 'greeting', stage: 'voice', title: engine === 'realtime' ? 'Backend prepares the welcome greeting' : 'Greeting begins alongside caller lookup' },
    { at_ms: greeting + 200, kind: 'dialogue', stage: 'voice', title: 'Welcome greeting ready', speaker: 'assistant', text: 'Namaste. Geeta Medicine mein aapka swagat hai. Main aapki kya madad kar sakti hoon?' },
    { at_ms: greeting + 600, kind: 'audio_transferred', stage: 'carrier', title: 'Greeting audio sent to VoiceLink', direction: 'output', details: {chunks: 8} },
  ];
  for (const original of events.filter(e => e.at_ms >= 3500)) {
    const event = { ...original, at_ms: original.at_ms + 5000 };
    expanded.push(event);
    if (event.kind === 'tool_started') {
      const mutation = event.tool === 'confirm_booking_offer';
      expanded.push({ ...event, at_ms: event.at_ms - 300, kind: mutation ? 'approval_granted' : 'tool_selected', stage: mutation ? 'consent' : 'voice', title: mutation ? 'Backend accepted explicit confirmation' : 'Engine requested a tool' });
      expanded.push({ ...event, at_ms: event.at_ms + 400, kind: 'database_started', stage: 'database', title: 'Backend query sent to Supabase' });
      expanded.push({ ...event, at_ms: event.at_ms + 1000, kind: 'database_completed', stage: 'database', title: 'Supabase returned to backend' });
    }
    if (event.kind === 'tool_completed') expanded.push({ ...event, at_ms: event.at_ms + 250, kind: 'result_transmitted', stage: 'voice', title: 'Tool result delivered to voice engine' });
    if (event.kind === 'committed') expanded.push({ ...event, at_ms: event.at_ms - 600, kind: 'mutation_started', title: 'Committing approved booking transaction', details: undefined });
    if (event.kind === 'dialogue') {
      expanded.push({ at_ms: event.at_ms + 500, kind: 'audio_transferred', stage: 'carrier', title: event.speaker === 'caller' ? 'Caller audio received by engine' : 'Response audio sent to VoiceLink', direction: event.speaker === 'caller' ? 'input' : 'output', details: {chunks: Math.round(event.at_ms / 100)} });
      if (event.speaker === 'assistant' && engine === 'realtime') expanded.push({ ...event, at_ms: event.at_ms - 500, kind: 'response_fragment', title: 'Receiving response transcript from Realtime', text: event.text?.slice(0, 44) });
    }
  }
  expanded.sort((a, b) => a.at_ms - b.at_ms);
  return expanded.map((event, i) => ({ ...event, sequence: i + 1 }));
}

export async function readEventStream(response: Response, onEvent: (event: TraceEvent) => void, onStatus: (status: string) => void, idleTimeoutMs = 8000): Promise<boolean> {
  if (!response.body) throw new Error("This browser cannot read the live stream.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "", complete = false;
  try {
    while (true) {
      let timeout: ReturnType<typeof setTimeout> | undefined;
      const stalled = new Promise<never>((_, reject) => {
        timeout = setTimeout(() => reject(new Error("Live stream heartbeat timed out.")), idleTimeoutMs);
      });
      const { done, value } = await Promise.race([reader.read(), stalled]).finally(() => {
        if (timeout) clearTimeout(timeout);
      });
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r/g, "");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
        const eventType = block.split("\n").find(line => line.startsWith("event:"))?.slice(6).trim();
        if (eventType === "complete") { complete = true; onStatus("Call ended"); }
        else if (eventType === "expired") throw new Error("The call trace has expired.");
        else if (eventType === "gap") onStatus("Earlier events expired; showing retained history");
        else if (!block.startsWith(":")) {
          const data = block.split("\n").find(line => line.startsWith("data: "));
          if (data) onEvent(JSON.parse(data.slice(6)) as TraceEvent);
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
  return complete;
}
