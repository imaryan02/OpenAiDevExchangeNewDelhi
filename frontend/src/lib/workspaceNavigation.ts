const pages = ["overview", "calendar", "appointments", "patients", "booking", "assistant", "presentation", "calls", "resources", "departments", "doctors", "settings"] as const;
export type WorkspacePage = typeof pages[number];
export type WorkspaceRoute = { page: WorkspacePage; callId: string | null };
type Snapshot = WorkspaceRoute & { canGoBack: boolean; canGoForward: boolean };
type Entry = { id: string; index: number };
const marker = "clinicNavigation";

export function readWorkspaceRoute(href: string): WorkspaceRoute {
  const url = new URL(href);
  const requested = url.searchParams.get("page");
  const page = pages.includes(requested as WorkspacePage) ? requested as WorkspacePage : "overview";
  const call = url.searchParams.get("call");
  const callId = page === "calls" && call && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(call) ? call : null;
  return { page, callId };
}

/** Browser history stores routes only; credentials and form contents stay out of it. */
export function createWorkspaceNavigation(browser: Window) {
  const readEntry = (): Entry | null => {
    const value = browser.history.state?.[marker];
    return value && typeof value.id === "string" && Number.isSafeInteger(value.index) && value.index >= 0 ? value : null;
  };
  const initial = readEntry() ?? { id: browser.crypto.randomUUID(), index: 0 };
  let tail = initial.index;
  const storageKey = `clinic.navigation.${initial.id}`;
  try {
    const saved = Number(browser.sessionStorage.getItem(storageKey));
    if (Number.isSafeInteger(saved) && saved >= initial.index) tail = saved;
  } catch { /* History still works when session storage is unavailable. */ }
  const listeners = new Set<() => void>();
  const saveTail = () => { try { browser.sessionStorage.setItem(storageKey, String(tail)); } catch { /* Optional persistence. */ } };
  const routeUrl = (route: WorkspaceRoute) => {
    const url = new URL(browser.location.href);
    url.searchParams.set("page", route.page);
    if (route.page === "calls" && route.callId) url.searchParams.set("call", route.callId);
    else url.searchParams.delete("call");
    return url;
  };
  const state = (entry: Entry) => ({ ...browser.history.state, [marker]: entry });
  browser.history.replaceState(state(initial), "", routeUrl(readWorkspaceRoute(browser.location.href)));
  saveTail();
  const snapshotNow = (): Snapshot => {
    const entry = readEntry();
    const index = entry?.id === initial.id ? entry.index : 0;
    return { ...readWorkspaceRoute(browser.location.href), canGoBack: index > 0, canGoForward: entry?.id === initial.id && index < tail };
  };
  let snapshot = snapshotNow();
  const refresh = () => {
    const next = snapshotNow();
    if (next.page === snapshot.page && next.callId === snapshot.callId && next.canGoBack === snapshot.canGoBack && next.canGoForward === snapshot.canGoForward) return;
    snapshot = next;
    listeners.forEach(listener => listener());
  };
  return {
    getSnapshot: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener);
      if (listeners.size === 1) browser.addEventListener("popstate", refresh);
      refresh();
      return () => { listeners.delete(listener); if (!listeners.size) browser.removeEventListener("popstate", refresh); };
    },
    navigate(page: WorkspacePage, callId: string | null = null) {
      const route = readWorkspaceRoute(routeUrl({ page, callId }).href);
      refresh();
      if (route.page === snapshot.page && route.callId === snapshot.callId) return;
      const entry = readEntry();
      const index = entry?.id === initial.id ? entry.index + 1 : 1;
      browser.history.pushState(state({ id: initial.id, index }), "", routeUrl(route));
      tail = index;
      saveTail();
      refresh();
    },
    back() { refresh(); if (snapshot.canGoBack) browser.history.back(); },
    forward() { refresh(); if (snapshot.canGoForward) browser.history.forward(); },
  };
}
