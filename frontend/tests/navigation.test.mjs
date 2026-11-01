import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/workspaceNavigation.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { createWorkspaceNavigation, readWorkspaceRoute } = await import(
  'data:text/javascript;base64,' + Buffer.from(compiled).toString('base64')
);

function browser(href = 'https://clinic.test/?other=preserved') {
  const entries = [{ href, state: null }];
  let index = 0;
  const listeners = new Set();
  const storage = new Map();
  const window = {
    location: { href },
    crypto: { randomUUID: () => 'history-session' },
    sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    addEventListener: (type, listener) => { if (type === 'popstate') listeners.add(listener); },
    removeEventListener: (type, listener) => { if (type === 'popstate') listeners.delete(listener); },
    history: {
      get state() { return entries[index].state; },
      replaceState(state, _, url) { entries[index] = { state, href: String(url) }; window.location.href = String(url); },
      pushState(state, _, url) { entries.splice(index + 1); entries.push({ state, href: String(url) }); index++; window.location.href = String(url); },
      back() { if (index > 0) { index--; window.location.href = entries[index].href; listeners.forEach(listener => listener()); } },
      forward() { if (index < entries.length - 1) { index++; window.location.href = entries[index].href; listeners.forEach(listener => listener()); } },
    },
  };
  return { window, entries };
}

test('page navigation traverses browser history and preserves other URL parameters', () => {
  const { window, entries } = browser();
  const nav = createWorkspaceNavigation(window);
  const stop = nav.subscribe(() => {});
  nav.navigate('appointments');
  nav.navigate('patients');
  window.history.back();
  assert.equal(nav.getSnapshot().page, 'appointments');
  assert.equal(nav.getSnapshot().canGoForward, true);
  nav.back();
  assert.equal(nav.getSnapshot().page, 'overview');
  assert.equal(nav.getSnapshot().canGoBack, false);
  nav.forward();
  assert.equal(nav.getSnapshot().page, 'appointments');
  assert.equal(new URL(window.location.href).searchParams.get('other'), 'preserved');
  assert.equal(entries.length, 3);
  stop();
});

test('a new destination after Back drops the forward branch; repeated clicks add no history', () => {
  const { window, entries } = browser();
  const nav = createWorkspaceNavigation(window);
  const stop = nav.subscribe(() => {});
  nav.navigate('appointments');
  nav.navigate('patients');
  nav.back();
  nav.navigate('calendar');
  nav.navigate('calendar');
  assert.equal(nav.getSnapshot().canGoForward, false);
  assert.equal(entries.length, 3);
  nav.forward();
  assert.equal(nav.getSnapshot().page, 'calendar');
  stop();
});

test('call detail restores on Forward and reload while keeping history controls', () => {
  const { window } = browser();
  let nav = createWorkspaceNavigation(window);
  let stop = nav.subscribe(() => {});
  const call = '11111111-2222-3333-4444-555555555555';
  nav.navigate('calls');
  nav.navigate('calls', call);
  nav.back();
  assert.equal(nav.getSnapshot().callId, null);
  stop();
  nav = createWorkspaceNavigation(window);
  stop = nav.subscribe(() => {});
  assert.equal(nav.getSnapshot().canGoForward, true);
  nav.forward();
  assert.equal(nav.getSnapshot().callId, call);
  stop();
  nav = createWorkspaceNavigation(window);
  assert.equal(nav.getSnapshot().callId, call);
  assert.equal(nav.getSnapshot().canGoBack, true);
});

test('invalid destinations fall back safely and call IDs apply only to call history', () => {
  assert.deepEqual(readWorkspaceRoute('https://clinic.test/?page=unknown&call=bad'), { page: 'overview', callId: null });
  assert.deepEqual(readWorkspaceRoute('https://clinic.test/?page=calls&call=bad'), { page: 'calls', callId: null });
  assert.deepEqual(readWorkspaceRoute('https://clinic.test/?page=patients&call=11111111-2222-3333-4444-555555555555'), { page: 'patients', callId: null });
});

test('navigation still works when browser storage is blocked', () => {
  const { window } = browser();
  window.sessionStorage = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  const nav = createWorkspaceNavigation(window);
  const stop = nav.subscribe(() => {});
  nav.navigate('calls');
  nav.back();
  assert.equal(nav.getSnapshot().page, 'overview');
  nav.forward();
  assert.equal(nav.getSnapshot().page, 'calls');
  stop();
});
