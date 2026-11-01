export type Profile = {
  owner_id: string; phone_e164: string; timezone: string;
  language: "adaptive" | "english" | "hinglish";
  mode: "receptionist" | "personal_agent"; whatsapp_fallback: boolean; generation: number;
};
export type Task = {
  id: string; title: string; description: string; status: "pending" | "completed";
  due_at: string | null; version: number;
};
export type Followup = {
  id: string; title: string; context: string; status: string; version: number;
  next_action: string | null; next_action_at: string | null; call_attempts: number;
};
export type Activity = { id: number; event_type: string; description: string; created_at: string };
export type Attempt = { id: string; followup_id: string; status: string; created_at: string };
export type Memory = { id: number; speaker: string; content: string; created_at: string; expires_at: string };
export type Readiness = {
  enabled: boolean; owner_configured: boolean; current_user_id: string;
  registered_phone: string | null;
  database_configured: boolean; voice_configured: boolean; voice_routing_implemented: boolean;
  callback_implemented: boolean; callback_provider: "twilio" | "voicelink";
  callback_configured: boolean; voicelink_outbound_configured: boolean; scheduler_enabled: boolean;
  whatsapp_configured: boolean; whatsapp_fallback_configured: boolean; whatsapp_sandbox: boolean; outbound_enabled: boolean;
  whatsapp_enabled: boolean; demo_controls_enabled: boolean; provider_acceptance_verified: boolean;
  server_time: string;
};
export type Snapshot = {
  profile: Profile; tasks: Task[]; followups: Followup[]; calls: Attempt[];
  attempts: Attempt[]; messages: Attempt[]; events: Activity[]; server_time: string;
};
