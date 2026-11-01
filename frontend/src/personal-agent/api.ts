import { authenticatedFetch, type AuthSession } from "../lib/supabaseAuth";

const base = (import.meta.env.VITE_PERSONAL_AGENT_API_BASE_URL
  ?? import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class PersonalApiError extends Error {
  constructor(message: string, public readonly code: string) { super(message); }
}

export async function personalRequest<T>(
  session: AuthSession, path: string, method = "GET", body?: unknown,
): Promise<T> {
  const response = await authenticatedFetch(`${base}/v1/personal-agent${path}`, session, {
    method, headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const message = response.status === 404 ? "This backend does not have Personal AI deployed yet."
      : typeof data?.message === "string" ? data.message
      : response.status === 422 ? "Check the phone, dates and required fields."
      : "Personal workspace could not be loaded. Try again.";
    throw new PersonalApiError(message, data?.code ?? `HTTP_${response.status}`);
  }
  return data as T;
}
