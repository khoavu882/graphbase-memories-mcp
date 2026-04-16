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
  Service:        { kind: 'entity-category', sidebarLabel: 'Service',        badgeSuffix: 'service',        summaryIn: ['topology'], bg: '#0ea5e9', border: '#0284c7', highlight: '#38bdf8', shape: 'dot',      size: 14 },
  BoundedContext: { kind: 'entity-category', sidebarLabel: 'BoundedContext', badgeSuffix: 'boundedcontext', summaryIn: ['topology'], bg: '#f59e0b', border: '#d97706', highlight: '#fbbf24', shape: 'hexagon',  size: 18 },
  Topic:          { kind: 'entity-category', sidebarLabel: 'Topic',          badgeSuffix: 'topic',          summaryIn: ['topology'], bg: '#10b981', border: '#059669', highlight: '#34d399', shape: 'triangle', size: 12 },
  DataStore:      { kind: 'entity-category', sidebarLabel: 'DataStore',      badgeSuffix: 'datastore',      summaryIn: ['topology'], bg: '#8b5cf6', border: '#7c3aed', highlight: '#a78bfa', shape: 'database', size: 14 },
  External:       { kind: 'entity-category', sidebarLabel: 'External',       badgeSuffix: 'external',       summaryIn: ['topology'], bg: '#f97316', border: '#ea580c', highlight: '#fb923c', shape: 'box',      size: 13 },
  EntityFact:     { kind: 'entity-category', sidebarLabel: 'Other',          badgeSuffix: 'entityfact',     summaryIn: ['collapsed', 'topology'], bg: '#94a3b8', border: '#64748b', highlight: '#cbd5e1', shape: 'dot', size: 11 },
  // First-class topology labels — n.label IS the category key (T5.3)
  Feature:      { kind: 'topo-label', sidebarLabel: 'Feature',      badgeSuffix: 'feature',      summaryIn: ['topology'], bg: '#ec4899', border: '#db2777', highlight: '#f472b6', shape: 'star',     size: 14 },
  DataSource:   { kind: 'topo-label', sidebarLabel: 'DataSource',   badgeSuffix: 'datasource',   summaryIn: ['topology'], bg: '#8b5cf6', border: '#7c3aed', highlight: '#a78bfa', shape: 'database', size: 14 },
  MessageQueue: { kind: 'topo-label', sidebarLabel: 'MessageQueue', badgeSuffix: 'messagequeue', summaryIn: ['topology'], bg: '#10b981', border: '#059669', highlight: '#34d399', shape: 'triangle', size: 12 },
};

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
const nodeDataset = new vis.DataSet();
const edgeDataset = new vis.DataSet();

// ── URL params ──────────────────────────────────────────────────────────
const urlParams = new URLSearchParams(window.location.search);
const wsInput = document.getElementById('ws-input');
wsInput.value = urlParams.get('workspace_id') || '';

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
function toVisNode(n) {
  // EntityFact nodes — styled by n.category via registry
  if (n.label === 'EntityFact') {
    const key = n.category || 'EntityFact';
    const reg = NODE_TYPE_REGISTRY[key] || NODE_TYPE_REGISTRY.EntityFact;
    return {
      id: n.id, label: n.display,
      title: `[${key}] ${n.id}${n.fact ? '\n' + n.fact.slice(0, 80) : ''}`,
      color: { background: reg.bg, border: reg.border, highlight: { background: reg.highlight, border: reg.border } },
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
      color: { background: reg.bg, border: reg.border, highlight: { background: reg.highlight, border: reg.border } },
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

// ── Inspect panel ───────────────────────────────────────────────────────
function showInspect(nodeId) {
  const item = rawData && rawData.nodes.find(n => n.id === nodeId);
  if (!item) return;

  document.getElementById('insp-id').textContent      = item.id;
  document.getElementById('insp-display').textContent = item.display;

  const lbl = document.getElementById('insp-label-badge');
  lbl.textContent  = item.label;
  lbl.className    = `inspect-badge badge-${item.label.toLowerCase()}`;

  // Category (EntityFact only)
  const catWrap = document.getElementById('insp-category-wrap');
  const catBadge = document.getElementById('insp-category-badge');
  if (item.label === 'EntityFact' && item.category) {
    catWrap.style.display    = '';
    catBadge.textContent     = item.category;
  } else {
    catWrap.style.display = 'none';
  }

  // Fact (EntityFact only)
  const factWrap = document.getElementById('insp-fact-wrap');
  const factEl   = document.getElementById('insp-fact');
  if (item.label === 'EntityFact' && item.fact) {
    factWrap.style.display = '';
    factEl.textContent     = item.fact;
  } else {
    factWrap.style.display = 'none';
  }

  // Staleness
  const staleBadge = document.getElementById('insp-stale-badge');
  const staleWrap  = document.getElementById('insp-stale-wrap');
  if (item.staleness_days != null) {
    staleWrap.style.display  = '';
    staleBadge.textContent   = item.is_stale
      ? `Stale — ${item.staleness_days.toFixed(1)} days`
      : `Fresh — ${item.staleness_days.toFixed(1)} days`;
    staleBadge.className = `inspect-badge ${item.is_stale ? 'badge-stale' : 'badge-fresh'}`;
  } else {
    staleWrap.style.display = 'none';
  }

  // Badge counts (Project nodes)
  const countsWrap = document.getElementById('insp-counts-wrap');
  const countsEl   = document.getElementById('insp-counts');
  if (item.badge_counts) {
    countsWrap.style.display = '';
    countsEl.innerHTML = Object.entries(item.badge_counts)
      .map(([k, v]) => `<div class="count-item"><div class="count-num">${v}</div><div class="count-lbl">${k}</div></div>`)
      .join('');
  } else {
    countsWrap.style.display = 'none';
  }

  document.getElementById('inspect').classList.add('visible');
}

document.getElementById('inspect-close').addEventListener('click', () => {
  document.getElementById('inspect').classList.remove('visible');
  if (network) network.unselectAll();
});

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
    network.on('click', params => {
      if (params.nodes.length > 0) showInspect(params.nodes[0]);
      else document.getElementById('inspect').classList.remove('visible');
    });
    network.on('stabilizationIterationsDone', () => {
      network.setOptions({ physics: { enabled: false } });
    });
  } else {
    network.setOptions(options);
  }
}

// ── Fetch & render ──────────────────────────────────────────────────────
async function load() {
  document.getElementById('loading').style.display   = 'flex';
  document.getElementById('error-panel').style.display = 'none';
  document.getElementById('btn-refresh').disabled    = true;
  document.getElementById('inspect').classList.remove('visible');

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

// ── Boot ────────────────────────────────────────────────────────────────
if (urlParams.get('topology') === 'true') {
  topoMode = true;
  document.getElementById('btn-collapsed').classList.remove('active');
  document.getElementById('btn-topology').classList.add('active');
  document.getElementById('mode-badge').textContent = 'Topology';
  document.getElementById('mode-badge').className   = 'mode-badge topology';
  document.querySelectorAll('.topo-section').forEach(el => el.classList.add('visible'));
  document.querySelectorAll('.collapsed-section').forEach(el => el.classList.add('hidden'));
}
load();
