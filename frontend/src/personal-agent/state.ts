import type { Followup } from "./types";

export const isPersonalAgentPath = (path: string) => path.replace(/\/$/, "") === "/demo/personal-agent";

export function countdown(trigger: string | null, now: number): string {
  if (!trigger) return "No timer";
  const timestamp = Date.parse(trigger);
  if (!Number.isFinite(timestamp)) return "Time unavailable";
  const seconds = Math.max(0, Math.ceil((timestamp - now) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const tail = `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
  return hours ? `${hours}:${tail}` : tail;
}

export function activeFollowups(rows: Followup[]): Followup[] {
  return rows.filter(row => !["resolved", "cancelled"].includes(row.status)).sort((a, b) =>
    (a.next_action_at ? Date.parse(a.next_action_at) : Infinity)
    - (b.next_action_at ? Date.parse(b.next_action_at) : Infinity));
}
