import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/supabaseAuth.ts', import.meta.url), 'utf8')
  .replaceAll('import.meta.env.VITE_SUPABASE_URL', '"https://auth.example.test"')
  .replaceAll('import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY', '"test-key"');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const auth = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
const originalFetch = globalThis.fetch;
const oldSession = { access_token: 'expired', refresh_token: 'old-refresh', user: { email: 'staff@example.test' } };
const freshSession = { ...oldSession, access_token: 'fresh', refresh_token: 'new-refresh' };
const response = (status, body = {}) => new Response(JSON.stringify(body), { status });

function storage() {
  const values = new Map([['ai-receptionist.session', JSON.stringify(oldSession)]]);
  globalThis.localStorage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
}

test('concurrent expired API requests share refresh and retry their original payloads', async () => {
  storage();
  let refreshes = 0;
  const requests = [];
  globalThis.fetch = async (url, init) => {
    if (url.includes('grant_type=refresh_token')) {
      refreshes++;
      await new Promise(resolve => setTimeout(resolve, 5));
      return response(200, freshSession);
    }
    requests.push({ body: init.body, token: new Headers(init.headers).get('Authorization') });
    return response(new Headers(init.headers).get('Authorization') === 'Bearer fresh' ? 200 : 401);
  };
  try {
    const results = await Promise.all([1, 2].map(index => auth.authenticatedFetch(
      'https://api.example.test/bookings', oldSession,
      { method: 'POST', body: JSON.stringify({ index }) },
    )));
    assert.deepEqual(results.map(item => item.status), [200, 200]);
    assert.equal(refreshes, 1);
    assert.deepEqual(requests.filter(item => item.token === 'Bearer fresh').map(item => item.body).sort(),
      ['{"index":1}', '{"index":2}']);
    assert.equal(JSON.parse(localStorage.getItem('ai-receptionist.session')).refresh_token, 'new-refresh');
    await auth.authenticatedFetch('https://api.example.test/bookings', oldSession);
    assert.equal(refreshes, 1, 'a stale React session must reuse the rotated token');
  } finally { globalThis.fetch = originalFetch; }
});

test('server errors do not trigger token refresh', async () => {
  storage();
  let calls = 0;
  globalThis.fetch = async () => { calls++; return response(500); };
  try {
    assert.equal((await auth.authenticatedFetch('https://api.example.test', oldSession)).status, 500);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = originalFetch; }
});

test('expired browser session restores with its refresh token', async () => {
  storage();
  globalThis.fetch = async (url, init) => {
    if (url.includes('grant_type=refresh_token')) return response(200, freshSession);
    return new Headers(init.headers).get('Authorization') === 'Bearer fresh'
      ? response(200, freshSession.user) : response(401);
  };
  try { assert.deepEqual(await auth.restoreSession(), freshSession); }
  finally { globalThis.fetch = originalFetch; }
});
