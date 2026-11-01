# Reading and editing the voice-agent playbook

Start with [the HTML reading edition](ENTERPRISE_VOICE_AGENT_PLAYBOOK.html). It embeds all nine diagrams; use **View full size** and horizontal scrolling for dense figures. It needs no external renderer or network to display text and diagrams. Source/reference links still require the linked files or repository access.

Edit [the Markdown source](ENTERPRISE_VOICE_AGENT_PLAYBOOK.md). Mermaid definitions remain editable there. The HTML is a generated reading edition; regenerate it after content changes.

Run the synthetic learning exercise from the repository root:

```powershell
py -3.12 docs/examples/voice_adapter_lab.py
```

Expected final line: `PASS: synthetic integration checks`. It uses fake data and no external services. It teaches contracts and recovery, rather than implementing a complete voice server.

To regenerate HTML, use Node.js 22 or later, installed `marked` and `playwright` packages, and Microsoft Edge available to Playwright. The rendering helper can use an existing package directory:

```powershell
node docs/examples/render_playbook.mjs --dependencies <path-to-existing-node_modules>
```

Without `--dependencies`, it resolves packages using normal Node module resolution. Rendering fetches Mermaid 11.4.1 from jsDelivr at build time, validates all diagrams in a temporary headless browser, embeds SVGs, checks the full-size control and saves preview PNGs for visual review. The output HTML does not fetch that dependency when read. These are document tools; they do not start the application, query a database, dial or message anyone.

For sharing, send the HTML and editable Markdown with this guide, the learning exercise and the relative-linked supporting notes. Application-source links are pinned to revision `258c4bce11cdfb6ee50432e3f43009cabd7e51d7`; recipients need repository access. Update source revision links when the implementation baseline changes.

The [PDF edition](../output/pdf/Enterprise_Voice_Agent_Playbook.pdf) preserves the full narrative and includes page numbers and print-adapted diagrams. The booking sequence uses two landscape pages; the database relationships are split into three figures. Companion-file references are plain text in PDF so they do not expose workstation-specific file URLs; web references and internal navigation remain links. To regenerate it in the same rendering environment, run `node docs/examples/export_playbook_pdf.mjs --dependencies <path-to-existing-node_modules>`.
