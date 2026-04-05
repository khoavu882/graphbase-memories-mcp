/**
 * ctl/graph/graph.js — Unified graph visualization
 * D3 v7 force simulation with drag-to-pin, domain swim lanes, SSE live updates.
 *
 * File-mode (file://):  loads ../unified-graph.json via fetch, stores layout in localStorage
 * Server mode (http://): loads /api/graph, saves layout via POST /api/graph/layout, listens on /events SSE
 */
(function () {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────────────────

  const DOMAINS  = ['sync', 'workflow', 'agents', 'context'];
  /** Initial x-center of each domain's swim lane (1600px canvas) */
  const LANE_X   = { sync: 200, workflow: 570, agents: 1020, context: 1400 };
  const CANVAS   = { w: 1600, h: 960 };
  const LAYOUT_KEY  = 'ctl-graph-layout-v1';
  const DOMAIN_KEY  = 'ctl-graph-domains-v1';

  /** Base radius by node type (px in SVG coordinate space) */
  const RADIUS = {
    sync_target:   18,
    workflow:      18,
    agent:         14,
    sync_file:     10,
    workflow_step: 11,
    command:        9,
  };
  const R_DEFAULT = 10;

  // ── State ──────────────────────────────────────────────────────────────────

  let graphData     = null;   // { nodes[], edges[], meta }
  let simulation    = null;   // d3 forceSimulation
  let simLinks      = [];     // edge objects after D3 resolves source/target to node refs
  let dragBehavior  = null;   // d3.drag instance
  let selectedId    = null;   // currently selected node ID
  let searchTerm    = '';     // lowercased filter string
  // Load persisted domain filter state (5.3)
  const _savedDomains = (() => {
    try { return JSON.parse(localStorage.getItem(DOMAIN_KEY)); } catch (_) { return null; }
  })();
  const visibleDomains = new Set(
    Array.isArray(_savedDomains) ? _savedDomains : DOMAINS
  );

  // ── DOM refs ───────────────────────────────────────────────────────────────

  const svgEl     = document.getElementById('graph-svg');
  const viewport  = document.getElementById('viewport');
  const edgeLayer = document.getElementById('edge-layer');
  const nodeLayer = document.getElementById('node-layer');
  const lblLayer  = document.getElementById('label-layer');
  const statsEl   = document.getElementById('graph-stats');
  const searchEl  = document.getElementById('search-input');
  const sseEl     = document.getElementById('sse-status');
  const dtTitle   = document.getElementById('details-title');
  const dtSub     = document.getElementById('details-subtitle');
  const dtBody    = document.getElementById('details-body');
  const logPanel  = document.getElementById('log-panel');
  const logOutput = document.getElementById('log-output');
  const logTitle  = document.getElementById('log-panel-title');

  // ── Utilities ──────────────────────────────────────────────────────────────

  function r(node)      { return RADIUS[node.type] || R_DEFAULT; }
  function lx(domain)   { return LANE_X[domain] || CANVAS.w / 2; }
  function esc(s)       { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function fetchGraph() {
    // file:// mode: load directly from relative path (no CORS issue for same-origin)
    if (window.location.protocol === 'file:') {
      const res = await fetch('../unified-graph.json');
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json();
    }
    // HTTP mode: prefer server API (Phase 4+); fall back to static file for simple dev servers
    for (const url of ['/api/graph', '../unified-graph.json']) {
      try {
        const res = await fetch(url);
        if (res.ok) return res.json();
      } catch (_) { /* try next */ }
    }
    throw new Error('Graph unavailable — run ./ctl.sh build, then ./ctl.sh graph');
  }

  // ── Layout helpers ─────────────────────────────────────────────────────────

  /** Spread nodes into vertical swim lanes by domain. Called on first load + reset. */
  function assignLanePositions(nodes) {
    const byDomain = {};
    DOMAINS.forEach(d => (byDomain[d] = []));
    nodes.forEach(n => (byDomain[n.domain] || (byDomain[n.domain] = [])).push(n));

    Object.entries(byDomain).forEach(([domain, group]) => {
      const cx = lx(domain);
      const count = group.length;
      group.forEach((node, i) => {
        const spread = Math.min(740, count * 52);
        const top    = (CANVAS.h - spread) / 2;
        const y      = count <= 1
          ? CANVAS.h / 2
          : top + (spread / (count - 1)) * i;
        node.x = cx + (Math.random() - 0.5) * 50;
        node.y = y  + (Math.random() - 0.5) * 20;
      });
    });
  }

  /** Restore drag-pinned positions from localStorage (or server-side state.json in Phase 4). */
  function loadSavedPositions(nodes) {
    let saved;
    try { saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}'); }
    catch (_) { return; }

    nodes.forEach(node => {
      const pos = saved[node.id];
      if (pos && typeof pos.x === 'number' && typeof pos.y === 'number') {
        node.fx = pos.x;
        node.fy = pos.y;
        node.x  = pos.x;
        node.y  = pos.y;
      }
    });
  }

  /** Persist a node's position after drag-end. */
  function savePosition(nodeId, x, y) {
    // localStorage (always, for file:// compatibility)
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}'); } catch (_) {}
    saved[nodeId] = { x: Math.round(x), y: Math.round(y) };
    try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(saved)); } catch (_) {}

    // POST to server when running over HTTP (Phase 4+)
    if (window.location.protocol !== 'file:') {
      fetch('/api/graph/layout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nodeId, x: Math.round(x), y: Math.round(y) }),
      }).catch(() => {});
    }
  }

  // ── Force simulation ───────────────────────────────────────────────────────

  function buildSimulation(nodes, edges) {
    // Filter edges whose source/target node doesn't exist — D3 forceLink throws on missing IDs
    const nodeIds = new Set(nodes.map(n => n.id));
    const valid   = edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
    if (valid.length < edges.length) {
      console.warn(`[ctl/graph] Skipped ${edges.length - valid.length} edge(s) with unresolved nodes`);
    }

    // Build link objects; D3 resolves source/target IDs → node refs via forceLink(.id())
    const links = valid.map(e => ({ source: e.source, target: e.target, type: e.type }));

    const sim = d3.forceSimulation(nodes)
      .force('link',     d3.forceLink(links).id(n => n.id).distance(65).strength(0.25))
      .force('charge',   d3.forceManyBody().strength(-200).distanceMax(400))
      .force('collide',  d3.forceCollide(n => r(n) + 16))
      // Domain lane force: pull nodes toward their lane's x-center
      .force('lane-x',   d3.forceX(n => lx(n.domain)).strength(0.5))
      // Soft vertical centering so the graph doesn't drift off screen
      .force('center-y', d3.forceY(CANVAS.h / 2).strength(0.06))
      .alphaDecay(0.018)
      .velocityDecay(0.4)
      .on('tick', renderGraph);

    // After D3 calls forceLink.initialize(), links are resolved; capture the array.
    simLinks = links;

    return sim;
  }

  // ── Drag ───────────────────────────────────────────────────────────────────

  function buildDrag() {
    return d3.drag()
      .on('start', (event) => {
        if (!event.active && simulation) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
      })
      .on('drag', (event) => {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
      })
      .on('end', (event) => {
        if (!event.active && simulation) simulation.alphaTarget(0);
        // Keep node pinned at dropped location; save the position.
        savePosition(event.subject.id, event.subject.fx, event.subject.fy);
      });
  }

  // ── Zoom / pan ─────────────────────────────────────────────────────────────

  function bindZoom() {
    const zoom = d3.zoom()
      .scaleExtent([0.25, 3.5])
      .filter(event => {
        // Wheel: always zoom. Click-drag: pan only on SVG background (not on nodes).
        if (event.type === 'wheel') return true;
        if (event.type === 'dblclick') return false;
        return !event.target.closest('.node');
      })
      .on('start', () => svgEl.classList.add('dragging'))
      .on('zoom',  event => viewport.setAttribute('transform', event.transform.toString()))
      .on('end',   () => svgEl.classList.remove('dragging'));

    d3.select(svgEl).call(zoom).on('dblclick.zoom', null);
  }

  // ── Rendering ─────────────────────────────────────────────────────────────

  /** Compute the set of currently visible node IDs based on domain filters + search. */
  function visibleSet() {
    const vis = new Set();
    graphData.nodes.forEach(n => {
      if (!visibleDomains.has(n.domain)) return;
      if (searchTerm && !n.label.toLowerCase().includes(searchTerm)) return;
      vis.add(n.id);
    });
    return vis;
  }

  function nodeClass(n) {
    return [
      'node',
      `type-${n.type}`,
      `domain-${n.domain}`,
      n.id === selectedId ? 'node-selected' : '',
    ].filter(Boolean).join(' ');
  }

  function renderGraph() {
    if (!graphData || !dragBehavior) return;

    const vis = visibleSet();

    // ── Edges ────────────────────────────────────────────────────────────────
    d3.select(edgeLayer)
      .selectAll('line.edge')
      .data(
        simLinks.filter(e => {
          const sid = typeof e.source === 'object' ? e.source.id : e.source;
          const tid = typeof e.target === 'object' ? e.target.id : e.target;
          return vis.has(sid) && vis.has(tid);
        }),
        e => {
          const s = typeof e.source === 'object' ? e.source.id : e.source;
          const t = typeof e.target === 'object' ? e.target.id : e.target;
          return `${s}→${t}`;
        }
      )
      .join('line')
      .attr('class', e => `edge edge-type-${e.type}`)
      .attr('x1', e => (typeof e.source === 'object' ? e.source.x : 0) ?? 0)
      .attr('y1', e => (typeof e.source === 'object' ? e.source.y : 0) ?? 0)
      .attr('x2', e => (typeof e.target === 'object' ? e.target.x : 0) ?? 0)
      .attr('y2', e => (typeof e.target === 'object' ? e.target.y : 0) ?? 0);

    // ── Node groups ───────────────────────────────────────────────────────────
    const visNodes = graphData.nodes.filter(n => vis.has(n.id));

    d3.select(nodeLayer)
      .selectAll('g.node')
      .data(visNodes, n => n.id)
      .join(
        enter => {
          const g = enter.append('g')
            .attr('class', nodeClass)
            .call(dragBehavior)
            .on('click', (event, n) => { event.stopPropagation(); selectNode(n); });
          g.append('circle').attr('class', 'node-state-ring').attr('r', n => r(n) + 4);
          g.append('circle').attr('class', 'node-circle').attr('r', r);
          return g;
        },
        update => update.attr('class', nodeClass),
        exit   => exit.remove()
      )
      .attr('transform', n => `translate(${n.x ?? 0},${n.y ?? 0})`);

    // ── Labels ────────────────────────────────────────────────────────────────
    d3.select(lblLayer)
      .selectAll('text.node-label')
      .data(visNodes, n => n.id)
      .join(
        enter  => enter.append('text').attr('class', 'node-label'),
        update => update,
        exit   => exit.remove()
      )
      .attr('x', n => (n.x ?? 0) + r(n) + 5)
      .attr('y', n => (n.y ?? 0) + 4)
      .text(n => n.label);
  }

  // ── Selection + detail panel ───────────────────────────────────────────────

  function selectNode(node) {
    selectedId = node.id;
    renderGraph();
    renderDetails(node);
    document.dispatchEvent(new CustomEvent('ctl:node-selected', { detail: node }));
  }

  function clearSelection() {
    if (!selectedId) return;
    selectedId = null;
    renderGraph();
    dtTitle.textContent = 'Select a node';
    dtSub.textContent   = 'Click any node to inspect it.';
    dtBody.innerHTML    = '<div class="empty-state">Use the graph canvas to explore nodes.</div>';
  }

  function renderDetails(node) {
    dtTitle.textContent = node.label;
    dtSub.textContent   = `${node.type.replace(/_/g, ' ')} · ${node.domain}`;

    // Metadata rows from node.meta
    const metaRows = Object.entries(node.meta || {})
      .filter(([, v]) => v !== '' && v !== null && !(Array.isArray(v) && v.length === 0))
      .map(([k, v]) => {
        const val = Array.isArray(v) ? v.join(', ') : String(v);
        return `<dt>${esc(k)}</dt><dd>${esc(val)}</dd>`;
      })
      .join('');

    // Connected neighbors from simLinks
    const conns = [];
    simLinks.forEach(e => {
      const src = typeof e.source === 'object' ? e.source : null;
      const tgt = typeof e.target === 'object' ? e.target : null;
      if (src && src.id === node.id && tgt) conns.push({ peer: tgt, rel: e.type, dir: '→' });
      if (tgt && tgt.id === node.id && src) conns.push({ peer: src, rel: e.type, dir: '←' });
    });

    const connHtml = conns.length
      ? `<section>
           <h3>Connections (${conns.length})</h3>
           <div class="details-list">
             ${conns.map(({ peer, rel, dir }) =>
               `<div class="details-list-item">
                 <strong>${esc(peer.label)}</strong><br>
                 <span class="muted">${esc(dir)} ${esc(rel.replace(/_/g,' '))} · ${esc(peer.type.replace(/_/g,' '))}</span>
               </div>`
             ).join('')}
           </div>
         </section>`
      : '';

    // Run panel — only shown for workflow-type nodes when connected to a server
    const runHtml = (node.type === 'workflow' && window.location.protocol !== 'file:')
      ? `<section class="run-section">
           <h3>Run Workflow</h3>
           <div class="run-field">
             <label for="run-feature-request">feature_request</label>
             <textarea id="run-feature-request" class="run-textarea"
               placeholder="Describe the feature or task to deliver…"
               rows="4"></textarea>
           </div>
           <button id="run-workflow-btn" class="btn-run" data-workflow-id="${esc(node.id)}">
             ▶ Run
           </button>
           <div id="run-output" class="run-output" hidden></div>
         </section>`
      : '';

    dtBody.innerHTML = `
      ${metaRows ? `<section><h3>Metadata</h3><dl>${metaRows}</dl></section>` : ''}
      ${connHtml}
      ${runHtml}
    `;

    // Wire the Run button if rendered
    if (runHtml) {
      document.getElementById('run-workflow-btn').addEventListener('click', runWorkflow);
    }
  }

  // ── Workflow execution ──────────────────────────────────────────────────────

  function runWorkflow(event) {
    const btn        = event.currentTarget;
    const workflowId = btn.dataset.workflowId;
    const textarea   = document.getElementById('run-feature-request');
    const outputEl   = document.getElementById('run-output');
    const request    = textarea.value.trim();

    if (!request) {
      textarea.focus();
      textarea.classList.add('run-textarea--error');
      textarea.addEventListener('input', () => textarea.classList.remove('run-textarea--error'), { once: true });
      return;
    }

    btn.disabled        = true;
    btn.textContent     = '⏳ Running…';
    outputEl.hidden     = false;
    outputEl.textContent = '';
    outputEl.classList.remove('run-output--error', 'run-output--done');

    fetch('/api/workflow', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ workflow_id: workflowId, feature_request: request }),
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) throw new Error(data.error);
        // Output lines arrive via existing SSE 'log' events; append them.
        outputEl.textContent = `[started] ${data.workflow_id || workflowId}\n`;
      })
      .catch(err => {
        outputEl.textContent = `Error: ${err.message}`;
        outputEl.classList.add('run-output--error');
        btn.disabled    = false;
        btn.textContent = '▶ Run';
      });
  }

  // ── Filters + controls ─────────────────────────────────────────────────────

  function bindControls() {
    // 5.3 — Domain filter checkboxes + localStorage persistence
    document.querySelectorAll('[data-domain]').forEach(cb => {
      // Apply saved state to checkbox appearance
      cb.checked = visibleDomains.has(cb.dataset.domain);

      cb.addEventListener('change', () => {
        if (cb.checked) visibleDomains.add(cb.dataset.domain);
        else visibleDomains.delete(cb.dataset.domain);
        // Persist to localStorage so state survives page reload
        try { localStorage.setItem(DOMAIN_KEY, JSON.stringify([...visibleDomains])); } catch (_) {}
        renderGraph();
      });
    });

    // Search
    searchEl.addEventListener('input', () => {
      searchTerm = searchEl.value.trim().toLowerCase();
      renderGraph();
    });

    // Reset layout
    document.getElementById('btn-reset-layout').addEventListener('click', () => {
      localStorage.removeItem(LAYOUT_KEY);
      graphData.nodes.forEach(n => { delete n.fx; delete n.fy; });
      assignLanePositions(graphData.nodes);
      if (simulation) simulation.nodes(graphData.nodes).alpha(0.8).restart();
    });

    // Click SVG background → deselect
    d3.select(svgEl).on('click.deselect', clearSelection);

    // 5.1 — Sync action buttons (server mode only)
    if (window.location.protocol !== 'file:') {
      document.querySelectorAll('.btn-sync').forEach(btn => {
        btn.addEventListener('click', () => runSyncOp(btn));
      });
    } else {
      // Hide sync panel in file:// mode — no server available
      const syncActions = document.getElementById('sync-actions');
      if (syncActions) syncActions.hidden = true;
    }

    // Log panel close button
    const closeBtn = document.getElementById('log-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => {
        if (logPanel) logPanel.hidden = true;
        if (logOutput) logOutput.textContent = '';
      });
    }
  }

  // ── Sync operation (5.1) ───────────────────────────────────────────────────

  function runSyncOp(btn) {
    const op      = btn.dataset.op;
    const targets = btn.dataset.targets ? btn.dataset.targets.split(',') : [];

    // Disable all sync buttons during the operation
    document.querySelectorAll('.btn-sync').forEach(b => { b.disabled = true; });

    // Show log panel
    if (logPanel)  logPanel.hidden  = false;
    if (logOutput) logOutput.textContent = `[sync] ${op}${targets.length ? ' → ' + targets.join(', ') : ''}\n`;
    if (logTitle)  logTitle.textContent  = `Sync — ${op}`;

    fetch('/api/sync', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ op, targets }),
    })
      .then(res => res.json())
      .then(data => {
        if (data.error) throw new Error(data.error);
        // Output streams via SSE 'log' events into logOutput
      })
      .catch(err => {
        if (logOutput) logOutput.textContent += `\nError: ${err.message}`;
        document.querySelectorAll('.btn-sync').forEach(b => { b.disabled = false; });
      });
  }

  // ── SSE live updates (Phase 4+) ────────────────────────────────────────────

  function bindSSE() {
    if (window.location.protocol === 'file:') return; // no server in file:// mode

    const es = new EventSource('/events');
    es.onopen  = () => { sseEl.textContent = 'Live'; };
    es.onerror = () => { sseEl.textContent = ''; };

    es.addEventListener('graph-updated', async () => {
      try {
        const data = await fetchGraph();
        reinitGraph(data);
        sseEl.textContent = 'Live — refreshed';
        setTimeout(() => { sseEl.textContent = 'Live'; }, 2500);
      } catch (_) {}
    });

    // Route log lines to whichever output panel is currently active.
    // Priority: workflow run-output (if visible) → shared log panel.
    es.addEventListener('log', (e) => {
      try {
        const { line } = JSON.parse(e.data);
        const runOut = document.getElementById('run-output');
        if (runOut && !runOut.hidden) {
          runOut.textContent += line + '\n';
          runOut.scrollTop = runOut.scrollHeight;
        } else if (logPanel && !logPanel.hidden && logOutput) {
          logOutput.textContent += line + '\n';
          logOutput.scrollTop = logOutput.scrollHeight;
        }
      } catch (_) {}
    });

    // Workflow run finished
    es.addEventListener('workflow-done', (e) => {
      const outputEl = document.getElementById('run-output');
      const btn      = document.getElementById('run-workflow-btn');
      if (outputEl) {
        try {
          const { exit_code } = JSON.parse(e.data);
          outputEl.textContent += exit_code === 0
            ? '\n[done] Workflow completed successfully.'
            : `\n[error] Workflow exited with code ${exit_code}.`;
          outputEl.classList.toggle('run-output--error', exit_code !== 0);
          outputEl.classList.toggle('run-output--done',  exit_code === 0);
          outputEl.scrollTop = outputEl.scrollHeight;
        } catch (_) {}
      }
      if (btn) { btn.disabled = false; btn.textContent = '▶ Run'; }
    });

    // Sync operation done / error (re-enable buttons)
    const _restoreSyncBtns = () => {
      document.querySelectorAll('.btn-sync').forEach(b => { b.disabled = false; });
    };

    es.addEventListener('done', (e) => {
      _restoreSyncBtns();
      if (logPanel && !logPanel.hidden && logOutput) {
        try {
          const { exit_code } = JSON.parse(e.data);
          logOutput.textContent += exit_code === 0
            ? '\n[done] Completed successfully.'
            : `\n[error] Exited with code ${exit_code}.`;
          logOutput.scrollTop = logOutput.scrollHeight;
        } catch (_) {}
      }
    });

    es.addEventListener('error', (e) => {
      _restoreSyncBtns();
      if (logPanel && !logPanel.hidden && logOutput) {
        try {
          const { exit_code } = JSON.parse(e.data);
          logOutput.textContent += `\n[error] Exited with code ${exit_code}.`;
          logOutput.scrollTop = logOutput.scrollHeight;
        } catch (_) {}
      }
    });

    es.addEventListener('workflow-error', (e) => {
      const outputEl = document.getElementById('run-output');
      const btn      = document.getElementById('run-workflow-btn');
      if (outputEl) {
        try { outputEl.textContent += `\n[error] ${JSON.parse(e.data).message || 'Unknown error'}`; } catch (_) {}
        outputEl.classList.add('run-output--error');
        outputEl.scrollTop = outputEl.scrollHeight;
      }
      if (btn) { btn.disabled = false; btn.textContent = '▶ Run'; }
    });
  }

  // ── Stats bar ──────────────────────────────────────────────────────────────

  function renderStats(meta) {
    const c = meta.counts;
    const byDomain = Object.entries(c.by_domain || {})
      .filter(([, n]) => n > 0)
      .map(([d, n]) => `${d}:${n}`)
      .join('  ');
    statsEl.textContent = `${c.nodes} nodes · ${c.edges} edges   ${byDomain}`;
  }

  // ── Graph init ─────────────────────────────────────────────────────────────

  function reinitGraph(data) {
    graphData = data;

    // Assign initial lane positions, then overlay saved drag positions
    assignLanePositions(data.nodes);
    loadSavedPositions(data.nodes);

    // Build drag before simulation so it's ready when first tick fires
    dragBehavior = buildDrag();

    // Build simulation (captures resolved simLinks internally)
    if (simulation) simulation.stop();
    simulation = buildSimulation(data.nodes, data.edges);

    renderStats(data.meta);
    // First render happens via simulation tick, but trigger one now for quick display
    renderGraph();
    document.dispatchEvent(new CustomEvent('ctl:data-loaded', { detail: data }));
  }

  // ── Boot ───────────────────────────────────────────────────────────────────

  async function init() {
    try {
      bindZoom();
      const data = await fetchGraph();
      reinitGraph(data);
      bindControls();
      bindSSE();
      document.addEventListener('ctl:select-entity', (e) => {
        const node = graphData && graphData.nodes.find(n => n.id === e.detail);
        if (node) selectNode(node);
      });
    } catch (err) {
      statsEl.textContent = `Failed to load graph: ${err.message}`;
      console.error('[ctl/graph]', err);
    }
  }

  init();
})();
