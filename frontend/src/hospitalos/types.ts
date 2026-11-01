export type Origin = "CENTRAL_DELHI" | "NORTH_DELHI" | "EAST_DELHI";
export type Preference = "ANY" | "AFFORDABLE" | "PRIVATE";
export type Requirement = "GENERAL" | "ICU" | "TRAUMA" | "PEDIATRIC" | "OBSTETRIC";

export type Facility = {
  slug: string; name: string; area: string; address: string; cost_category: string;
  synthetic: boolean; connected_receiving_desk: boolean; emergency_open: boolean;
  ed_bays_ready: number; ed_bays_available: number; ed_holds_active: number;
  icu_beds_ready: number; icu_beds_available: number; icu_holds_active: number;
  ventilators_ready: number; pending_requests: number;
  ct_available: boolean; trauma_available: boolean; pediatric_available: boolean;
  obstetric_available: boolean; verified_at: string; distance_km: number;
  recommended: boolean; reason_codes: string[];
};

export type Resource = Omit<Facility, "connected_receiving_desk" | "distance_km" | "recommended" | "reason_codes" | "address" | "ed_bays_available" | "icu_beds_available"> & {
  id: string; location_id: string; receiving_enabled: boolean; version: number;
  updated_by: string | null;
};

export type DemoEvent = { id: number; event_type: string; actor_type: string; detail: Record<string, unknown>; occurred_at: string };
export type DemoRequest = {
  id: string; case_id: string; organization_id: string; status: "PENDING" | "ACCEPTED" | "DECLINED" | "EXPIRED" | "WITHDRAWN" | "HOLD_CONFLICT";
  version: number; deadline_at: string; created_at: string; decided_at: string | null;
  arrival_note: string | null;
  eta_minutes: number | null; origin: Origin; requirement: Requirement; audience: "PATIENT" | "AMBULANCE";
  facility_name: string; facility_slug: string; hold_state: "ACTIVE" | "RELEASED" | "EXPIRED" | null;
  hold_expires_at: string | null; events: DemoEvent[]; synthetic_demo: true;
};
export type TrackingCredentials = { case_id: string; tracking_token: string };

export const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const formatVerified = (value: string) => new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata",
}).format(new Date(value));

export async function responseMessage(response: Response): Promise<string> {
  const body = await response.json().catch(() => null) as { detail?: string | { message?: string }; message?: string } | null;
  const detail = body?.detail;
  return (typeof detail === "string" ? detail : detail?.message) ?? body?.message ?? `Request failed (${response.status}).`;
}
