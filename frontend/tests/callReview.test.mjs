import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const source = readFileSync(new URL('../src/lib/callReview.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022}}).outputText;
const {buildSpans, elapsed, operationOutcome, eventLabel} = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'));
const event = (sequence, event_type, metadata, duration_ms=null) => ({sequence, event_type, metadata, duration_ms, stage: '', occurred_at: '2026-01-01T00:00:00Z'});
test('nested queries remain correlated and do not add to tool duration', () => {
  const spans = buildSpans([
    event(1,'tool_started',{tool_invocation_id:'t1',tool:'search_availability',elapsed_ms:100}),
    event(2,'database_started',{tool_invocation_id:'t1',query_id:'q1',elapsed_ms:110}),
    event(3,'database_completed',{tool_invocation_id:'t1',query_id:'q1',elapsed_ms:130},20),
    event(4,'tool_completed',{tool_invocation_id:'t1',elapsed_ms:150},50),
  ]);
  assert.equal(spans.length,2);
  assert.equal(spans[1].parentId,spans[0].id);
  assert.equal(spans[0].duration,50);
});
test('legacy events never invent measured elapsed time or pair unrelated invocations', () => {
  const spans=buildSpans([event(1,'tool_started',{tool:'lookup_caller_family'}),event(2,'tool_completed',{},295)]);
  assert.equal(spans.length,2);
  assert.equal(spans[0].status,'Completion not captured');
  assert.equal(spans[1].start,null);
  assert.equal(elapsed(event(3,'call_started',{})),null);
});
test('a call with no persisted action does not imply task success', () => {
  assert.equal(operationOutcome([]),'Task outcome not established');
  assert.equal(operationOutcome([{status:'COMMITTED'},{status:'FAILED'}]),'1 committed · 1 failed');
});
test('transport directions are explicit without promising heard audio', () => {
  assert.equal(eventLabel(event(1,'audio_transferred',{direction:'output'})),'Agent audio sent to carrier');
  assert.match(eventLabel(event(2,'audio_transferred',{})),/unavailable/);
});

test('message execution links use exact captured IDs without nearby-turn guesses', async () => {
  const {linkedEvents}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
  const events=[event(1,'dialogue',{message_source_id:'m1',response_id:'r1'}),event(2,'tool_started',{response_id:'r1',tool_invocation_id:'t1'}),event(3,'dialogue',{message_source_id:'m2',caller_turn_id:2}),event(4,'tool_completed',{tool_invocation_id:'t1'})];
  assert.deepEqual(linkedEvents(events,'m1').map(e=>e.sequence),[1,2]);
  assert.deepEqual(linkedEvents(events,'missing'),[]);
});
test('noise grouping preserves original evidence and separates correlation boundaries', async () => {
  const {diagnosticGroups,eventIssue}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
  const events=[event(1,'playback_started',{response_id:'r1'}),event(2,'playback_started',{response_id:'r1'}),event(3,'playback_started',{response_id:'r2'}),event(4,'readback_failed',{failure_type:'TimeoutError'})];
  const groups=diagnosticGroups(events);
  assert.deepEqual(groups.map(g=>g.length),[2,1,1]);
  assert.deepEqual(groups.flat(),events);
  assert.equal(eventIssue(events[3]),true);
});
