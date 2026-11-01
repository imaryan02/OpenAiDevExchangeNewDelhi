export type AuthSession = { access_token: string; refresh_token: string; user: { email?: string | null } };
const storageKey = "ai-receptionist.session";
const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL ?? "").replace(/\/$/, "");
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? "";
function assertConfigured() { if (!supabaseUrl || !publishableKey) throw new Error("Add VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY to frontend/.env, then restart Vite."); }
function storeSession(session: AuthSession) { localStorage.setItem(storageKey, JSON.stringify(session)); return session; }
let refreshInFlight: Promise<AuthSession | null> | null = null;

export async function authenticatedFetch(url: string, session: AuthSession, init?: RequestInit): Promise<Response> {
  assertConfigured();
  const saved = localStorage.getItem(storageKey);
  let current = saved ? JSON.parse(saved) as AuthSession : session;
  const send = (token: string) => {
    const headers = new Headers(init?.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return fetch(url, { ...init, headers });
  };
  let response = await send(current.access_token);
  if (response.status === 401) {
    // Concurrent polling and edits share one refresh-token exchange.
    const latest = localStorage.getItem(storageKey);
    const newer = latest ? JSON.parse(latest) as AuthSession : null;
    if (newer && newer.access_token !== current.access_token) current = newer;
    else {
      const refreshed = await refreshSession(current);
      if (!refreshed) return response;
      current = refreshed;
    }
    response = await send(current.access_token);
  }
  return response;
}
export async function signInWithPassword(email: string, password: string): Promise<AuthSession> {
  assertConfigured();
  const response = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=password`, { method: "POST", headers: { apikey: publishableKey, "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  const body = (await response.json()) as AuthSession & { msg?: string; message?: string };
  if (!response.ok || !body.access_token || !body.refresh_token) throw new Error(body.msg ?? body.message ?? "Supabase could not sign you in.");
  return storeSession(body);
}
function refreshSession(session: AuthSession): Promise<AuthSession | null> {
  if (!refreshInFlight) refreshInFlight = requestRefreshSession(session).finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}
async function requestRefreshSession(session: AuthSession): Promise<AuthSession | null> {
  const response = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
    method: "POST", headers: { apikey: publishableKey, "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refresh_token }),
  });
  const body = (await response.json().catch(() => null)) as (AuthSession & { user?: AuthSession["user"] }) | null;
  if (!response.ok || !body?.access_token || !body.refresh_token) return null;
  return storeSession({ ...body, user: body.user ?? session.user });
}
export async function restoreSession(): Promise<AuthSession | null> {
  const rawSession = localStorage.getItem(storageKey); if (!rawSession) return null;
  try {
    let session = JSON.parse(rawSession) as AuthSession;
    assertConfigured();
    let response = await fetch(`${supabaseUrl}/auth/v1/user`, { headers: { apikey: publishableKey, Authorization: `Bearer ${session.access_token}` } });
    if (!response.ok) {
      const refreshed = await refreshSession(session);
      if (!refreshed) return null;
      session = refreshed;
      response = await fetch(`${supabaseUrl}/auth/v1/user`, { headers: { apikey: publishableKey, Authorization: `Bearer ${session.access_token}` } });
      if (!response.ok) return null;
    }
    const user = (await response.json()) as { email?: string | null };
    return storeSession({ ...session, user });
  } catch { return null; }
}
export function clearStoredSession() { localStorage.removeItem(storageKey); }
