// ── §1 NODE TYPE REGISTRY ─────────────────────────────────────────────────
// Single source of truth: replaces NODE_COLORS + CATEGORY_STYLES + TOPO_NODE_LABELS.
// Add one entry here to propagate to rendering, filtering, and summary strip.
const NODE_TYPE_REGISTRY = {
  // Structural nodes
  Workspace: {
    kind: 'structural', sidebarLabel: 'Workspace', badgeSuffix: 'workspace',
    summaryIn: ['collapsed'],
    color: { background: '#7c3aed', border: '#6d28d9',
             highlight: { background: '#8b5cf6', border: '#7c3aed' } },
    shape: 'star', size: 24,
  },
  Project: {
    kind: 'structural', sidebarLabel: 'Project', badgeSuffix: 'project',
    summaryIn: ['collapsed'],
    color: { background: '#2563eb', border: '#1d4ed8',
             highlight: { background: '#3b82f6', border: '#2563eb' } },
    shape: 'dot', size: 16,
  },
  Stale: {
    kind: 'structural', sidebarLabel: null, badgeSuffix: 'stale',
    summaryIn: [],
    color: { background: '#b45309', border: '#92400e',
             highlight: { background: '#d97706', border: '#b45309' } },
    shape: 'dot', size: 16,
  },
  // EntityFact subcategories (n.label === 'EntityFact', styled by n.category)
  // All entries use unified vis-network color shape: { background, border, highlight: { background, border } }
  Service:        { kind: 'entity-category', sidebarLabel: 'Service',        badgeSuffix: 'service',        summaryIn: ['topology'], color: { background: '#0ea5e9', border: '#0284c7', highlight: { background: '#38bdf8', border: '#0284c7' } }, shape: 'dot',      size: 14 },
  BoundedContext: { kind: 'entity-category', sidebarLabel: 'BoundedContext', badgeSuffix: 'boundedcontext', summaryIn: ['topology'], color: { background: '#f59e0b', border: '#d97706', highlight: { background: '#fbbf24', border: '#d97706' } }, shape: 'hexagon',  size: 18 },
  Topic:          { kind: 'entity-category', sidebarLabel: 'Topic',          badgeSuffix: 'topic',          summaryIn: ['topology'], color: { background: '#10b981', border: '#059669', highlight: { background: '#34d399', border: '#059669' } }, shape: 'triangle', size: 12 },
  DataStore:      { kind: 'entity-category', sidebarLabel: 'DataStore',      badgeSuffix: 'datastore',      summaryIn: ['topology'], color: { background: '#8b5cf6', border: '#7c3aed', highlight: { background: '#a78bfa', border: '#7c3aed' } }, shape: 'database', size: 14 },
  External:       { kind: 'entity-category', sidebarLabel: 'External',       badgeSuffix: 'external',       summaryIn: ['topology'], color: { background: '#f97316', border: '#ea580c', highlight: { background: '#fb923c', border: '#ea580c' } }, shape: 'box',      size: 13 },
  EntityFact:     { kind: 'entity-category', sidebarLabel: 'Other',          badgeSuffix: 'entityfact',     summaryIn: ['collapsed', 'topology'], color: { background: '#94a3b8', border: '#64748b', highlight: { background: '#cbd5e1', border: '#64748b' } }, shape: 'dot', size: 11 },
  // First-class topology labels — n.label IS the category key (T5.3)
  Feature:      { kind: 'topo-label', sidebarLabel: 'Feature',      badgeSuffix: 'feature',      summaryIn: ['topology'], color: { background: '#ec4899', border: '#db2777', highlight: { background: '#f472b6', border: '#db2777' } }, shape: 'star',     size: 14 },
  DataSource:   { kind: 'topo-label', sidebarLabel: 'DataSource',   badgeSuffix: 'datasource',   summaryIn: ['topology'], color: { background: '#8b5cf6', border: '#7c3aed', highlight: { background: '#a78bfa', border: '#7c3aed' } }, shape: 'database', size: 14 },
  MessageQueue: { kind: 'topo-label', sidebarLabel: 'MessageQueue', badgeSuffix: 'messagequeue', summaryIn: ['topology'], color: { background: '#10b981', border: '#059669', highlight: { background: '#34d399', border: '#059669' } }, shape: 'triangle', size: 12 },
};

// ── §2 THEME SYSTEM ────────────────────────────────────────────────────────
// dim palette used by activateFocus() — must match CSS token values per theme
const PALETTE = {
  dark:  { dimColor: { background: '#1e293b', border: '#334155',
                       highlight: { background: '#1e293b', border: '#334155' } },
           dimFont: '#0f172a' },   // matches --bg-base: labels dissolve into background
  light: { dimColor: { background: '#e2e8f0', border: '#cbd5e1',
                       highlight: { background: '#e2e8f0', border: '#cbd5e1' } },
           dimFont: '#f8fafc' },   // matches --bg-base light: labels dissolve into background
};

const _THEME_KEY = 'graphbase-theme';
function currentTheme() { return document.documentElement.dataset.theme || 'dark'; }

function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem(_THEME_KEY, next);
  const btn = document.getElementById('btn-theme');
  if (btn) btn.textContent = next === 'dark' ? '☀ Light' : '☽ Dark';
}

// Apply persisted theme immediately (script is at bottom of <body>, DOM is ready)
(function initTheme() {
  const saved = localStorage.getItem(_THEME_KEY);
  if (saved) document.documentElement.dataset.theme = saved;
  const btn = document.getElementById('btn-theme');
  if (btn) btn.textContent = currentTheme() === 'dark' ? '☀ Light' : '☽ Dark';
}());

// Derived from registry — no manual sync needed
const TOPO_NODE_LABELS = new Set(
  Object.entries(NODE_TYPE_REGISTRY)
    .filter(([, v]) => v.kind === 'topo-label').map(([k]) => k)
);

const EDGE_COLORS = {
  MEMBER_OF:          { color: '#475569', highlight: '#64748b' },
  BELONGS_TO:         { color: '#475569', highlight: '#64748b' },
  CROSS_SERVICE_LINK: { color: '#10b981', highlight: '#34d399' },
  AFFECTS:            { color: '#ef4444', highlight: '#f87171' },
  INVOLVES:           { color: '#ec4899', highlight: '#f472b6' },
  CONSUMES:           { color: '#10b981', highlight: '#34d399' },
  PRODUCES:           { color: '#3b82f6', highlight: '#60a5fa' },
  READS:              { color: '#94a3b8', highlight: '#cbd5e1' },
  WRITES:             { color: '#f59e0b', highlight: '#fbbf24' },
  CONFLICTS_WITH:     { color: '#ef4444', highlight: '#f87171' },
  MERGES_INTO:        { color: '#a78bfa', highlight: '#c4b5fd' },
  // First-class topology relationship types (T5.3)
  CALLS_DOWNSTREAM:   { color: '#3b82f6', highlight: '#60a5fa' },
  CALLS_UPSTREAM:     { color: '#6366f1', highlight: '#818cf8' },
  READS_FROM:         { color: '#94a3b8', highlight: '#cbd5e1' },
  WRITES_TO:          { color: '#f59e0b', highlight: '#fbbf24' },
  PUBLISHES_TO:       { color: '#10b981', highlight: '#34d399' },
  SUBSCRIBES_TO:      { color: '#06b6d4', highlight: '#22d3ee' },
  MEMBER_OF_CONTEXT:  { color: '#f59e0b', highlight: '#fbbf24' },
  PART_OF:            { color: '#475569', highlight: '#64748b' },
  HAS_FEATURE:        { color: '#ec4899', highlight: '#f472b6' },
};

// ── State ───────────────────────────────────────────────────────────────
let rawData    = null;
let network    = null;
let topoMode   = false;
let pendingFocusId = null;
const nodeDataset = new vis.DataSet();
const edgeDataset = new vis.DataSet();

// ── URL params ──────────────────────────────────────────────────────────
const urlParams = new URLSearchParams(window.location.search);
const wsInput = document.getElementById('ws-input');
pendingFocusId = urlParams.get('focus');
wsInput.value = urlParams.get('workspace') || urlParams.get('workspace_id') || '';

// Ensure the graph sidebar controls satisfy browser form-field checks.
document.querySelectorAll('input:not([name])').forEach((input, index) => {
  input.name =
    input.dataset.label ||
    input.dataset.edge ||
    input.dataset.category ||
    input.id ||
    `graph-field-${index}`;
});

// ── Active filters ──────────────────────────────────────────────────────
function activeNodeLabels() {
  return [...document.querySelectorAll('[data-filter="node"]')]
    .filter(cb => cb.checked).map(cb => cb.dataset.label);
}
function activeCategories() {
  return [...document.querySelectorAll('[data-filter="category"]')]
    .filter(cb => cb.checked).map(cb => cb.dataset.category);
}
function activeEdgeTypes() {
  const attr = topoMode ? '[data-filter="topo-edge"]' : '[data-filter="edge"]';
  return [...document.querySelectorAll(attr)]
    .filter(cb => cb.checked).map(cb => cb.dataset.edge);
}

// ── Build vis node object ───────────────────────────────────────────────
// All NODE_TYPE_REGISTRY entries use unified color shape: { background, border, highlight: {…} }
function toVisNode(n) {
  // EntityFact nodes — styled by n.category via registry
  if (n.label === 'EntityFact') {
    const key = n.category || 'EntityFact';
    const reg = NODE_TYPE_REGISTRY[key] || NODE_TYPE_REGISTRY.EntityFact;
    return {
      id: n.id, label: n.display,
      title: `[${key}] ${n.id}${n.fact ? '\n' + n.fact.slice(0, 80) : ''}`,
      color: reg.color,
      shape: reg.shape, size: reg.size,
      font: { size: 10, color: '#e2e8f0' }, borderWidth: 1.5, _raw: n,
    };
  }
  // First-class topology nodes — n.label IS the registry key
  if (TOPO_NODE_LABELS.has(n.label)) {
    const reg = NODE_TYPE_REGISTRY[n.label];
    return {
      id: n.id, label: n.display,
      title: `[${n.label}] ${n.id}`,
      color: reg.color,
      shape: reg.shape, size: reg.size,
      font: { size: 10, color: '#e2e8f0' }, borderWidth: 1.5, _raw: n,
    };
  }
  // Structural nodes (Workspace, Project, Stale)
  const colorKey = n.is_stale ? 'Stale' : n.label;
  const reg = NODE_TYPE_REGISTRY[colorKey] || NODE_TYPE_REGISTRY.Project;
  return {
    id: n.id, label: n.display,
    title: `${n.label}: ${n.id}`,
    color: reg.color, size: reg.size, shape: reg.shape,
    font: { size: 12, color: '#e2e8f0' }, borderWidth: 2, _raw: n,
  };
}

function toVisEdge(e, idx) {
  const col = EDGE_COLORS[e.type] || { color: '#334155', highlight: '#475569' };
  return {
    id: `e-${idx}`,
    from: e.source,
    to: e.target,
    label: e.type === 'MEMBER_OF' || e.type === 'BELONGS_TO' ? '' : e.type,
    color: col,
    arrows: { to: { enabled: true, scaleFactor: 0.5 } },
    smooth: { type: 'continuous' },
    font: { size: 8, color: '#64748b', align: 'middle' },
    _type: e.type,
  };
}

// ── Apply filters (no network reinit) ───────────────────────────────────
function applyFilters() {
  // Reset focus state inline — do NOT call exitFocus() to avoid §9→§11 coupling cycle
  focusNodeId = null;
  _focusIndicator?.classList.remove('visible');

  if (!rawData) return;
  const types = activeEdgeTypes();
  let visibleNodes;

  if (topoMode) {
    const cats = activeCategories();
    visibleNodes = rawData.nodes.filter(n => {
      if (n.label === 'EntityFact') return cats.includes(n.category || 'EntityFact');
      if (TOPO_NODE_LABELS.has(n.label)) return cats.includes(n.label);
      return true; // Workspace + Project always visible in topology too
    });
  } else {
    const labels = activeNodeLabels();
    visibleNodes = rawData.nodes.filter(n => labels.includes(n.label));
  }

  const visibleIds   = new Set(visibleNodes.map(n => n.id));
  const visibleEdges = rawData.edges.filter(e =>
    types.includes(e.type) &&
    visibleIds.has(e.source) &&
    visibleIds.has(e.target)
  );

  nodeDataset.clear();
  edgeDataset.clear();
  nodeDataset.add(visibleNodes.map(toVisNode));
  edgeDataset.add(visibleEdges.map(toVisEdge));
}

// ── Update summary strip (registry-driven, fixes F2) ───────────────────
function updateSummary(summary) {
  const mode   = topoMode ? 'topology' : 'collapsed';
  const counts = summary.counts || {};
  const rows   = Object.entries(NODE_TYPE_REGISTRY)
    .filter(([, r]) => r.summaryIn.includes(mode) && r.sidebarLabel !== null)
    .map(([key, r]) =>
      `<div class="summary-row"><span>${r.sidebarLabel}</span><span>${(counts[key] ?? 0).toLocaleString()}</span></div>`
    ).join('');
  document.getElementById('summary-panel').innerHTML = rows;

  const total  = summary.total_nodes_in_graph ?? 0;
  const capped = summary.capped_at ?? 200;
  const totalEl = document.getElementById('total-label');
  if (totalEl) {
    totalEl.textContent = topoMode
      ? `${(counts.EntityFact ?? 0).toLocaleString()} entities loaded`
      : (total > capped
          ? `Showing ≤${capped} of ${total.toLocaleString()} total nodes`
          : `${total.toLocaleString()} total nodes`);
  }
}

// ── §12 DETAIL PANEL ───────────────────────────────────────────────────────
const _detailPanel  = document.getElementById('detail-panel');
const _dpTypeBadge  = document.getElementById('dp-type-badge');
const _dpId         = document.getElementById('dp-id');
const _dpDisplay    = document.getElementById('dp-display');
const _dpMeta       = document.getElementById('dp-section-meta');
const _dpEdgesWrap  = document.getElementById('dp-section-edges');
const _dpEdgeList   = document.getElementById('dp-edge-list');
const _dpNeighWrap  = document.getElementById('dp-section-neighbors');
const _dpNeighChips = document.getElementById('dp-neighbor-chips');
const _dpCopy       = document.getElementById('dp-copy');
const _dpFullDetail = document.getElementById('dp-full-detail');

function buildEdgeSummary(nodeId) {
  const counts = {};
  for (const e of (rawData?.edges || [])) {
    if (e.source === nodeId || e.target === nodeId) {
      const dir = e.source === nodeId ? '→' : '←';
      const key = `${dir}__${e.type}`;
      if (!counts[key]) counts[key] = { dir, type: e.type, n: 0 };
      counts[key].n++;
    }
  }
  return Object.values(counts).sort((a, b) => b.n - a.n);
}

function renderMetaSection(item) {
  let html = '';
  if (item.label === 'Project') {
    html += '<h3>Metadata</h3>';
    if (item.staleness_days != null) {
      const pct   = Math.min(item.staleness_days / 30 * 100, 100).toFixed(0);
      const color = item.is_stale ? '#d97706' : '#16a34a';
      const label = item.is_stale
        ? `Stale — ${item.staleness_days.toFixed(1)} days`
        : `Fresh — ${item.staleness_days.toFixed(1)} days`;
      html += `<div class="dp-field">
        <span class="dp-label">Freshness</span>
        <span class="dp-value">${label}</span>
        <div class="freshness-bar"><div class="freshness-fill" style="width:${pct}%;background:${color}"></div></div>
      </div>`;
    }
    if (item.badge_counts) {
      html += '<div class="dp-field"><span class="dp-label">Child Nodes</span>';
      for (const [k, v] of Object.entries(item.badge_counts)) {
        if (v > 0) html += `<div class="dp-count-row"><span>${k}</span><span>${v}</span></div>`;
      }
      html += '</div>';
    }
  } else if (item.label === 'Workspace') {
    html += '<h3>Metadata</h3>';
    const childCount = (rawData?.edges || []).filter(e => e.target === item.id && e.type === 'MEMBER_OF').length;
    html += `<div class="dp-field"><span class="dp-label">Projects</span><span class="dp-value">${childCount}</span></div>`;
  } else if (item.label === 'EntityFact') {
    html += '<h3>Metadata</h3>';
    if (item.category) html += `<div class="dp-field"><span class="dp-label">Category</span><span class="dp-value">${item.category}</span></div>`;
    if (item.scope)    html += `<div class="dp-field"><span class="dp-label">Scope</span><span class="dp-value">${item.scope}</span></div>`;
    if (item.fact)     html += `<div class="dp-field"><span class="dp-label">Fact</span><div class="dp-value fact">${item.fact}</div></div>`;
  } else {
    // Topology nodes: Feature, DataSource, MessageQueue, BoundedContext
    html += '<h3>Metadata</h3>';
    if (item.health_status) html += `<div class="dp-field"><span class="dp-label">Health</span><span class="dp-value">${item.health_status}</span></div>`;
    if (item.source_type)   html += `<div class="dp-field"><span class="dp-label">Source Type</span><span class="dp-value">${item.source_type}</span></div>`;
    if (item.queue_type)    html += `<div class="dp-field"><span class="dp-label">Queue Type</span><span class="dp-value">${item.queue_type}</span></div>`;
    if (item.domain)        html += `<div class="dp-field"><span class="dp-label">Domain</span><span class="dp-value">${item.domain}</span></div>`;
  }
  return html || '<p style="color:#475569;font-size:12px;padding:4px 0">No additional metadata.</p>';
}

function openDetailPanel(nodeId) {
  const item = rawData?.nodes.find(n => n.id === nodeId);
  if (!item) return;

  _dpId.textContent      = item.id;
  _dpDisplay.textContent = item.display;
  if (_dpFullDetail) {
    _dpFullDetail.onclick = () => {
      window.location.href = `/ui/index.html#memory/${encodeURIComponent(item.id)}`;
    };
  }

  // Type badge — use category for EntityFact nodes
  const badgeLabel = (item.label === 'EntityFact' && item.category) ? item.category : item.label;
  _dpTypeBadge.textContent = badgeLabel;
  _dpTypeBadge.className   = `inspect-badge badge-${badgeLabel.toLowerCase()}`;

  // Copy button
  _dpCopy.onclick = () => {
    navigator.clipboard.writeText(item.id).catch(() => {});
    _dpCopy.textContent = 'Copied!';
    setTimeout(() => { _dpCopy.textContent = 'Copy'; }, 1500);
  };

  // Meta section
  _dpMeta.innerHTML = renderMetaSection(item);

  // Edge summary (client-side from rawData)
  const edges = buildEdgeSummary(nodeId);
  if (edges.length > 0) {
    _dpEdgesWrap.style.display = '';
    _dpEdgeList.innerHTML = edges.map(e =>
      `<div class="dp-edge-row">
        <span><span class="dp-edge-dir">${e.dir}</span>${e.type}</span>
        <span class="dp-edge-count">×${e.n}</span>
      </div>`
    ).join('');
  } else {
    _dpEdgesWrap.style.display = 'none';
  }

  // Neighbors (first 5 via vis-network, reflects active edge filters)
  const neighborIds = network
    ? [...new Set([
        ...network.getConnectedNodes(nodeId, 'from'),
        ...network.getConnectedNodes(nodeId, 'to'),
      ])].slice(0, 5)
    : [];
  if (neighborIds.length > 0) {
    _dpNeighWrap.style.display = '';
    _dpNeighChips.innerHTML = neighborIds.map(nid => {
      const neighbor = rawData?.nodes.find(n => n.id === nid);
      const label    = neighbor ? neighbor.display : nid;
      return `<button class="neighbor-chip" data-nid="${nid}" title="${nid}">${label}</button>`;
    }).join('');
    _dpNeighChips.querySelectorAll('.neighbor-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        if (network) network.selectNodes([btn.dataset.nid]);
        openDetailPanel(btn.dataset.nid);
      });
    });
  } else {
    _dpNeighWrap.style.display = 'none';
  }

  _detailPanel.classList.add('open');
}

function closeDetailPanel() {
  _detailPanel.classList.remove('open');
}

document.getElementById('dp-close').addEventListener('click', closeDetailPanel);

// ── §11 FOCUS MODE ─────────────────────────────────────────────────────────
// State: null = idle; string nodeId = focus active on that node.
let focusNodeId = null;
const _focusIndicator = document.getElementById('focus-indicator');

function activateFocus(nodeId) {
  focusNodeId = nodeId;

  // Keep-set: focal node + 1-hop neighbours (both directions via active edge filters)
  // Note: getConnectedNodes() reflects the CURRENTLY VISIBLE (filtered) dataset — intentional.
  const neighbors = new Set([
    nodeId,
    ...(network?.getConnectedNodes(nodeId, 'from') || []),
    ...(network?.getConnectedNodes(nodeId, 'to')   || []),
  ]);

  // Batch update — O(N), single DataSet write. Safe for 5000-node topology mode.
  // Uses { returnType: 'Object' } for O(1) keyed access (vis-network official pattern).
  const allNodes = nodeDataset.get({ returnType: 'Object' });
  const updates  = Object.keys(allNodes).map(id => {
    if (id === nodeId) {
      // Focal node: full color + white border + thicker border width.
      // Use _raw to derive original color — item.color may already be p.dimColor when shifting focus.
      const orig = allNodes[id]._raw ? toVisNode(allNodes[id]._raw) : allNodes[id];
      return { id, opacity: 1, borderWidth: 4, borderDashes: false,
               color: { ...orig.color, border: '#ffffff',
                        highlight: { ...orig.color?.highlight, border: '#ffffff' } } };
    }
    if (neighbors.has(id)) {
      // 1-hop neighbors: restore full original appearance from _raw.
      // Restoring only opacity is insufficient — dim operations set color and font.color explicitly,
      // so a shift-focus would leave neighbors invisible (dimmed colors at opacity 1) without this.
      const raw = allNodes[id]._raw;
      if (raw) return { ...toVisNode(raw), opacity: 1, borderDashes: false };
      return { id, opacity: 1, borderWidth: 1.5, borderDashes: false };
    }
    // Dimmed: near-background color + invisible label (WCAG 1.4.1 secondary non-color cue via dashes).
    // font.color is explicitly dimmed because vis-network renders labels in a separate canvas pass
    // that does not reliably inherit node opacity — must be set explicitly to prevent label bleed.
    const p = PALETTE[currentTheme()];
    return { id, opacity: 0.12, color: p.dimColor, borderDashes: [4, 4], font: { color: p.dimFont } };
  });
  nodeDataset.update(updates);

  // TODO(post-MVP): dim edges not connected to focusNodeId via edgeDataset.update()

  network?.focus(nodeId, {
    scale: 1.4,
    animation: { duration: 400, easingFunction: 'easeInOutQuad' },
  });
  _focusIndicator.classList.add('visible');
}

function exitFocus() {
  if (focusNodeId === null) return;
  focusNodeId = null;
  _focusIndicator.classList.remove('visible');
  // Full re-render restores all node colors from NODE_TYPE_REGISTRY (Option A: lightweight restore)
  applyFilters();
}

// ── Bootstrap vis-network ───────────────────────────────────────────────
function initNetwork(nodeCount) {
  const container = document.getElementById('graph');
  const isLarge = nodeCount > 200;
  const options = {
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        avoidOverlap:         isLarge ? 0.3  : 0.5,
        gravitationalConstant: isLarge ? -30  : -50,
        springLength:         isLarge ? 80   : 100,
      },
      stabilization: {
        iterations:    isLarge ? 80  : 150,
        updateInterval: isLarge ? 50 : 25,
      },
    },
    interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
    layout: { improvedLayout: false },
  };
  if (!network) {
    network = new vis.Network(container, { nodes: nodeDataset, edges: edgeDataset }, options);
    window.network = network;
    // ── Click handler with 75ms debounce ────────────────────────────────
    // Single-click opens detail panel; doubleClick (added in P2) cancels this timer.
    let _clickTimer = null;
    network.on('click', params => {
      clearTimeout(_clickTimer);
      if (params.nodes.length === 0) {
        _clickTimer = setTimeout(() => { closeDetailPanel(); }, 75);
        return;
      }
      const nid = params.nodes[0];
      _clickTimer = setTimeout(() => { openDetailPanel(nid); }, 75);
    });
    // ── Double-click enters/shifts/exits focus mode ──────────────────────
    // Cancels the pending single-click detail-panel open (75ms debounce above).
    network.on('doubleClick', params => {
      clearTimeout(_clickTimer);           // cancel pending single-click (shared closure)
      if (params.nodes.length === 0) return;
      const nid = params.nodes[0];
      if (focusNodeId === nid) exitFocus();   // same node → exit focus
      else activateFocus(nid);               // new node → enter / shift focus
    });
    network.on('stabilizationIterationsDone', () => {
      network.setOptions({ physics: { enabled: false } });
    });
  } else {
    network.setOptions(options);
  }
}

function applyPendingFocus() {
  if (!pendingFocusId || !network) return;
  const node = nodeDataset.get(pendingFocusId);
  if (!node) return;
  network.selectNodes([pendingFocusId]);
  network.focus(pendingFocusId, {
    scale: 1.2,
    animation: { duration: 400, easingFunction: 'easeInOutQuad' },
  });
  openDetailPanel(pendingFocusId);
  pendingFocusId = null;
}

// ── Fetch & render ──────────────────────────────────────────────────────
async function load() {
  focusNodeId = null;                                         // sync focus reset before any await
  _focusIndicator?.classList.remove('visible');
  closeDetailPanel();                                         // sync panel reset before any await
  document.getElementById('loading').style.display   = 'flex';
  document.getElementById('error-panel').style.display = 'none';
  document.getElementById('btn-refresh').disabled    = true;

  const hint = document.getElementById('loading-hint');
  if (topoMode) hint.textContent = 'Topology mode may take a moment for large graphs…';
  else hint.textContent = '';

  try {
    const wsId  = wsInput.value.trim();
    const parts = ['/graph/overview'];
    const qs    = [];
    if (wsId)      qs.push(`workspace_id=${encodeURIComponent(wsId)}`);
    if (topoMode)  qs.push('topology=true');
    if (qs.length) parts.push('?' + qs.join('&'));

    const res = await fetch(parts.join(''));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    rawData = await res.json();

    updateSummary(rawData.summary);
    applyFilters();
    initNetwork(nodeDataset.length);
    applyPendingFocus();

    document.getElementById('loading').style.display = 'none';
  } catch (err) {
    document.getElementById('loading').style.display   = 'none';
    document.getElementById('error-msg').textContent   = `Failed to load: ${err.message}`;
    document.getElementById('error-panel').style.display = 'flex';
  } finally {
    document.getElementById('btn-refresh').disabled = false;
  }
}

// ── Topology mode toggle ────────────────────────────────────────────────
function setMode(topology) {
  topoMode = topology;

  document.getElementById('btn-collapsed').classList.toggle('active', !topology);
  document.getElementById('btn-topology').classList.toggle('active',  topology);

  const modeBadge = document.getElementById('mode-badge');
  modeBadge.textContent = topology ? 'Topology' : 'Collapsed';
  modeBadge.className   = topology ? 'mode-badge topology' : 'mode-badge';

  document.querySelectorAll('.topo-section').forEach(el => el.classList.toggle('visible', topology));
  document.querySelectorAll('.collapsed-section').forEach(el => el.classList.toggle('hidden', topology));

  load();
}

document.getElementById('btn-collapsed').addEventListener('click', () => { if (topoMode)  setMode(false); });
document.getElementById('btn-topology').addEventListener('click',  () => { if (!topoMode) setMode(true);  });

// ── Theme toggle ─────────────────────────────────────────────────────────
document.getElementById('btn-theme').addEventListener('click', toggleTheme);

// ── Workspace apply ─────────────────────────────────────────────────────
document.getElementById('ws-apply').addEventListener('click', load);
wsInput.addEventListener('keydown', e => { if (e.key === 'Enter') load(); });

// ── Debounced workspace input ───────────────────────────────────────────
let _wsDebounce = null;
wsInput.addEventListener('input', () => {
  clearTimeout(_wsDebounce);
  _wsDebounce = setTimeout(load, 300);
});

// ── Canvas controls ─────────────────────────────────────────────────────
let _physicsOn = false;
document.getElementById('btn-fit').addEventListener('click', () => {
  if (network) network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
});
document.getElementById('btn-physics').addEventListener('click', () => {
  if (!network) return;
  _physicsOn = !_physicsOn;
  network.setOptions({ physics: { enabled: _physicsOn } });
  const btn = document.getElementById('btn-physics');
  btn.textContent = _physicsOn ? '⚡ Physics ON' : '⚡ Physics';
  btn.classList.toggle('physics-on', _physicsOn);
});

// ── Filter checkboxes ───────────────────────────────────────────────────
document.querySelectorAll('[data-filter]').forEach(cb => {
  cb.addEventListener('change', applyFilters);
});

// ── Refresh button ──────────────────────────────────────────────────────
document.getElementById('btn-refresh').addEventListener('click', load);

// ── Global keyboard shortcuts ────────────────────────────────────────────
// Escape priority chain: exit focus first, then close detail panel
// F key: enter focus on selected node (or exit if already focused)
document.addEventListener('keydown', e => {
  if (document.activeElement.tagName === 'INPUT') return;   // never intercept text entry
  if (e.key === 'Escape') {
    if (focusNodeId !== null) { exitFocus(); return; }
    closeDetailPanel();
    return;
  }
  if (e.key === 'f' || e.key === 'F') {
    if (focusNodeId !== null) { exitFocus(); return; }
    const sel = network?.getSelectedNodes() || [];
    if (sel.length > 0) activateFocus(sel[0]);
  }
});

// ── Boot ────────────────────────────────────────────────────────────────
if (urlParams.get('topology') === 'true' || pendingFocusId) {
  topoMode = true;
  document.getElementById('btn-collapsed').classList.remove('active');
  document.getElementById('btn-topology').classList.add('active');
  document.getElementById('mode-badge').textContent = 'Topology';
  document.getElementById('mode-badge').className   = 'mode-badge topology';
  document.querySelectorAll('.topo-section').forEach(el => el.classList.add('visible'));
  document.querySelectorAll('.collapsed-section').forEach(el => el.classList.add('hidden'));
}
load();
