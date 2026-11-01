import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';

const source = readFileSync(new URL('../src/personal-agent/state.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022,
} }).outputText;
const { countdown, activeFollowups, isPersonalAgentPath } = await import(
  'data:text/javascript;base64,' + Buffer.from(compiled).toString('base64')
);

test('personal pathname does not replace receptionist or conference entry', () => {
  assert.equal(isPersonalAgentPath('/demo/personal-agent'), true);
  assert.equal(isPersonalAgentPath('/demo/personal-agent/'), true);
  for (const path of ['/', '/demo/personal-agent-other', '/calls']) assert.equal(isPersonalAgentPath(path), false);
});

test('countdown uses saved trigger time and never becomes negative', () => {
  const start = Date.parse('2026-09-27T12:00:00Z');
  assert.equal(countdown('2026-09-27T12:01:00Z', start), '01:00');
  assert.equal(countdown('2026-09-27T12:01:00Z', start + 17500), '00:43');
  assert.equal(countdown('2026-09-27T12:01:00Z', start + 70000), '00:00');
  assert.equal(countdown('2026-09-27T13:01:00Z', start), '1:01:00');
  assert.equal(countdown('invalid', start), 'Time unavailable');
});

test('unresolved answered events stay visible while completed events disappear', () => {
  const rows = [
    { id: 'resolved', status: 'resolved' }, { id: 'cancelled', status: 'cancelled' },
    { id: 'later', status: 'scheduled', next_action_at: '2026-09-27T13:00:00Z' },
    { id: 'unresolved', status: 'awaiting_acknowledgment' },
    { id: 'sooner', status: 'scheduled', next_action_at: '2026-09-27T12:00:00Z' },
  ];
  assert.deepEqual(activeFollowups(rows).map(row => row.id), ['sooner', 'later', 'unresolved']);
  assert.equal(rows.length, 5);
});
