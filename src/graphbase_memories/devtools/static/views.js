/**
 * ctl/graph/views.js — Context Navigator list views
 * Tab routing + entity list views for Bounded Contexts, Services, Features, Databases, Memories.
 *
 * Communicates with graph.js via CustomEvents (no shared globals):
 *   graph.js → views.js : 'ctl:data-loaded'   { detail: graphData }
 *   graph.js → views.js : 'ctl:node-selected'  { detail: node }
 *   views.js → graph.js : 'ctl:select-entity'  { detail: nodeId }
 */
(function () {
  'use strict';

  // ── Constants ────────────────────────────────────────────────────────────────

  const VIEW_KEY    = 'ctl-active-view-v1';
  const VALID_VIEWS = ['graph', 'overview', 'bounded-contexts', 'services', 'features', 'databases', 'memories', 'episodic'];

  // ── State ────────────────────────────────────────────────────────────────────

  let ctxNodes  = null;   // nodes where domain === 'context', set on ctl:data-loaded
  let memories  = null;   // memories.json content, loaded lazily on first Memories tab open
  let activeView = 'graph';
  let selectedId = null;  // currently selected entity node ID

  let activeServiceBCFilter     = null;   // null = show all bounded contexts
  let activeFeatureStatusFilter = null;   // null = show all statuses

  // ── Helpers ──────────────────────────────────────────────────────────────────

  function nodesByType(type) {
    return (ctxNodes || []).filter(n => n.type === type);
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function panel(view) {
    return document.querySelector(`.view-panel[data-view="${view}"]`);
  }

  // ── Tab routing ──────────────────────────────────────────────────────────────

  function switchView(name) {
    if (!VALID_VIEWS.includes(name)) name = 'graph';
    activeView = name;
    try { localStorage.setItem(VIEW_KEY, name); } catch (_) {}

    document.querySelectorAll('.view-tab').forEach(tab => {
      const active = tab.dataset.view === name;
      tab.setAttribute('aria-selected', active ? 'true' : 'false');
      tab.classList.toggle('view-tab--active', active);
    });

    document.querySelectorAll('.view-panel').forEach(p => {
      p.hidden = p.dataset.view !== name;
    });

    // Show/hide graph-only toolbar controls
    const isGraph  = name === 'graph';
    const legend   = document.getElementById('graph-legend');
    const resetBtn = document.getElementById('btn-reset-layout');
    if (legend)   legend.hidden   = !isGraph;
    if (resetBtn) resetBtn.hidden = !isGraph;

    renderCurrentView();
  }

  function renderCurrentView() {
    if (!ctxNodes && activeView !== 'graph' && activeView !== 'memories' && activeView !== 'episodic') {
      const p = panel(activeView);
      if (p && !p.innerHTML.trim()) {
        p.innerHTML = '<div class="list-empty">Loading graph data…</div>';
      }
      return;
    }
    switch (activeView) {
      case 'overview':         renderOverview();        break;
      case 'bounded-contexts': renderBoundedContexts(); break;
      case 'services':         renderServices();        break;
      case 'features':         renderFeatures();        break;
      case 'databases':        renderDatabases();       break;
      case 'memories':         renderMemories();        break;
      case 'episodic':         renderEpisodic();        break;
    }
  }

  // ── Overview ─────────────────────────────────────────────────────────────────

  function renderOverview() {
    const p = panel('overview');
    if (!p) return;

    const counts = [
      { num: nodesByType('bounded_context').length, label: 'Bounded Contexts', view: 'bounded-contexts' },
      { num: nodesByType('service').length,         label: 'Services',          view: 'services' },
      { num: nodesByType('feature').length,         label: 'Features',          view: 'features' },
      { num: nodesByType('database').length,        label: 'Databases',         view: 'databases' },
    ];

    const statsHTML = counts.map(s => `
      <div class="stat-card" data-target-view="${esc(s.view)}" tabindex="0" role="button">
        <div class="stat-card-num">${s.num}</div>
        <div class="stat-card-label">${esc(s.label)}</div>
      </div>
    `).join('');

    let ctxCardHTML = '';
    const projectCtx = memories && memories.entries && memories.entries.find(e => e.key === 'project/context');
    if (projectCtx) {
      const overviewLine = projectCtx.content.split('\n').find(l => /^Overview:/i.test(l));
      const overview     = overviewLine ? overviewLine.replace(/^Overview:\s*/i, '') : projectCtx.content.split('\n').find(l => l.trim()) || '';
      ctxCardHTML = `
        <div class="overview-context-card">
          <p class="overview-context-title">Project Context</p>
          <p class="overview-context-text">${esc(overview)}</p>
        </div>
      `;
    } else {
      ctxCardHTML = `
        <div class="overview-context-card">
          <p class="overview-context-title">Project Context</p>
          <p class="overview-context-text" style="color:var(--muted);font-size:0.82rem">
            No project context loaded yet.<br>
            Run <code style="font-family:monospace">/do:save --type learnings</code> to seed it.
          </p>
        </div>
      `;
    }

    p.innerHTML = `<div class="overview-stats">${statsHTML}</div>${ctxCardHTML}`;

    p.querySelectorAll('.stat-card').forEach(card => {
      card.addEventListener('click', () => switchView(card.dataset.targetView));
      card.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); switchView(card.dataset.targetView); }
      });
    });

    // Try to load memories in background for the context card
    if (!memories) {
      fetchMemories().then(data => {
        memories = data;
        if (activeView === 'overview') renderOverview();
      });
    }
  }

  // ── Bounded Contexts ─────────────────────────────────────────────────────────

  function renderBoundedContexts() {
    const p = panel('bounded-contexts');
    if (!p) return;

    const bcs = nodesByType('bounded_context');
    if (!bcs.length) {
      p.innerHTML = '<div class="list-empty">No bounded context data. Run <code>ctl.sh build</code> to index the project.</div>';
      return;
    }

    const sorted = [...bcs].sort((a, b) => a.label.localeCompare(b.label));
    const cards  = sorted.map(bc => {
      const services = (bc.meta && bc.meta.services) || [];
      const chips    = services.map(svc =>
        `<span class="bc-chip" data-svc="${esc(svc)}" tabindex="0" role="button">${esc(svc)}</span>`
      ).join('');
      return `
        <div class="bc-card" data-node-id="${esc(bc.id)}" tabindex="0" role="button">
          <p class="bc-card-name">${esc(bc.label)}</p>
          <p class="bc-card-count">${services.length} service${services.length !== 1 ? 's' : ''}</p>
          <div class="bc-service-chips">${chips || '<span style="color:var(--muted);font-size:0.78rem">No services indexed</span>'}</div>
        </div>
      `;
    }).join('');

    p.innerHTML = `<div class="bc-grid">${cards}</div>`;

    p.querySelectorAll('.bc-card').forEach(card => {
      card.addEventListener('click', e => {
        if (e.target.classList.contains('bc-chip')) return;
        selectEntity(card.dataset.nodeId);
      });
      card.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectEntity(card.dataset.nodeId); }
      });
    });

    p.querySelectorAll('.bc-chip').forEach(chip => {
      chip.addEventListener('click', e => {
        e.stopPropagation();
        const svcNode = (ctxNodes || []).find(n => n.type === 'service' && n.label === chip.dataset.svc);
        if (svcNode) { selectEntity(svcNode.id); switchView('services'); }
      });
      chip.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          const svcNode = (ctxNodes || []).find(n => n.type === 'service' && n.label === chip.dataset.svc);
          if (svcNode) { selectEntity(svcNode.id); switchView('services'); }
        }
      });
    });
  }

  // ── Services ──────────────────────────────────────────────────────────────────

  function renderServices() {
    const p = panel('services');
    if (!p) return;

    const svcs = nodesByType('service');
    if (!svcs.length) {
      p.innerHTML = '<div class="list-empty">No service data. Run <code>ctl.sh build</code> to index the project.</div>';
      return;
    }

    const bcNames = [...new Set(
      svcs.map(s => (s.meta && s.meta.bounded_context) || '').filter(Boolean)
    )].sort();

    const filterChips = [
      `<button class="filter-chip${!activeServiceBCFilter ? ' filter-chip--active' : ''}" data-bc="">All</button>`,
      ...bcNames.map(bc =>
        `<button class="filter-chip${activeServiceBCFilter === bc ? ' filter-chip--active' : ''}" data-bc="${esc(bc)}">${esc(bc)}</button>`
      ),
    ].join('');

    const filtered = activeServiceBCFilter
      ? svcs.filter(s => (s.meta && s.meta.bounded_context) === activeServiceBCFilter)
      : svcs;
    const sorted = [...filtered].sort((a, b) => a.label.localeCompare(b.label));

    const rows = sorted.map(svc => {
      const meta       = svc.meta || {};
      const bc         = meta.bounded_context || '—';
      const status     = (meta.doc_status || 'unknown').toLowerCase();
      const primaryDbs = (meta.databases && meta.databases.primary) || [];
      const depCount   = ((meta.dependencies && meta.dependencies.calls) || []).length;
      const isSelected = svc.id === selectedId;
      return `
        <tr class="ctx-row${isSelected ? ' ctx-row--selected' : ''}"
            data-node-id="${esc(svc.id)}" data-label="${esc(svc.label.toLowerCase())}">
          <td>${esc(svc.label)}</td>
          <td><span class="status-badge" style="background:var(--context-soft);color:var(--context)">${esc(bc)}</span></td>
          <td><span class="status-badge status-badge--${esc(status)}">${esc(status)}</span></td>
          <td>${primaryDbs.map(esc).join(', ') || '—'}</td>
          <td style="text-align:center;color:var(--muted)">${depCount || '—'}</td>
          <td><span class="ctx-graph-link" data-node-id="${esc(svc.id)}">↗ graph</span></td>
        </tr>
      `;
    }).join('');

    p.innerHTML = `
      <div class="list-view">
        <div class="list-view-header">
          <span style="font-weight:700;font-size:0.9rem">${filtered.length} service${filtered.length !== 1 ? 's' : ''}</span>
          <div class="list-filter-bar">${filterChips}</div>
        </div>
        <table class="ctx-table">
          <thead><tr>
            <th>Name</th><th>Bounded Context</th><th>Status</th>
            <th>Primary DB</th><th>Deps</th><th></th>
          </tr></thead>
          <tbody>${rows || '<tr><td colspan="6"><div class="list-empty">No services match the selected filter.</div></td></tr>'}</tbody>
        </table>
      </div>
    `;

    p.querySelectorAll('.filter-chip[data-bc]').forEach(chip => {
      chip.addEventListener('click', () => {
        activeServiceBCFilter = chip.dataset.bc || null;
        renderServices();
        highlightSelectedRows(selectedId);
      });
    });

    _bindRowsAndLinks(p);
  }

  // ── Features ──────────────────────────────────────────────────────────────────

  function renderFeatures() {
    const p = panel('features');
    if (!p) return;

    const feats = nodesByType('feature');
    if (!feats.length) {
      p.innerHTML = '<div class="list-empty">No feature data. Run <code>ctl.sh build</code> to index the project.</div>';
      return;
    }

    const STATUSES = ['DRAFT', 'IN-REVIEW', 'READY', 'ARCHIVED'];
    const filterChips = [
      `<button class="filter-chip${!activeFeatureStatusFilter ? ' filter-chip--active' : ''}" data-status="">All</button>`,
      ...STATUSES.map(st =>
        `<button class="filter-chip${activeFeatureStatusFilter === st ? ' filter-chip--active' : ''}" data-status="${esc(st)}">${esc(st)}</button>`
      ),
    ].join('');

    const filtered = activeFeatureStatusFilter
      ? feats.filter(f => ((f.meta && f.meta.status) || '').toUpperCase() === activeFeatureStatusFilter)
      : feats;
    const sorted = [...filtered].sort((a, b) => a.label.localeCompare(b.label));

    const rows = sorted.map(feat => {
      const meta     = feat.meta || {};
      const status   = (meta.status || 'DRAFT').toUpperCase();
      const owner    = (meta.services && meta.services.primary_owner) || '—';
      const parts    = (meta.services && meta.services.participants) || [];
      const validated = meta.validated_at || '—';
      const statusCls = { READY: 'ready', 'IN-REVIEW': 'in-review', ARCHIVED: 'archived' }[status] || 'draft';
      const isSelected = feat.id === selectedId;
      return `
        <tr class="ctx-row${isSelected ? ' ctx-row--selected' : ''}"
            data-node-id="${esc(feat.id)}" data-label="${esc(feat.label.toLowerCase())}">
          <td>${esc(feat.label)}</td>
          <td><span class="status-badge status-badge--${esc(statusCls)}">${esc(status)}</span></td>
          <td>${esc(owner)}</td>
          <td>${parts.length ? parts.map(esc).join(', ') : '—'}</td>
          <td>${esc(validated)}</td>
          <td><span class="ctx-graph-link" data-node-id="${esc(feat.id)}">↗ graph</span></td>
        </tr>
      `;
    }).join('');

    p.innerHTML = `
      <div class="list-view">
        <div class="list-view-header">
          <span style="font-weight:700;font-size:0.9rem">${filtered.length} feature${filtered.length !== 1 ? 's' : ''}</span>
          <div class="list-filter-bar">${filterChips}</div>
        </div>
        <table class="ctx-table">
          <thead><tr>
            <th>Name</th><th>Status</th><th>Primary Owner</th>
            <th>Participants</th><th>Validated At</th><th></th>
          </tr></thead>
          <tbody>${rows || '<tr><td colspan="6"><div class="list-empty">No features match the selected filter.</div></td></tr>'}</tbody>
        </table>
      </div>
    `;

    p.querySelectorAll('.filter-chip[data-status]').forEach(chip => {
      chip.addEventListener('click', () => {
        activeFeatureStatusFilter = chip.dataset.status || null;
        renderFeatures();
        highlightSelectedRows(selectedId);
      });
    });

    _bindRowsAndLinks(p);
  }

  // ── Databases ─────────────────────────────────────────────────────────────────

  function renderDatabases() {
    const p = panel('databases');
    if (!p) return;

    const dbs = nodesByType('database');
    if (!dbs.length) {
      p.innerHTML = '<div class="list-empty">No database data. Run <code>ctl.sh build</code> to index the project.</div>';
      return;
    }

    const sorted = [...dbs].sort((a, b) => a.label.localeCompare(b.label));
    const rows   = sorted.map(db => {
      const meta    = db.meta || {};
      const engine  = meta.engine || '—';
      const shared  = meta.shared ? 'Shared' : 'Private';
      const owners  = (meta.primary_owners || []).join(', ') || '—';
      const readers = (meta.readers || []).length;
      const isSelected = db.id === selectedId;
      return `
        <tr class="ctx-row${isSelected ? ' ctx-row--selected' : ''}"
            data-node-id="${esc(db.id)}" data-label="${esc(db.label.toLowerCase())}">
          <td>${esc(db.label)}</td>
          <td>${esc(engine)}</td>
          <td style="color:${meta.shared ? 'var(--workflow)' : 'var(--muted)'}">${esc(shared)}</td>
          <td>${esc(owners)}</td>
          <td style="text-align:center;color:var(--muted)">${readers || '—'}</td>
          <td><span class="ctx-graph-link" data-node-id="${esc(db.id)}">↗ graph</span></td>
        </tr>
      `;
    }).join('');

    p.innerHTML = `
      <div class="list-view">
        <div class="list-view-header">
          <span style="font-weight:700;font-size:0.9rem">${dbs.length} database${dbs.length !== 1 ? 's' : ''}</span>
        </div>
        <table class="ctx-table">
          <thead><tr>
            <th>Name</th><th>Engine</th><th>Scope</th>
            <th>Primary Owners</th><th>Readers</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;

    _bindRowsAndLinks(p);
  }

  // ── Memories ──────────────────────────────────────────────────────────────────

  function memAge(isoStr) {
    try {
      const h = Math.floor((Date.now() - new Date(isoStr).getTime()) / 3600000);
      if (h < 1)  return 'just now';
      if (h < 24) return `${h}h ago`;
      return `${Math.floor(h / 24)}d ago`;
    } catch (_) { return '—'; }
  }

  function memIsStale(isoStr) {
    try { return Date.now() - new Date(isoStr).getTime() > 72 * 3600000; }
    catch (_) { return false; }
  }

  function memSection(title, entries) {
    if (!entries.length) return '';
    const items = entries.map(e => {
      const stale = memIsStale(e.modified_at);
      const age   = memAge(e.modified_at);
      const kb    = (e.size_bytes / 1024).toFixed(1);
      const date  = new Date(e.modified_at).toLocaleDateString();
      return `
        <div class="memory-entry${stale ? ' memory-entry--stale' : ''}"
             data-memory-key="${esc(e.key)}" tabindex="0" role="button">
          <span class="memory-key">${esc(e.key)}</span>
          <span class="memory-age">${esc(age)}${stale ? ' &nbsp;<span class="memory-stale-warn">stale</span>' : ''}</span>
          <span class="memory-meta">${esc(kb)} KB · ${esc(date)}</span>
        </div>
      `;
    }).join('');
    return `<p class="memory-section-title">${esc(title)}</p>${items}`;
  }

  async function renderMemories() {
    const p = panel('memories');
    if (!p) return;

    if (!memories) {
      p.innerHTML = '<div class="list-empty">Loading memories…</div>';
      memories = await fetchMemories();
    }

    if (!memories || !memories.entries || !memories.entries.length) {
      p.innerHTML = `
        <div class="list-empty">
          Memories unavailable.<br>
          In server mode, start CTL server — it reads <code>.serena/memories/</code> live.<br>
          In file mode, run <code>builders/build-memories.sh</code> first.
        </div>
      `;
      return;
    }

    const entries  = memories.entries;
    const project  = entries.filter(e => e.key.startsWith('project/'));
    const active   = entries.filter(e => e.key === 'session/active');
    const history  = entries.filter(e => e.key.startsWith('session/history/')).reverse(); // newest first
    const services = entries.filter(e => e.key.startsWith('services/'));
    const checkpts = entries.filter(e => e.key.startsWith('checkpoints/'));
    const other    = entries.filter(e =>
      !e.key.startsWith('project/') &&
      !e.key.startsWith('session/') &&
      !e.key.startsWith('services/') &&
      !e.key.startsWith('checkpoints/')
    );

    p.innerHTML = `
      <div class="memory-sections">
        ${memSection('Project', project)}
        ${memSection('Session', [...active, ...history])}
        ${memSection('Services', services)}
        ${memSection('Checkpoints', checkpts)}
        ${other.length ? memSection('Other', other) : ''}
        <p class="memory-section-title" style="margin-top:24px;border:none;padding-bottom:0">
          Generated ${new Date(memories.generated).toLocaleString()} · ${entries.length} entr${entries.length !== 1 ? 'ies' : 'y'}
        </p>
      </div>
    `;

    p.querySelectorAll('.memory-entry').forEach(entry => {
      entry.addEventListener('click',   () => showMemoryDetail(entry.dataset.memoryKey));
      entry.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showMemoryDetail(entry.dataset.memoryKey); }
      });
    });
  }

  function showMemoryDetail(key) {
    const entry   = memories && memories.entries && memories.entries.find(e => e.key === key);
    const dtTitle = document.getElementById('details-title');
    const dtSub   = document.getElementById('details-subtitle');
    const dtBody  = document.getElementById('details-body');
    if (!dtTitle || !dtBody) return;

    dtTitle.textContent = key;
    if (dtSub) dtSub.textContent = `memory · ${entry ? (entry.size_bytes / 1024).toFixed(1) + ' KB' : 'not found'}`;
    dtBody.innerHTML    = entry
      ? `<div class="memory-content">${esc(entry.content)}</div>`
      : '<div class="empty-state">Memory not found.</div>';

    document.querySelectorAll('.memory-entry').forEach(el => {
      el.classList.toggle('memory-entry--selected', el.dataset.memoryKey === key);
    });
  }

  async function fetchMemories() {
    // Server mode: live read from /api/memories
    if (window.location.protocol !== 'file:') {
      try {
        const res = await fetch('/api/memories');
        if (res.ok) return res.json();
      } catch (_) {}
    }
    // File mode: pre-built memories.json (one level up from graph/)
    try {
      const res = await fetch('../memories.json');
      if (res.ok) return res.json();
    } catch (_) {}
    return null;
  }

  // ── Episodic (graphbase-memories graph view) ──────────────────────────────────

  let _episodicData        = null;   // cached API response
  let _episodicFilter      = null;   // active type filter: null | 'memory' | 'entity'
  let _episodicEntityFilter = null;  // active entity name filter string

  async function renderEpisodic() {
    const p = panel('episodic');
    if (!p) return;

    if (!_episodicData) {
      p.innerHTML = '<div class="list-empty">Loading episodic graph…</div>';
      try {
        const res = await fetch('/api/graphbase');
        if (!res.ok) {
          const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
          p.innerHTML = `<div class="list-empty">${esc(err.error || 'Failed to load episodic data.')}</div>`;
          return;
        }
        _episodicData = await res.json();
      } catch (e) {
        p.innerHTML = `<div class="list-empty">Could not fetch /api/graphbase: ${esc(String(e))}</div>`;
        return;
      }
    }

    const data     = _episodicData;
    const allNodes = data.nodes || [];
    const allLinks = data.links || [];

    // Type filters
    const NODE_TYPES = [...new Set(allNodes.map(n => n.type))].sort();
    const filterBar  = [
      `<button class="filter-chip${!_episodicFilter ? ' filter-chip--active' : ''}" data-ep-filter="">All (${allNodes.length})</button>`,
      `<button class="filter-chip${_episodicFilter === 'memory' ? ' filter-chip--active' : ''}" data-ep-filter="memory">Memories</button>`,
      `<button class="filter-chip${_episodicFilter === 'entity' ? ' filter-chip--active' : ''}" data-ep-filter="entity">Entities</button>`,
    ].join('');

    // Entity name filter bar
    const entities    = allNodes.filter(n => n.node_type === 'entity');
    const entityNames = [...new Set(entities.map(n => n.label))].sort();
    const entityChips = entityNames.slice(0, 20).map(name =>
      `<button class="filter-chip filter-chip--sm${_episodicEntityFilter === name ? ' filter-chip--active' : ''}" data-ep-entity="${esc(name)}">${esc(name)}</button>`
    ).join('');

    // Apply filters to node list
    let filtered = allNodes;
    if (_episodicFilter) filtered = filtered.filter(n => n.node_type === _episodicFilter);
    if (_episodicEntityFilter) {
      // Gather memory IDs that reference this entity
      const entityNode = allNodes.find(n => n.node_type === 'entity' && n.label === _episodicEntityFilter);
      if (entityNode) {
        const linkedMemIds = new Set(
          allLinks
            .filter(l => l.source === entityNode.id || l.target === entityNode.id)
            .map(l => l.source === entityNode.id ? l.target : l.source)
        );
        filtered = filtered.filter(n => n.node_type === 'entity'
          ? n.label === _episodicEntityFilter
          : linkedMemIds.has(n.id)
        );
      }
    }

    // Render node list table
    const rows = filtered.map(n => {
      const isMemory  = n.node_type === 'memory';
      const typeClass = isMemory ? `status-badge status-badge--${esc(n.type || 'session')}` : 'status-badge';
      const tagsHtml  = (n.tags && n.tags.length)
        ? n.tags.map(t => `<span class="bc-chip" style="cursor:default">${esc(t)}</span>`).join('')
        : '';
      const expFlag   = n.is_expired ? ' <span style="color:var(--warning);font-size:0.75rem">[expired]</span>' : '';
      return `
        <tr class="ctx-row" data-node-id="${esc(n.id)}" data-label="${esc((n.label || '').toLowerCase())}">
          <td><span class="${typeClass}">${esc(n.node_type)}</span></td>
          <td>${esc(n.label)}${expFlag}</td>
          <td><span class="status-badge">${esc(n.type || '—')}</span></td>
          <td>${tagsHtml}</td>
          <td style="color:var(--muted);font-size:0.78rem">${esc(n.updated_at ? n.updated_at.slice(0, 10) : '—')}</td>
        </tr>
      `;
    }).join('');

    p.innerHTML = `
      <div class="list-view">
        <div class="list-view-header" style="flex-wrap:wrap;gap:8px">
          <span style="font-weight:700;font-size:0.9rem">
            ${esc(data.project)} · ${filtered.length} / ${allNodes.length} nodes
            (${data.total_memories} total memories)
          </span>
          <div class="list-filter-bar">${filterBar}</div>
        </div>
        ${entityChips ? `<div class="list-filter-bar" style="padding:6px 12px;flex-wrap:wrap">${entityChips}</div>` : ''}
        <table class="ctx-table">
          <thead><tr>
            <th>Kind</th><th>Label</th><th>Type</th><th>Tags</th><th>Updated</th>
          </tr></thead>
          <tbody>${rows || '<tr><td colspan="5"><div class="list-empty">No nodes match filter.</div></td></tr>'}</tbody>
        </table>
        <p style="color:var(--muted);font-size:0.76rem;padding:8px 12px">
          ${allLinks.length} edge${allLinks.length !== 1 ? 's' : ''} ·
          Generated ${esc(data.generated_at ? data.generated_at.slice(0, 19).replace('T', ' ') : '—')}
          <button class="filter-chip" id="ep-refresh" style="margin-left:12px">↺ Refresh</button>
        </p>
      </div>
    `;

    // Filter chip handlers
    p.querySelectorAll('[data-ep-filter]').forEach(btn => {
      btn.addEventListener('click', () => {
        _episodicFilter = btn.dataset.epFilter || null;
        renderEpisodic();
      });
    });

    p.querySelectorAll('[data-ep-entity]').forEach(btn => {
      btn.addEventListener('click', () => {
        _episodicEntityFilter = _episodicEntityFilter === btn.dataset.epEntity ? null : btn.dataset.epEntity;
        renderEpisodic();
      });
    });

    const refreshBtn = p.querySelector('#ep-refresh');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        _episodicData = null;
        renderEpisodic();
      });
    }

    // Row search integration
    const searchEl = document.getElementById('search-input');
    if (searchEl && searchEl.value.trim()) {
      const term = searchEl.value.trim().toLowerCase();
      p.querySelectorAll('.ctx-row').forEach(row => {
        row.hidden = !(row.dataset.label || '').includes(term);
      });
    }
  }

  // ── Shared row binding helper ─────────────────────────────────────────────────

  function _bindRowsAndLinks(p) {
    p.querySelectorAll('.ctx-row').forEach(row => {
      row.addEventListener('click', e => {
        if (e.target.classList.contains('ctx-graph-link')) return;
        selectEntity(row.dataset.nodeId);
      });
    });
    p.querySelectorAll('.ctx-graph-link').forEach(link => {
      link.addEventListener('click', e => {
        e.stopPropagation();
        goToGraph(link.dataset.nodeId);
      });
    });
  }

  // ── Cross-linking: list → graph ───────────────────────────────────────────────

  function selectEntity(nodeId) {
    selectedId = nodeId;
    highlightSelectedRows(nodeId);
    document.dispatchEvent(new CustomEvent('ctl:select-entity', { detail: nodeId }));
  }

  function goToGraph(nodeId) {
    selectEntity(nodeId);
    switchView('graph');
  }

  function highlightSelectedRows(nodeId) {
    document.querySelectorAll('.ctx-row').forEach(row => {
      row.classList.toggle('ctx-row--selected', row.dataset.nodeId === nodeId);
    });
  }

  // ── Cross-linking: graph → list ───────────────────────────────────────────────

  document.addEventListener('ctl:node-selected', e => {
    const node = e.detail;
    if (node && node.domain === 'context') {
      selectedId = node.id;
      highlightSelectedRows(node.id);
    }
  });

  document.addEventListener('ctl:data-loaded', e => {
    ctxNodes = (e.detail.nodes || []).filter(n => n.domain === 'context');
    if (activeView !== 'graph') renderCurrentView();
  });

  // ── Search integration ────────────────────────────────────────────────────────
  // Connects the existing sidebar search input to list view filtering

  const searchEl = document.getElementById('search-input');
  if (searchEl) {
    searchEl.addEventListener('input', () => {
      if (activeView === 'graph') return; // graph.js handles its own filter
      const term = searchEl.value.trim().toLowerCase();
      document.querySelectorAll('.ctx-row').forEach(row => {
        row.hidden = term.length > 0 && !(row.dataset.label || '').includes(term);
      });
    });
  }

  // ── Keyboard shortcuts ────────────────────────────────────────────────────────

  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      if (searchEl) searchEl.focus();
    }
    if (e.key === 'Escape' && searchEl && document.activeElement === searchEl) {
      searchEl.value = '';
      searchEl.dispatchEvent(new Event('input'));
    }
  });

  // ── Init ──────────────────────────────────────────────────────────────────────

  function init() {
    document.querySelectorAll('.view-tab').forEach(tab => {
      tab.addEventListener('click', () => switchView(tab.dataset.view));
    });

    // Restore last active view from localStorage
    let saved;
    try { saved = localStorage.getItem(VIEW_KEY); } catch (_) {}
    switchView(saved && VALID_VIEWS.includes(saved) ? saved : 'graph');
  }

  init();
})();
