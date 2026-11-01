// Generates an HTML reading edition and verifies Mermaid diagrams in a browser.
// Needs marked and playwright. --dependencies points at an existing node_modules.
// Mermaid 11.4.1 is fetched by Node; the final HTML embeds SVGs
// and needs no external JavaScript/CDN to read. Markdown stays editable.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const args = process.argv.slice(2);
const dependencyIndex = args.indexOf('--dependencies');
const require = createRequire(dependencyIndex >= 0
  ? path.resolve(args[dependencyIndex + 1], '../renderer.cjs') : import.meta.url);
const { marked } = await import(pathToFileURL(require.resolve('marked')).href);
const { chromium } = require('playwright');
const source = path.join(root, 'ENTERPRISE_VOICE_AGENT_PLAYBOOK.md');
const output = path.join(root, 'ENTERPRISE_VOICE_AGENT_PLAYBOOK.html');
const markdown = await fs.readFile(source, 'utf8');
const sourceHash = createHash('sha256').update(markdown).digest('hex');
const escape = text => text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
let diagramCount = 0;
const renderer = new marked.Renderer();
renderer.code = ({ text, lang }) => lang === 'mermaid'
  ? `<figure class="diagram"><div class="mermaid">${escape(text)}</div><figcaption>Figure ${++diagramCount}</figcaption></figure>`
  : `<pre><code class="language-${escape(lang || '')}">${escape(text)}</code></pre>`;
const body = marked.parse(markdown, { renderer, gfm: true });
const mermaidResponse = await fetch('https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js',
  { signal:AbortSignal.timeout(20000) });
if (!mermaidResponse.ok) throw new Error(`Mermaid download: ${mermaidResponse.status}`);
const mermaidBundle = await mermaidResponse.text();
const css = `
:root { color-scheme: light; --ink:#223346; --muted:#526375; --line:#d8e0e7; }
* { box-sizing:border-box; } body { margin:0; background:#edf1f5; color:var(--ink); font:16px/1.65 system-ui, sans-serif; }
main { max-width:1080px; margin:32px auto; padding:55px 62px; background:white; }
h1 { font-size:2.25rem; line-height:1.15; } h2 { margin:2.8rem 0 1rem; font-size:1.6rem; line-height:1.3; color:#163a5b; }
h3 { margin-top:1.8rem; font-size:1.17rem; } p,li { max-width:85ch; } a { color:#175d95; text-underline-offset:3px; }
aside { margin:24px 0; padding:16px 20px; background:#f1f6fa; border-left:4px solid #397395; }
table { display:block; width:100%; overflow-x:auto; border-collapse:collapse; margin:20px 0; font-size:.9rem; }
th,td { text-align:left; vertical-align:top; padding:11px 13px; border:1px solid var(--line); } th { background:#eaf1f7; }
code { font: .88em/1.5 Consolas,monospace; } pre { padding:18px; background:#f4f6f8; border:1px solid var(--line); overflow-x:auto; white-space:pre; }
hr { border:0; border-top:1px solid var(--line); margin:28px 0; } .diagram { margin:28px 0; padding:18px 10px; border:1px solid var(--line); }
.mermaid { overflow-x:auto; text-align:center; } .mermaid svg { display:block; margin:auto; max-width:100%; height:auto; }
figcaption { text-align:center; color:var(--muted); font-size:.8rem; padding-top:12px; } .edition { color:var(--muted); font-size:.82rem; }
.diagram-toggle { display:block; margin:12px auto 0; padding:6px 12px; border:1px solid #96aec2; background:#f1f6fa; color:#163a5b; cursor:pointer; }
@media(max-width:700px){main{margin:0;padding:24px 18px;}body{font-size:15px;}h1{font-size:1.8rem;}}
@media print{body{background:white;}main{margin:0;padding:0;max-width:none;}h2,h3{break-after:avoid;}figure,pre,tr{break-inside:avoid;}a{color:inherit;}table{overflow:visible;}}
`;
const skeleton = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="document-source-sha256" content="${sourceHash}"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Enterprise Voice Agent Playbook</title><style>${css}</style></head><body><main><p class="edition">Reading edition · generated from editable Markdown · 5 October 2026</p>${body}</main></body></html>`;
const server = http.createServer((_request, response) => {
  response.writeHead(200, { 'Content-Type':'text/html; charset=utf-8' });
  response.end(skeleton);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({ channel:'msedge', headless:true });
  const page = await browser.newPage({ viewport:{ width:1400, height:1000 } });
  await page.goto(`http://127.0.0.1:${server.address().port}`, { waitUntil:'load' });
  await page.addScriptTag({ content:mermaidBundle });
  const result = await page.evaluate(async () => {
    const mermaid = window.mermaid;
    mermaid.initialize({ startOnLoad:false, securityLevel:'strict', theme:'default',
      themeVariables:{ fontFamily:'Arial, sans-serif', fontSize:'17px' },
      flowchart:{ htmlLabels:false, useMaxWidth:true }, sequence:{ useMaxWidth:true } });
    const figures = [...document.querySelectorAll('.mermaid')];
    const errors = [];
    for (let index=0; index<figures.length; index++) {
      try {
        const { svg } = await mermaid.render(`diagram-${index}`, figures[index].textContent);
        figures[index].innerHTML = svg;
        const graphic = figures[index].querySelector('svg');
        graphic.dataset.nativeWidth = graphic.viewBox.baseVal.width;
        figures[index].tabIndex = 0;
        figures[index].setAttribute('aria-label',`Figure ${index+1}; scroll horizontally when expanded`);
        const button = document.createElement('button');
        button.className = 'diagram-toggle'; button.type = 'button';
        button.textContent = 'View full size'; button.setAttribute('aria-pressed','false');
        figures[index].parentElement.appendChild(button);
      } catch(error) { errors.push({ index:index+1, message:String(error) }); }
    }
    return { diagrams:figures.length, errors };
  });
  if (result.errors.length) throw new Error(JSON.stringify(result));
  await page.evaluate(() => document.querySelectorAll('script').forEach(script => script.remove()));
  await page.addScriptTag({ content:`function initializeDiagramControls() {
    document.querySelectorAll('.diagram-toggle').forEach(button => {
    button.addEventListener('click', () => {
      const svg = button.parentElement.querySelector('svg');
      const expanded = button.getAttribute('aria-pressed') !== 'true';
      svg.style.width = expanded ? svg.dataset.nativeWidth + 'px' : '100%';
      svg.style.maxWidth = expanded ? 'none' : '100%';
      button.setAttribute('aria-pressed', String(expanded));
      button.textContent = expanded ? 'Fit to page' : 'View full size';
    });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeDiagramControls);
  } else { initializeDiagramControls(); }` });
  await page.locator('.diagram-toggle').first().click();
  if (await page.locator('.diagram-toggle').first().getAttribute('aria-pressed') !== 'true')
    throw new Error('Diagram full-size control failed');
  await page.locator('.diagram-toggle').first().click();
  await fs.writeFile(output, await page.content(), 'utf8');
  await page.goto(pathToFileURL(output).href, { waitUntil:'load' });
  await page.locator('.diagram-toggle').first().click();
  if (await page.locator('.diagram-toggle').first().getAttribute('aria-pressed') !== 'true')
    throw new Error('Offline HTML enlargement control failed');
  await page.locator('.diagram-toggle').first().click();
  const screenshot = path.join(root, 'voice-playbook-preview.png');
  await page.screenshot({ path:screenshot });
  const screenshots = [];
  for (let index=0; index<diagramCount; index++) {
    const file = path.join(root, `voice-playbook-diagram-${index+1}.png`);
    await page.locator('figure.diagram').nth(index).screenshot({ path:file });
    screenshots.push(path.basename(file));
  }
  console.log(JSON.stringify({ output:path.basename(output), sourceHash, ...result, screenshots }));
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
