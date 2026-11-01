// PDF layout derived from the existing editable handbook. Requires the same
// marked/playwright package environment as render_playbook.mjs, plus Edge.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const args = process.argv.slice(2);
const dependencyIndex = args.indexOf('--dependencies');
const require = createRequire(dependencyIndex >= 0
  ? path.resolve(args[dependencyIndex + 1], '../renderer.cjs') : import.meta.url);
const { chromium } = require('playwright');
const htmlPath = path.join(repo, 'docs/ENTERPRISE_VOICE_AGENT_PLAYBOOK.html');
const source = (await fs.readFile(path.join(repo, 'docs/ENTERPRISE_VOICE_AGENT_PLAYBOOK.md'), 'utf8')).replaceAll('\r\n','\n');
const definitions = [...source.matchAll(/^```mermaid\n([\s\S]*?)^```/gm)].map(match => match[1]);
if (definitions.length !== 9) throw new Error('Expected nine source diagrams');
const outputDirectory = path.join(repo, 'output/pdf');
await fs.mkdir(outputDirectory, { recursive:true });
const response = await fetch('https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js',
  { signal:AbortSignal.timeout(20000) });
if (!response.ok) throw new Error('Mermaid dependency unavailable');
const mermaidBundle = await response.text();
const browser = await chromium.launch({ channel:'msedge', headless:true });
try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil:'load' });
  await page.addScriptTag({ content:mermaidBundle });
  const diagrams = await page.evaluate(async definitions => {
    window.mermaid.initialize({ startOnLoad:false, securityLevel:'strict', theme:'neutral',
      themeVariables:{fontFamily:'Arial, sans-serif',fontSize:'18px'},
      flowchart:{htmlLabels:false,nodeSpacing:24,rankSpacing:32,useMaxWidth:true},
      er:{fontSize:18,useMaxWidth:true},
      sequence:{width:100,actorMargin:25,messageFontSize:17,noteFontSize:17,useMaxWidth:true} });
    const figures = [...document.querySelectorAll('figure.diagram')];
    for (let index=0; index<definitions.length; index++) {
      let source = definitions[index];
      if ([0,2,3,8].includes(index)) source = source.replace('flowchart LR', 'flowchart TB');
      if (index === 8) source = source
        .replace('Model and speech services','Model and<br/>speech services')
        .replace('Outbound calls and messaging','Outbound calls<br/>and messaging')
        .replace('Optional OTLP collector','Optional OTLP<br/>collector')
        .replace('Supabase Postgres','Supabase<br/>Postgres');
      if (index === 5) {
        const replacements = [
          ['Bound caller context and speech','Bound caller context<br/>and speech'],
          ['Actual available sessions via tool result','Actual available sessions<br/>via tool result'],
          ['Prepare selected patient/session offer','Prepare selected<br/>patient/session offer'],
          ['Validated offer and private signed token','Validated offer and<br/>private signed token'],
          ['Controlled readback audio and mark','Controlled readback<br/>audio and mark'],
          ['Classify and validate current proposal/turn','Classify and validate<br/>current proposal/turn'],
          ['Approval + booking + result in one transaction','Approval + booking + result<br/>in one transaction']
        ];
        for (const [from,to] of replacements) source = source.replace(from,to);
      }
      if (index === 5) {
        const lines = source.trim().split('\n');
        const participants = lines.filter(line=>line.trim().startsWith('participant'));
        const interactions = lines.filter(line=>!line.trim().startsWith('participant') && line.trim()!=='sequenceDiagram');
        const boundary = interactions.findIndex(line=>line.includes('Later explicit acceptance'));
        const phases = [interactions.slice(0,boundary),interactions.slice(boundary)];
        const heading = figures[index].previousElementSibling;
        if (heading?.tagName==='H3') heading.remove();
        for (let phase=0; phase<phases.length;phase++) {
          const definition = ['sequenceDiagram',...participants,...phases[phase]].join('\n');
          const {svg} = await window.mermaid.render(`pdf-sequence-${phase}`,definition);
          const figure=document.createElement('figure');figure.className='diagram sequence-landscape';
          figure.innerHTML=`<h3>${phase===0?'10.2 Worked booking sequence - discovery and readback':'Booking sequence - approval and commit'}</h3><div class="mermaid">${svg}</div><figcaption>Figure 6${phase===0?'a':'b'}. ${phase===0?'Discovery and controlled presentation':'Later approval and guarded commit'}</figcaption>`;
          figures[index].before(figure);
        }
        figures[index].remove();
      } else if (index === 6) {
        const lines = source.trim().split('\n').slice(1);
        const groups = [
          ['Clinic relationships', lines.filter(line => !/VOICE_|PERSONAL_/.test(line))],
          ['Voice operation evidence', lines.filter(line => /VOICE_/.test(line))],
          ['Personal Agent relationships', lines.filter(line => /PERSONAL_/.test(line))]
        ];
        for (let group=0;group<groups.length;group++) {
          let definition = 'erDiagram\n'+groups[group][1].join('\n');
          const names={ORGANIZATION_USERS:'Members',DOCTOR_ASSIGNMENTS:'Assignments',
            ORGANIZATIONS:'Organizations',APPOINTMENTS:'Appointments',CONTACT_PHONES:'ContactPhones',
            PATIENT_CONTACTS:'PatientContacts',CONTACTS:'Contacts',PATIENTS:'Patients',
            APPOINTMENT_SESSIONS:'Sessions',APPOINTMENT_CONTACT_PERMISSIONS:'AppointmentPermissions',
            PERSONAL_AGENT_PROFILES:'PersonalProfiles',PERSONAL_AGENT_TASKS:'PersonalTasks',
            PERSONAL_AGENT_FOLLOWUPS:'Followups',PERSONAL_AGENT_ATTEMPTS:'Attempts',
            VOICE_CALL_SESSIONS:'VoiceCallSessions',VOICE_OPERATION_RECORDS:'VoiceOperations'};
          for (const [full,short] of Object.entries(names)) definition=definition.replaceAll(full,short);
          const {svg} = await window.mermaid.render(`pdf-diagram-${index}-${group}`,definition);
          const figure = document.createElement('figure'); figure.className='diagram';
          figure.innerHTML=`<div class="mermaid">${svg}</div><figcaption>Figure 7${String.fromCharCode(97+group)}. ${groups[group][0]}${group===0?'<br>Short labels: Members = organization_users; Assignments = doctor_assignments;<br>Sessions = appointment_sessions; AppointmentPermissions = appointment_contact_permissions.':''}</figcaption>`;
          figures[index].before(figure);
        }
        figures[index].remove();
      } else {
        const {svg} = await window.mermaid.render(`pdf-diagram-${index}`,source);
        figures[index].querySelector('.mermaid').innerHTML=svg;
      }
    }
    document.querySelectorAll('.mermaid svg').forEach(svg => {
      svg.setAttribute('width',String(svg.viewBox.baseVal.width));
      svg.setAttribute('height',String(svg.viewBox.baseVal.height));
    });
    document.querySelectorAll('.diagram-toggle,script').forEach(node=>node.remove());
    document.querySelectorAll('main a[href]').forEach(link=>{
      const href=link.getAttribute('href');
      if (!href.startsWith('#') && !/^https?:/i.test(href)) {
        link.removeAttribute('href');link.classList.add('companion-reference');
      }
    });
    return document.querySelectorAll('figure.diagram').length;
  }, definitions);
  await page.addStyleTag({ content:`
    @page { size:A4; margin:15mm 16mm 19mm; }
    @page sequence { size:A4 landscape; margin:12mm 14mm 18mm; }
    body { background:white; font:10.5pt/1.43 Arial,sans-serif; color:#223346; }
    main { width:auto; max-width:none; margin:0; padding:0; }
    .edition { display:none; } h1 { font-size:25pt; line-height:1.15; }
    h2 { font-size:16pt; margin:22px 0 10px; break-after:avoid; }
    h3 { font-size:12pt; margin:16px 0 8px; break-after:avoid; }
    p,li { max-width:none; } p { margin:8px 0; } ul,ol { padding-left:20px; }
    aside { padding:11px 14px; margin:14px 0; break-inside:avoid; }
    table { display:table; width:100%; overflow:visible; font-size:8.8pt; line-height:1.32; margin:12px 0; table-layout:auto; }
    thead { display:table-header-group; } tbody { display:table-row-group; }
    th,td { padding:6px 7px; overflow-wrap:anywhere; } th {min-width:48px;overflow-wrap:normal;} tr { break-inside:avoid; }
    pre { font-size:8.3pt; line-height:1.38; padding:10px; white-space:pre-wrap; overflow-wrap:anywhere; overflow:visible; break-inside:avoid; }
    code { font-family:Consolas,monospace; font-size:.94em; }
    .diagram { padding:9px; margin:16px 0; break-inside:avoid; }
    .mermaid { overflow:visible; } .mermaid svg { width:auto!important; max-width:100%!important; max-height:190mm; height:auto; }
    .sequence-landscape {page:sequence;break-before:page;break-after:page;margin:0;padding:5px;}
    .sequence-landscape svg {max-height:157mm;}
    figcaption { font-size:8pt; padding-top:8px; }
    a { color:#175d95; text-decoration:none; } hr { margin:14px 0; }
    .companion-reference {color:inherit;}
  ` });
  await page.emulateMedia({media:'print'});
  await page.evaluate(()=>document.fonts.ready);
  const output = path.join(outputDirectory,'Enterprise_Voice_Agent_Playbook.pdf');
  await page.pdf({path:output,format:'A4',preferCSSPageSize:true,printBackground:true,
    displayHeaderFooter:true,headerTemplate:'<span></span>',
    footerTemplate:'<div style="font:8px Arial; color:#526375; width:100%; margin:0 16mm; display:flex; justify-content:space-between"><span>Enterprise Voice Agent Playbook · Version 1.1</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'});
  console.log(JSON.stringify({output,sourceDiagrams:definitions.length,printedFigures:diagrams}));
} finally { await browser.close(); }
