import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const compile = source => 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText).toString('base64');
const traceURL = compile(readFileSync(new URL('../src/presentation/trace.ts', import.meta.url),'utf8'));
const observatorySource = readFileSync(new URL('../src/components/Observatory.tsx', import.meta.url),'utf8');
const presentationSource = readFileSync(new URL('../src/components/PresentationPage.tsx', import.meta.url),'utf8');
const {rehearsal, readEventStream} = await import(traceURL);
const {appointmentState, signalFor, followStream, liveEventDwell} = await import(compile(readFileSync(new URL('../src/presentation/state.ts', import.meta.url),'utf8').replace("'./trace'",JSON.stringify(traceURL))));
test('booking fields survive result and final playback events',()=>{
 const state=appointmentState(rehearsal('booking'));
 assert.equal(state.outcome,'Confirmed'); assert.equal(state.details.doctor_name,'Dr Amit Kumar'); assert.equal(state.details.booking_reference,'DEMO-1042');
});
test('correction replaces offer and failure never confirms',()=>{
 assert.match(appointmentState(rehearsal('correction')).details.session_date,/Day after tomorrow/);
 assert.equal(appointmentState(rehearsal('failure')).outcome,'Operation failed');
});
test('cancellation and later failures override prior confirmation',()=>{
 const events=rehearsal('booking');
 assert.equal(appointmentState([...events,{kind:'committed',tool:'cancel_appointment',details:{status:'CANCELLED'}}]).outcome,'Cancelled');
 assert.equal(appointmentState([...events,{kind:'tool_failed'}]).outcome,'Operation failed');
});
test('signals follow observed directions and distinguish non-success states',()=>{
 assert.equal(signalFor({kind:'tool_completed'}).route,'result');
 assert.equal(signalFor({kind:'tool_started'}).route,'request');
 assert.equal(signalFor({kind:'playback_acknowledged'}).route,'outbound');
 assert.equal(signalFor({kind:'audio_transferred',direction:'input',details:{boundary:'gateway'}}).node,'gateway');
 assert.equal(signalFor({kind:'audio_transferred',direction:'output'}).route,'outbound');
 assert.equal(signalFor({kind:'database_completed'}).node,'database');
 assert.equal(signalFor({kind:'playback_interrupted'}).state,'interrupted');
 assert.equal(signalFor({kind:'correction'}).state,'correction');
 assert.equal(signalFor({stage:'consent'}).state,'waiting');
});
test('tool outcomes are scoped to the active backend operation',()=>{
 assert.match(observatorySource, /event\.operation_id === activeOperation/);
 assert.match(observatorySource, /operationEvents\.some\(event => event\.kind === 'committed'/);
 assert.doesNotMatch(observatorySource, /const failed = events\.some/);
});
test('live presentation pacing holds meaningful beats and catches up under backlog',()=>{
 assert.equal(liveEventDwell({kind:'tool_selected'}),1700);
 assert.equal(liveEventDwell({kind:'dialogue',speaker:'caller'}),1800);
 assert.equal(liveEventDwell({kind:'audio_transferred'}),380);
 assert.ok(liveEventDwell({kind:'tool_selected'},8)<liveEventDwell({kind:'tool_selected'}));
 assert.match(observatorySource,/Chosen by engine/);
 assert.match(presentationSource,/HEARD · PROCESSING/);
});
test('live pacing rapidly sheds noisy backlogs without skipping meaningful beats',()=>{
 assert.equal(liveEventDwell({kind:'audio_transferred'},30),70);
 assert.equal(liveEventDwell({kind:'response_fragment'},14),120);
 assert.equal(liveEventDwell({kind:'committed'},30),520);
});
test('SSE reader rejects a half-open stream after its heartbeat goes stale',async()=>{
 const response=new Response(new ReadableStream({start(){}}));
 await assert.rejects(readEventStream(response,()=>{},()=>{},20),/heartbeat timed out/);
});
test('SSE reconnect resumes cursor, ignores duplicates and stops at complete',async()=>{
 const original=globalThis.fetch, urls=[], received=[];
 globalThis.fetch=async url=>{urls.push(url); return new Response(urls.length===1 ? 'id: 1\ndata: {"sequence":1,"kind":"call_started"}\n\n' : 'data: {"sequence":1}\n\ndata: {"sequence":2,"kind":"call_ended"}\n\nevent: complete\ndata: {}\n\n');};
 try { await followStream('http://local/events?organization_id=test','test',new AbortController().signal,e=>received.push(e.sequence),()=>{}); assert.deepEqual(received,[1,2]); assert.match(urls[1],/after=1$/); assert.equal(urls.length,2); } finally { globalThis.fetch=original; }
});
test('live canvas contains no rehearsal-specific identity or booking fallbacks',()=>{
 for (const value of ['Aryan', 'Bibha', 'Dr Sweta', 'Hari Vidhya Clinic']) {
  assert.equal(observatorySource.includes(value) || presentationSource.includes(value), false, `${value} must not be a live fallback`);
 }
 assert.match(presentationSource, /clinicName = 'Geeta Medicine'/);
 assert.match(observatorySource, /Waiting for observed caller intent/);
});
test('live mode polls, auto-follows, and surfaces observer status',()=>{
 assert.match(presentationSource, /setInterval\(\(\) => void loadCalls\(\), 2500\)/);
 assert.match(presentationSource, /Call found · connecting to observed events/);
 assert.match(presentationSource, /active\?\.title \?\? status/);
 assert.match(presentationSource, /body\.calls\.filter\(call => !call\.ended\)/);
 assert.match(presentationSource, /call\.id === selectedCall && !call\.ended/);
 assert.match(presentationSource, /Replay call/);
 assert.match(presentationSource, /live-health/);
});
