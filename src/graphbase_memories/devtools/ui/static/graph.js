const NODE_TYPE_REGISTRY = {
  Workspace: {
    kind: "structural",
    sidebarLabel: "Workspace",
    badgeSuffix: "workspace",
    summaryIn: ["collapsed"],
    color: {
      background: "#7c3aed",
      border: "#6d28d9",
      highlight: { background: "#8b5cf6", border: "#7c3aed" },
    },
    shape: "star",
    size: 24,
  },
  Project: {
    kind: "structural",
    sidebarLabel: "Project",
    badgeSuffix: "project",
    summaryIn: ["collapsed"],
    color: {
      background: "#2563eb",
      border: "#1d4ed8",
      highlight: { background: "#3b82f6", border: "#2563eb" },
    },
    shape: "dot",
    size: 16,
  },
  Stale: {
    kind: "structural",
    sidebarLabel: null,
    badgeSuffix: "stale",
    summaryIn: [],
    color: {
      background: "#b45309",
      border: "#92400e",
      highlight: { background: "#d97706", border: "#b45309" },
    },
    shape: "dot",
    size: 16,
  },
  Service: {
    kind: "entity-category",
    sidebarLabel: "Service",
    badgeSuffix: "service",
    summaryIn: ["topology"],
    color: {
      background: "#0ea5e9",
      border: "#0284c7",
      highlight: { background: "#38bdf8", border: "#0284c7" },
    },
    shape: "dot",
    size: 14,
  },
  BoundedContext: {
    kind: "entity-category",
    sidebarLabel: "BoundedContext",
    badgeSuffix: "boundedcontext",
    summaryIn: ["topology"],
    color: {
      background: "#f59e0b",
      border: "#d97706",
      highlight: { background: "#fbbf24", border: "#d97706" },
    },
    shape: "hexagon",
    size: 18,
  },
  Topic: {
    kind: "entity-category",
    sidebarLabel: "Topic",
    badgeSuffix: "topic",
    summaryIn: ["topology"],
    color: {
      background: "#10b981",
      border: "#059669",
      highlight: { background: "#34d399", border: "#059669" },
    },
    shape: "triangle",
    size: 12,
  },
  DataStore: {
    kind: "entity-category",
    sidebarLabel: "DataStore",
    badgeSuffix: "datastore",
    summaryIn: ["topology"],
    color: {
      background: "#8b5cf6",
      border: "#7c3aed",
      highlight: { background: "#a78bfa", border: "#7c3aed" },
    },
    shape: "database",
    size: 14,
  },
  External: {
    kind: "entity-category",
    sidebarLabel: "External",
    badgeSuffix: "external",
    summaryIn: ["topology"],
    color: {
      background: "#f97316",
      border: "#ea580c",
      highlight: { background: "#fb923c", border: "#ea580c" },
    },
    shape: "box",
    size: 13,
  },
  EntityFact: {
    kind: "entity-category",
    sidebarLabel: "Other",
    badgeSuffix: "entityfact",
    summaryIn: ["collapsed", "topology"],
    color: {
      background: "#94a3b8",
      border: "#64748b",
      highlight: { background: "#cbd5e1", border: "#64748b" },
    },
    shape: "dot",
    size: 11,
  },
  Feature: {
    kind: "topo-label",
    sidebarLabel: "Feature",
    badgeSuffix: "feature",
    summaryIn: ["topology"],
    color: {
      background: "#ec4899",
      border: "#db2777",
      highlight: { background: "#f472b6", border: "#db2777" },
    },
    shape: "star",
    size: 14,
  },
  DataSource: {
    kind: "topo-label",
    sidebarLabel: "DataSource",
    badgeSuffix: "datasource",
    summaryIn: ["topology"],
    color: {
      background: "#8b5cf6",
      border: "#7c3aed",
      highlight: { background: "#a78bfa", border: "#7c3aed" },
    },
    shape: "database",
    size: 14,
  },
  MessageQueue: {
    kind: "topo-label",
    sidebarLabel: "MessageQueue",
    badgeSuffix: "messagequeue",
    summaryIn: ["topology"],
    color: {
      background: "#10b981",
      border: "#059669",
      highlight: { background: "#34d399", border: "#059669" },
    },
    shape: "triangle",
    size: 12,
  },
};

const PALETTE = {
  dark: {
    dimColor: {
      background: "#1e293b",
      border: "#334155",
      highlight: { background: "#1e293b", border: "#334155" },
    },
    dimFont: "#0f172a",
  },
  light: {
    dimColor: {
      background: "#e2e8f0",
      border: "#cbd5e1",
      highlight: { background: "#e2e8f0", border: "#cbd5e1" },
    },
    dimFont: "#f8fafc",
  },
};

const EDGE_COLORS = {
  MEMBER_OF: { color: "#475569", highlight: "#64748b" },
  BELONGS_TO: { color: "#475569", highlight: "#64748b" },
  CROSS_SERVICE_LINK: { color: "#10b981", highlight: "#34d399" },
  AFFECTS: { color: "#ef4444", highlight: "#f87171" },
  INVOLVES: { color: "#ec4899", highlight: "#f472b6" },
  CONSUMES: { color: "#10b981", highlight: "#34d399" },
  PRODUCES: { color: "#3b82f6", highlight: "#60a5fa" },
  READS: { color: "#94a3b8", highlight: "#cbd5e1" },
  WRITES: { color: "#f59e0b", highlight: "#fbbf24" },
  CONFLICTS_WITH: { color: "#ef4444", highlight: "#f87171" },
  MERGES_INTO: { color: "#a78bfa", highlight: "#c4b5fd" },
  CALLS_DOWNSTREAM: { color: "#3b82f6", highlight: "#60a5fa" },
  CALLS_UPSTREAM: { color: "#6366f1", highlight: "#818cf8" },
  READS_FROM: { color: "#94a3b8", highlight: "#cbd5e1" },
  WRITES_TO: { color: "#f59e0b", highlight: "#fbbf24" },
  PUBLISHES_TO: { color: "#10b981", highlight: "#34d399" },
  SUBSCRIBES_TO: { color: "#06b6d4", highlight: "#22d3ee" },
  MEMBER_OF_CONTEXT: { color: "#f59e0b", highlight: "#fbbf24" },
  PART_OF: { color: "#475569", highlight: "#64748b" },
  HAS_FEATURE: { color: "#ec4899", highlight: "#f472b6" },
};

const TOPO_NODE_LABELS = new Set(
  Object.entries(NODE_TYPE_REGISTRY)
    .filter(([, value]) => value.kind === "topo-label")
    .map(([key]) => key)
);

const CLUSTER_THRESHOLD = 500;
const CLUSTER_SAMPLE_LIMIT = 6;

class GraphOverviewApp {
  static THEME_KEY = "graphbase-theme";

  constructor(documentRef = document) {
    this.document = documentRef;
    this.urlParams = new URLSearchParams(window.location.search);
    this.embedded = this.urlParams.get("embedded") === "1";
    this.rawData = null;
    this.network = null;
    this.topoMode = false;
    this.pendingFocusId = null;
    this.focusNodeId = null;
    this.physicsOn = false;
    this.workspaceDebounce = null;
    this.clickTimer = null;
    this.clusterState = { totalNodes: 0, active: false, expanded: false, skippedReason: null };
    this.clusterMeta = new Map();
    this.openClusterIds = [];
    this.nodeDataset = new vis.DataSet();
    this.edgeDataset = new vis.DataSet();
    this.refs = this.cacheRefs();
  }

  cacheRefs() {
    return {
      graph: this.document.getElementById("graph"),
      workspaceInput: this.document.getElementById("ws-input"),
      workspaceApply: this.document.getElementById("ws-apply"),
      collapsedButton: this.document.getElementById("btn-collapsed"),
      topologyButton: this.document.getElementById("btn-topology"),
      modeBadge: this.document.getElementById("mode-badge"),
      summaryPanel: this.document.getElementById("summary-panel"),
      totalLabel: this.document.getElementById("total-label"),
      refreshButton: this.document.getElementById("btn-refresh"),
      fitButton: this.document.getElementById("btn-fit"),
      physicsButton: this.document.getElementById("btn-physics"),
      exportJsonButton: this.document.getElementById("btn-export-json"),
      exportCsvButton: this.document.getElementById("btn-export-csv"),
      clusterStatus: this.document.getElementById("cluster-status"),
      clusterSummary: this.document.getElementById("cluster-summary"),
      clusterExpandButton: this.document.getElementById("btn-expand-clusters"),
      clusterResetButton: this.document.getElementById("btn-reset-clusters"),
      themeButton: this.document.getElementById("btn-theme"),
      loadingOverlay: this.document.getElementById("loading"),
      loadingHint: this.document.getElementById("loading-hint"),
      errorPanel: this.document.getElementById("error-panel"),
      errorMessage: this.document.getElementById("error-msg"),
      focusIndicator: this.document.getElementById("focus-indicator"),
      detailPanel: this.document.getElementById("detail-panel"),
      detailTypeBadge: this.document.getElementById("dp-type-badge"),
      detailId: this.document.getElementById("dp-id"),
      detailDisplay: this.document.getElementById("dp-display"),
      detailMeta: this.document.getElementById("dp-section-meta"),
      detailEdgesWrap: this.document.getElementById("dp-section-edges"),
      detailEdgeList: this.document.getElementById("dp-edge-list"),
      detailNeighborsWrap: this.document.getElementById("dp-section-neighbors"),
      detailNeighborChips: this.document.getElementById("dp-neighbor-chips"),
      detailCopy: this.document.getElementById("dp-copy"),
      detailFullDetail: this.document.getElementById("dp-full-detail"),
      detailClose: this.document.getElementById("dp-close"),
      topoSections: [...this.document.querySelectorAll(".topo-section")],
      collapsedSections: [...this.document.querySelectorAll(".collapsed-section")],
      filterInputs: [...this.document.querySelectorAll("[data-filter]")],
      namelessInputs: [...this.document.querySelectorAll("input:not([name])")],
      nodeFilters: [...this.document.querySelectorAll('[data-filter="node"]')],
      categoryFilters: [...this.document.querySelectorAll('[data-filter="category"]')],
      edgeFilters: [...this.document.querySelectorAll('[data-filter="edge"]')],
      topologyEdgeFilters: [...this.document.querySelectorAll('[data-filter="topo-edge"]')],
    };
  }

  init() {
    this.applySavedTheme();
    this.ensureInputNames();
    this.readUrlState();
    this.applyInitialMode();
    this.bindEvents();
    return this.load();
  }

  ensureInputNames() {
    this.refs.namelessInputs.forEach((input, index) => {
      input.name =
        input.dataset.label ||
        input.dataset.edge ||
        input.dataset.category ||
        input.id ||
        `graph-field-${index}`;
    });
  }

  readUrlState() {
    this.pendingFocusId = this.urlParams.get("focus");
    this.refs.workspaceInput.value =
      this.urlParams.get("workspace") || this.urlParams.get("workspace_id") || "";
    this.topoMode = this.urlParams.get("topology") === "true" || Boolean(this.pendingFocusId);
  }

  bindEvents() {
    this.refs.detailClose.addEventListener("click", () => this.closeDetailPanel());
    this.refs.collapsedButton.addEventListener("click", () => {
      if (this.topoMode) {
        this.setMode(false);
      }
    });
    this.refs.topologyButton.addEventListener("click", () => {
      if (!this.topoMode) {
        this.setMode(true);
      }
    });
    this.refs.themeButton.addEventListener("click", () => this.toggleTheme());
    this.refs.workspaceApply.addEventListener("click", () => this.load());
    this.refs.workspaceInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        this.load();
      }
    });
    this.refs.workspaceInput.addEventListener("input", () => {
      window.clearTimeout(this.workspaceDebounce);
      this.workspaceDebounce = window.setTimeout(() => this.load(), 300);
    });
    this.refs.fitButton.addEventListener("click", () => {
      if (this.network) {
        this.network.fit({
          animation: { duration: 500, easingFunction: "easeInOutQuad" },
        });
      }
    });
    this.refs.physicsButton.addEventListener("click", () => this.togglePhysics());
    this.refs.exportJsonButton.addEventListener("click", () => this.exportVisibleJson());
    this.refs.exportCsvButton.addEventListener("click", () => this.exportVisibleCsv());
    this.refs.clusterExpandButton?.addEventListener("click", () => this.expandAllClusters());
    this.refs.clusterResetButton?.addEventListener("click", () => this.reclusterVisible());
    this.refs.filterInputs.forEach((input) => {
      input.addEventListener("change", () => this.applyFilters());
    });
    this.refs.refreshButton.addEventListener("click", () => this.load());
    this.document.addEventListener("keydown", (event) => this.handleGlobalKeyDown(event));
  }

  currentTheme() {
    return this.document.documentElement.dataset.theme || "dark";
  }

  applySavedTheme() {
    const saved = window.localStorage.getItem(GraphOverviewApp.THEME_KEY);
    if (saved) {
      this.document.documentElement.dataset.theme = saved;
    }
    this.updateThemeButton();
  }

  updateThemeButton() {
    this.refs.themeButton.textContent =
      this.currentTheme() === "dark" ? "\u2600 Light" : "\u263d Dark";
  }

  toggleTheme() {
    const next = this.currentTheme() === "dark" ? "light" : "dark";
    this.document.documentElement.dataset.theme = next;
    window.localStorage.setItem(GraphOverviewApp.THEME_KEY, next);
    this.updateThemeButton();
  }

  applyInitialMode() {
    this.refs.collapsedButton.classList.toggle("active", !this.topoMode);
    this.refs.topologyButton.classList.toggle("active", this.topoMode);
    this.refs.modeBadge.textContent = this.topoMode ? "Topology" : "Collapsed";
    this.refs.modeBadge.className = this.topoMode ? "mode-badge topology" : "mode-badge";
    this.refs.topoSections.forEach((element) => {
      element.classList.toggle("visible", this.topoMode);
    });
    this.refs.collapsedSections.forEach((element) => {
      element.classList.toggle("hidden", this.topoMode);
    });
  }

  activeNodeLabels() {
    return this.refs.nodeFilters.filter((input) => input.checked).map((input) => input.dataset.label);
  }

  activeCategories() {
    return this.refs.categoryFilters
      .filter((input) => input.checked)
      .map((input) => input.dataset.category);
  }

  activeEdgeTypes() {
    const source = this.topoMode ? this.refs.topologyEdgeFilters : this.refs.edgeFilters;
    return source.filter((input) => input.checked).map((input) => input.dataset.edge);
  }

  currentVisibleGraphData() {
    if (!this.rawData) {
      return { nodes: [], edges: [] };
    }

    let visibleNodes;
    if (this.topoMode) {
      const categories = this.activeCategories();
      visibleNodes = this.rawData.nodes.filter((node) => {
        if (node.label === "EntityFact") {
          return categories.includes(node.category || "EntityFact");
        }
        if (TOPO_NODE_LABELS.has(node.label)) {
          return categories.includes(node.label);
        }
        return true;
      });
    } else {
      const labels = this.activeNodeLabels();
      visibleNodes = this.rawData.nodes.filter((node) => labels.includes(node.label));
    }

    const visibleIds = new Set(visibleNodes.map((node) => node.id));
    const edgeTypes = this.activeEdgeTypes();
    const visibleEdges = this.rawData.edges.filter(
      (edge) =>
        edgeTypes.includes(edge.type) &&
        visibleIds.has(edge.source) &&
        visibleIds.has(edge.target)
    );

    return { nodes: visibleNodes, edges: visibleEdges };
  }

  safeExportSegment(value, fallback) {
    const text = String(value || fallback).trim();
    const normalized = text.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "");
    return normalized || fallback;
  }

  exportBaseName() {
    const mode = this.topoMode ? "topology" : "collapsed";
    const workspace = this.safeExportSegment(this.refs.workspaceInput.value, "all-workspaces");
    return `graph-subgraph-${mode}-${workspace}`;
  }

  downloadBlob(filename, mimeType, content) {
    const blob = new Blob([content], { type: mimeType });
    const objectUrl = URL.createObjectURL(blob);
    const anchor = this.document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  }

  exportVisibleJson() {
    const visible = this.currentVisibleGraphData();
    const payload = {
      exported_at: new Date().toISOString(),
      mode: this.topoMode ? "topology" : "collapsed",
      workspace_id: this.refs.workspaceInput.value.trim() || null,
      filters: {
        node_labels: this.topoMode ? [] : this.activeNodeLabels(),
        categories: this.topoMode ? this.activeCategories() : [],
        edge_types: this.activeEdgeTypes(),
      },
      visible_counts: {
        nodes: visible.nodes.length,
        edges: visible.edges.length,
      },
      summary: this.rawData?.summary || null,
      nodes: visible.nodes,
      edges: visible.edges,
    };
    this.downloadBlob(
      `${this.exportBaseName()}.json`,
      "application/json",
      JSON.stringify(payload, null, 2)
    );
  }

  csvCell(value) {
    const text =
      value === null || value === undefined
        ? ""
        : typeof value === "object"
          ? JSON.stringify(value)
          : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  collectRecordKeys(records) {
    return [...new Set(records.flatMap((record) => Object.keys(record)))].sort();
  }

  exportVisibleCsv() {
    const visible = this.currentVisibleGraphData();
    const nodeKeys = this.collectRecordKeys(visible.nodes);
    const edgeKeys = this.collectRecordKeys(visible.edges);
    const columns = ["record_type", ...nodeKeys, ...edgeKeys.filter((key) => !nodeKeys.includes(key))];
    const rows = [columns];

    for (const node of visible.nodes) {
      rows.push(columns.map((column) => (column === "record_type" ? "node" : node[column])));
    }
    for (const edge of visible.edges) {
      rows.push(columns.map((column) => (column === "record_type" ? "edge" : edge[column])));
    }

    this.downloadBlob(
      `${this.exportBaseName()}.csv`,
      "text/csv;charset=utf-8",
      rows.map((row) => row.map((cell) => this.csvCell(cell)).join(",")).join("\n")
    );
  }

  clusterGroupFor(node) {
    if (node.label === "EntityFact") {
      const category = node.category || "EntityFact";
      return {
        key: `entity:${category}`,
        label: category === "EntityFact" ? "Other" : category,
        registryKey: category,
      };
    }
    if (TOPO_NODE_LABELS.has(node.label)) {
      return {
        key: `topology:${node.label}`,
        label: node.label,
        registryKey: node.label,
      };
    }
    return null;
  }

  toVisNode(node) {
    const clusterGroup = this.clusterGroupFor(node);
    if (node.label === "EntityFact") {
      const key = node.category || "EntityFact";
      const registry = NODE_TYPE_REGISTRY[key] || NODE_TYPE_REGISTRY.EntityFact;
      return {
        id: node.id,
        label: node.display,
        title: `[${key}] ${node.id}${node.fact ? `\n${node.fact.slice(0, 80)}` : ""}`,
        color: registry.color,
        shape: registry.shape,
        size: registry.size,
        font: { size: 10, color: "#e2e8f0" },
        borderWidth: 1.5,
        _clusterGroupKey: clusterGroup?.key || null,
        _raw: node,
      };
    }
    if (TOPO_NODE_LABELS.has(node.label)) {
      const registry = NODE_TYPE_REGISTRY[node.label];
      return {
        id: node.id,
        label: node.display,
        title: `[${node.label}] ${node.id}`,
        color: registry.color,
        shape: registry.shape,
        size: registry.size,
        font: { size: 10, color: "#e2e8f0" },
        borderWidth: 1.5,
        _clusterGroupKey: clusterGroup?.key || null,
        _raw: node,
      };
    }
    const colorKey = node.is_stale ? "Stale" : node.label;
    const registry = NODE_TYPE_REGISTRY[colorKey] || NODE_TYPE_REGISTRY.Project;
    return {
      id: node.id,
      label: node.display,
      title: `${node.label}: ${node.id}`,
      color: registry.color,
      size: registry.size,
      shape: registry.shape,
      font: { size: 12, color: "#e2e8f0" },
      borderWidth: 2,
      _clusterGroupKey: clusterGroup?.key || null,
      _raw: node,
    };
  }

  toVisEdge(edge, index) {
    const color = EDGE_COLORS[edge.type] || { color: "#334155", highlight: "#475569" };
    return {
      id: `e-${index}`,
      from: edge.source,
      to: edge.target,
      label: edge.type === "MEMBER_OF" || edge.type === "BELONGS_TO" ? "" : edge.type,
      color,
      arrows: { to: { enabled: true, scaleFactor: 0.5 } },
      smooth: { type: "continuous" },
      font: { size: 8, color: "#64748b", align: "middle" },
      _type: edge.type,
    };
  }

  applyFilters() {
    this.focusNodeId = null;
    this.refs.focusIndicator.classList.remove("visible");

    if (!this.rawData) {
      return;
    }

    const visible = this.currentVisibleGraphData();
    this.closeDetailPanel();
    this.clusterMeta.clear();
    this.openClusterIds = [];
    this.nodeDataset.clear();
    this.edgeDataset.clear();
    this.nodeDataset.add(visible.nodes.map((node) => this.toVisNode(node)));
    this.edgeDataset.add(visible.edges.map((edge, index) => this.toVisEdge(edge, index)));
    this.initNetwork(visible.nodes.length, { forceReset: true });
    this.applyLargeGraphClustering(visible);
  }

  updateSummary(summary) {
    const mode = this.topoMode ? "topology" : "collapsed";
    const counts = summary.counts || {};
    const rows = Object.entries(NODE_TYPE_REGISTRY)
      .filter(([, registry]) => registry.summaryIn.includes(mode) && registry.sidebarLabel !== null)
      .map(
        ([key, registry]) =>
          `<div class="summary-row"><span>${registry.sidebarLabel}</span><span>${(counts[key] ?? 0).toLocaleString()}</span></div>`
      )
      .join("");
    this.refs.summaryPanel.innerHTML = rows;

    const total = summary.total_nodes_in_graph ?? 0;
    const capped = summary.capped_at ?? 200;
    this.refs.totalLabel.textContent = this.topoMode
      ? `${(counts.EntityFact ?? 0).toLocaleString()} entities loaded`
      : total > capped
        ? `Showing ≤${capped} of ${total.toLocaleString()} total nodes`
        : `${total.toLocaleString()} total nodes`;
  }

  buildEdgeSummary(nodeId) {
    const counts = {};
    for (const edge of this.rawData?.edges || []) {
      if (edge.source === nodeId || edge.target === nodeId) {
        const direction = edge.source === nodeId ? "→" : "←";
        const key = `${direction}__${edge.type}`;
        if (!counts[key]) {
          counts[key] = { dir: direction, type: edge.type, n: 0 };
        }
        counts[key].n += 1;
      }
    }
    return Object.values(counts).sort((left, right) => right.n - left.n);
  }

  renderMetaSection(item) {
    let html = "";
    if (item.label === "Project") {
      html += "<h3>Metadata</h3>";
      if (item.staleness_days != null) {
        const pct = Math.min((item.staleness_days / 30) * 100, 100).toFixed(0);
        const color = item.is_stale ? "#d97706" : "#16a34a";
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
        for (const [key, value] of Object.entries(item.badge_counts)) {
          if (value > 0) {
            html += `<div class="dp-count-row"><span>${key}</span><span>${value}</span></div>`;
          }
        }
        html += "</div>";
      }
    } else if (item.label === "Workspace") {
      const childCount = (this.rawData?.edges || []).filter(
        (edge) => edge.target === item.id && edge.type === "MEMBER_OF"
      ).length;
      html += `<h3>Metadata</h3><div class="dp-field"><span class="dp-label">Projects</span><span class="dp-value">${childCount}</span></div>`;
    } else if (item.label === "EntityFact") {
      html += "<h3>Metadata</h3>";
      if (item.category) {
        html += `<div class="dp-field"><span class="dp-label">Category</span><span class="dp-value">${item.category}</span></div>`;
      }
      if (item.scope) {
        html += `<div class="dp-field"><span class="dp-label">Scope</span><span class="dp-value">${item.scope}</span></div>`;
      }
      if (item.fact) {
        html += `<div class="dp-field"><span class="dp-label">Fact</span><div class="dp-value fact">${item.fact}</div></div>`;
      }
    } else {
      html += "<h3>Metadata</h3>";
      if (item.health_status) {
        html += `<div class="dp-field"><span class="dp-label">Health</span><span class="dp-value">${item.health_status}</span></div>`;
      }
      if (item.source_type) {
        html += `<div class="dp-field"><span class="dp-label">Source Type</span><span class="dp-value">${item.source_type}</span></div>`;
      }
      if (item.queue_type) {
        html += `<div class="dp-field"><span class="dp-label">Queue Type</span><span class="dp-value">${item.queue_type}</span></div>`;
      }
      if (item.domain) {
        html += `<div class="dp-field"><span class="dp-label">Domain</span><span class="dp-value">${item.domain}</span></div>`;
      }
    }
    return (
      html || '<p style="color:#475569;font-size:12px;padding:4px 0">No additional metadata.</p>'
    );
  }

  renderClusterMetaSection(meta) {
    const sampleMembers = meta.sampleMembers
      .map(
        (member) => `
          <div class="dp-count-row">
            <span>${member.display}</span>
            <span>${member.label}</span>
          </div>
        `
      )
      .join("");
    const remainder =
      meta.memberCount > meta.sampleMembers.length
        ? `<div class="dp-field"><span class="dp-label">More Members</span><span class="dp-value">${(meta.memberCount - meta.sampleMembers.length).toLocaleString()} additional nodes inside this cluster.</span></div>`
        : "";
    return `
      <h3>Cluster</h3>
      <div class="dp-field">
        <span class="dp-label">Grouping</span>
        <span class="dp-value">${meta.groupLabel}</span>
      </div>
      <div class="dp-field">
        <span class="dp-label">Contained Nodes</span>
        <span class="dp-value">${meta.memberCount.toLocaleString()}</span>
      </div>
      <div class="dp-field">
        <span class="dp-label">Sample Members</span>
        ${sampleMembers || '<span class="dp-value">No members available.</span>'}
      </div>
      ${remainder}
    `;
  }

  isClusterNode(nodeId) {
    return Boolean(this.network && typeof this.network.isCluster === "function" && this.network.isCluster(nodeId));
  }

  openClusterPanel(clusterId) {
    const meta = this.clusterMeta.get(clusterId);
    if (!meta) {
      return;
    }

    this.refs.detailId.textContent = clusterId;
    this.refs.detailDisplay.textContent = meta.display;
    this.refs.detailTypeBadge.textContent = "Cluster";
    this.refs.detailTypeBadge.className = "inspect-badge badge-cluster";
    this.refs.detailFullDetail.textContent = "Expand Cluster";
    this.refs.detailFullDetail.onclick = () => this.expandCluster(clusterId);
    this.refs.detailFullDetail.disabled = false;

    this.refs.detailCopy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(meta.memberIds.join("\n"));
      } catch {}
      this.refs.detailCopy.textContent = "Copied!";
      window.setTimeout(() => {
        this.refs.detailCopy.textContent = "Copy";
      }, 1500);
    };

    this.refs.detailMeta.innerHTML = this.renderClusterMetaSection(meta);
    this.refs.detailEdgesWrap.style.display = "none";

    if (meta.sampleMembers.length > 0) {
      this.refs.detailNeighborsWrap.style.display = "";
      this.refs.detailNeighborChips.innerHTML = meta.sampleMembers
        .map(
          (member) =>
            `<button class="neighbor-chip" data-cluster="${clusterId}" data-nid="${member.id}" title="${member.id}">${member.display}</button>`
        )
        .join("");
      this.refs.detailNeighborChips.querySelectorAll(".neighbor-chip").forEach((button) => {
        button.addEventListener("click", () => {
          this.expandCluster(button.dataset.cluster, button.dataset.nid);
        });
      });
    } else {
      this.refs.detailNeighborsWrap.style.display = "none";
    }

    this.refs.detailPanel.classList.add("open");
  }

  openDetailPanel(nodeId) {
    if (this.isClusterNode(nodeId)) {
      this.openClusterPanel(nodeId);
      return;
    }
    const item = this.rawData?.nodes.find((node) => node.id === nodeId);
    if (!item) {
      return;
    }

    this.refs.detailId.textContent = item.id;
    this.refs.detailDisplay.textContent = item.display;
    this.refs.detailFullDetail.textContent = "View Full Detail";
    this.refs.detailFullDetail.disabled = false;
    this.refs.detailFullDetail.onclick = () => {
      this.openMemoryDetail(item.id);
    };

    const badgeLabel = item.label === "EntityFact" && item.category ? item.category : item.label;
    this.refs.detailTypeBadge.textContent = badgeLabel;
    this.refs.detailTypeBadge.className = `inspect-badge badge-${badgeLabel.toLowerCase()}`;

    this.refs.detailCopy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(item.id);
      } catch {}
      this.refs.detailCopy.textContent = "Copied!";
      window.setTimeout(() => {
        this.refs.detailCopy.textContent = "Copy";
      }, 1500);
    };

    this.refs.detailMeta.innerHTML = this.renderMetaSection(item);

    const edges = this.buildEdgeSummary(nodeId);
    if (edges.length > 0) {
      this.refs.detailEdgesWrap.style.display = "";
      this.refs.detailEdgeList.innerHTML = edges
        .map(
          (edge) => `<div class="dp-edge-row">
            <span><span class="dp-edge-dir">${edge.dir}</span>${edge.type}</span>
            <span class="dp-edge-count">×${edge.n}</span>
          </div>`
        )
        .join("");
    } else {
      this.refs.detailEdgesWrap.style.display = "none";
    }

    const neighborIds = this.network
      ? [
          ...new Set([
            ...this.network.getConnectedNodes(nodeId, "from"),
            ...this.network.getConnectedNodes(nodeId, "to"),
          ]),
        ].slice(0, 5)
      : [];

    if (neighborIds.length > 0) {
      this.refs.detailNeighborsWrap.style.display = "";
      this.refs.detailNeighborChips.innerHTML = neighborIds
        .map((neighborId) => {
          const neighbor = this.rawData?.nodes.find((node) => node.id === neighborId);
          const label = neighbor ? neighbor.display : neighborId;
          return `<button class="neighbor-chip" data-nid="${neighborId}" title="${neighborId}">${label}</button>`;
        })
        .join("");
      this.refs.detailNeighborChips.querySelectorAll(".neighbor-chip").forEach((button) => {
        button.addEventListener("click", () => {
          if (this.network) {
            this.network.selectNodes([button.dataset.nid]);
          }
          this.openDetailPanel(button.dataset.nid);
        });
      });
    } else {
      this.refs.detailNeighborsWrap.style.display = "none";
    }

    this.refs.detailPanel.classList.add("open");
  }

  closeDetailPanel() {
    this.refs.detailPanel.classList.remove("open");
  }

  activateFocus(nodeId) {
    this.focusNodeId = nodeId;
    const neighbors = new Set([
      nodeId,
      ...(this.network?.getConnectedNodes(nodeId, "from") || []),
      ...(this.network?.getConnectedNodes(nodeId, "to") || []),
    ]);
    const allNodes = this.nodeDataset.get({ returnType: "Object" });
    const updates = Object.keys(allNodes).map((id) => {
      if (id === nodeId) {
        const original = allNodes[id]._raw ? this.toVisNode(allNodes[id]._raw) : allNodes[id];
        return {
          id,
          opacity: 1,
          borderWidth: 4,
          borderDashes: false,
          color: {
            ...original.color,
            border: "#ffffff",
            highlight: { ...original.color?.highlight, border: "#ffffff" },
          },
        };
      }
      if (neighbors.has(id)) {
        const raw = allNodes[id]._raw;
        if (raw) {
          return { ...this.toVisNode(raw), opacity: 1, borderDashes: false };
        }
        return { id, opacity: 1, borderWidth: 1.5, borderDashes: false };
      }
      const palette = PALETTE[this.currentTheme()];
      return {
        id,
        opacity: 0.12,
        color: palette.dimColor,
        borderDashes: [4, 4],
        font: { color: palette.dimFont },
      };
    });

    this.nodeDataset.update(updates);
    this.network?.focus(nodeId, {
      scale: 1.4,
      animation: { duration: 400, easingFunction: "easeInOutQuad" },
    });
    this.refs.focusIndicator.classList.add("visible");
  }

  exitFocus() {
    if (this.focusNodeId === null) {
      return;
    }
    this.focusNodeId = null;
    this.refs.focusIndicator.classList.remove("visible");
    this.applyFilters();
  }

  buildClusterBuckets(nodes) {
    const buckets = new Map();
    for (const node of nodes) {
      const clusterGroup = this.clusterGroupFor(node);
      if (!clusterGroup) {
        continue;
      }
      if (!buckets.has(clusterGroup.key)) {
        buckets.set(clusterGroup.key, { ...clusterGroup, nodes: [] });
      }
      buckets.get(clusterGroup.key).nodes.push(node);
    }
    return [...buckets.values()].filter((bucket) => bucket.nodes.length >= 2);
  }

  clusterNodeProperties(bucket, clusterId) {
    const registry = NODE_TYPE_REGISTRY[bucket.registryKey] || NODE_TYPE_REGISTRY.EntityFact;
    return {
      id: clusterId,
      label: `${bucket.label} ×${bucket.nodes.length}`,
      title: `${bucket.nodes.length} ${bucket.label} nodes`,
      shape: "database",
      size: Math.min(18 + Math.round(bucket.nodes.length / 12), 42),
      borderWidth: 2,
      font: { size: 12, color: "#e2e8f0", face: "inherit" },
      color: registry.color,
    };
  }

  setClusterState(nextState) {
    this.clusterState = {
      totalNodes: 0,
      active: false,
      expanded: false,
      skippedReason: null,
      clusterCount: 0,
      clusteredNodes: 0,
      ...nextState,
    };
    this.updateClusterUi();
  }

  updateClusterUi() {
    if (!this.refs.clusterStatus || !this.refs.clusterSummary) {
      return;
    }

    const state = this.clusterState;
    if (state.active) {
      this.refs.clusterStatus.hidden = false;
      this.refs.clusterSummary.textContent =
        `Clustering active: ${state.totalNodes.toLocaleString()} visible nodes condensed into ${state.clusterCount.toLocaleString()} groups. Double-click a cluster to expand it.`;
      this.refs.clusterExpandButton.hidden = false;
      this.refs.clusterExpandButton.disabled = false;
      this.refs.clusterResetButton.hidden = false;
      this.refs.clusterResetButton.disabled = false;
      return;
    }

    if (state.expanded) {
      this.refs.clusterStatus.hidden = false;
      this.refs.clusterSummary.textContent =
        "Clusters expanded. Use Re-cluster to condense the visible graph again.";
      this.refs.clusterExpandButton.hidden = true;
      this.refs.clusterResetButton.hidden = false;
      this.refs.clusterResetButton.disabled = false;
      return;
    }

    if (state.skippedReason === "focus") {
      this.refs.clusterStatus.hidden = false;
      this.refs.clusterSummary.textContent =
        "Large graph detected. Clustering is paused so the requested node can stay directly inspectable.";
      this.refs.clusterExpandButton.hidden = true;
      this.refs.clusterResetButton.hidden = false;
      this.refs.clusterResetButton.disabled = false;
      return;
    }

    this.refs.clusterStatus.hidden = true;
    this.refs.clusterExpandButton.hidden = true;
    this.refs.clusterResetButton.hidden = true;
  }

  applyLargeGraphClustering(visible) {
    const totalNodes = visible.nodes.length;
    if (!this.network || totalNodes <= CLUSTER_THRESHOLD) {
      this.setClusterState({ totalNodes });
      return;
    }

    if (this.pendingFocusId) {
      this.setClusterState({ totalNodes, skippedReason: "focus" });
      return;
    }

    const buckets = this.buildClusterBuckets(visible.nodes);
    if (buckets.length === 0) {
      this.setClusterState({ totalNodes });
      return;
    }

    let clusterCount = 0;
    let clusteredNodes = 0;

    for (const bucket of buckets) {
      const clusterId = `cluster:${bucket.key}`;
      const meta = {
        id: clusterId,
        display: `${bucket.label} Cluster`,
        groupLabel: bucket.label,
        memberCount: bucket.nodes.length,
        memberIds: bucket.nodes.map((node) => node.id),
        sampleMembers: bucket.nodes.slice(0, CLUSTER_SAMPLE_LIMIT).map((node) => ({
          id: node.id,
          display: node.display,
          label: node.category || node.label,
        })),
      };
      this.clusterMeta.set(clusterId, meta);
      this.network.cluster({
        joinCondition: (nodeOptions) => nodeOptions._clusterGroupKey === bucket.key,
        processProperties: (clusterOptions, childNodes) => ({
          ...clusterOptions,
          label: `${bucket.label} ×${childNodes.length}`,
          title: `${childNodes.length} ${bucket.label} nodes`,
          mass: Math.max(childNodes.length, 2),
          value: childNodes.length,
        }),
        clusterNodeProperties: this.clusterNodeProperties(bucket, clusterId),
      });
      if (this.isClusterNode(clusterId)) {
        this.openClusterIds.push(clusterId);
        clusterCount += 1;
        clusteredNodes += bucket.nodes.length;
      }
    }

    this.setClusterState({
      totalNodes,
      active: clusterCount > 0,
      clusterCount,
      clusteredNodes,
    });
  }

  selectAndInspectNode(nodeId) {
    if (!this.network) {
      return;
    }
    window.setTimeout(() => {
      this.network.selectNodes([nodeId]);
      this.network.focus(nodeId, {
        scale: 1.2,
        animation: { duration: 350, easingFunction: "easeInOutQuad" },
      });
      this.openDetailPanel(nodeId);
    }, 60);
  }

  expandCluster(clusterId, nodeId = null) {
    if (!this.isClusterNode(clusterId)) {
      if (nodeId) {
        this.selectAndInspectNode(nodeId);
      }
      return;
    }

    this.network.openCluster(clusterId);
    this.openClusterIds = this.openClusterIds.filter((id) => id !== clusterId);

    if (this.openClusterIds.some((id) => this.isClusterNode(id))) {
      this.setClusterState({
        ...this.clusterState,
        active: true,
        expanded: false,
        clusterCount: this.openClusterIds.filter((id) => this.isClusterNode(id)).length,
      });
    } else {
      this.setClusterState({
        totalNodes: this.clusterState.totalNodes,
        expanded: true,
      });
    }

    if (nodeId) {
      this.selectAndInspectNode(nodeId);
    } else {
      this.closeDetailPanel();
    }
  }

  expandAllClusters() {
    if (!this.network) {
      return;
    }
    for (const clusterId of this.openClusterIds) {
      if (this.isClusterNode(clusterId)) {
        this.network.openCluster(clusterId);
      }
    }
    this.openClusterIds = [];
    this.closeDetailPanel();
    this.setClusterState({
      totalNodes: this.clusterState.totalNodes,
      expanded: true,
    });
  }

  reclusterVisible() {
    this.applyFilters();
  }

  networkOptions(nodeCount) {
    const isLarge = nodeCount > 200;
    return {
      physics: {
        enabled: this.physicsOn,
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          avoidOverlap: isLarge ? 0.3 : 0.5,
          gravitationalConstant: isLarge ? -30 : -50,
          springLength: isLarge ? 80 : 100,
        },
        stabilization: {
          iterations: isLarge ? 80 : 150,
          updateInterval: isLarge ? 50 : 25,
        },
      },
      interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
      layout: { improvedLayout: false },
    };
  }

  initNetwork(nodeCount, { forceReset = false } = {}) {
    const options = this.networkOptions(nodeCount);
    if (forceReset && this.network) {
      this.network.destroy();
      this.network = null;
    }
    if (!this.network) {
      this.network = new vis.Network(
        this.refs.graph,
        { nodes: this.nodeDataset, edges: this.edgeDataset },
        options
      );
      this.bindNetworkEvents();
      window.network = this.network;
    } else {
      this.network.setOptions(options);
    }
  }

  bindNetworkEvents() {
    this.network.on("click", (params) => {
      window.clearTimeout(this.clickTimer);
      if (params.nodes.length === 0) {
        this.clickTimer = window.setTimeout(() => this.closeDetailPanel(), 75);
        return;
      }
      const nodeId = params.nodes[0];
      this.clickTimer = window.setTimeout(() => {
        if (this.isClusterNode(nodeId)) {
          this.openClusterPanel(nodeId);
          return;
        }
        this.openDetailPanel(nodeId);
      }, 75);
    });

    this.network.on("doubleClick", (params) => {
      window.clearTimeout(this.clickTimer);
      if (params.nodes.length === 0) {
        return;
      }
      const nodeId = params.nodes[0];
      if (this.isClusterNode(nodeId)) {
        this.expandCluster(nodeId);
        return;
      }
      if (this.focusNodeId === nodeId) {
        this.exitFocus();
      } else {
        this.activateFocus(nodeId);
      }
    });

    this.network.on("stabilizationIterationsDone", () => {
      if (!this.physicsOn) {
        this.network.setOptions({ physics: { enabled: false } });
      }
    });
  }

  applyPendingFocus() {
    if (!this.pendingFocusId || !this.network) {
      return;
    }
    const node = this.nodeDataset.get(this.pendingFocusId);
    if (!node) {
      return;
    }
    this.network.selectNodes([this.pendingFocusId]);
    this.network.focus(this.pendingFocusId, {
      scale: 1.2,
      animation: { duration: 400, easingFunction: "easeInOutQuad" },
    });
    this.openDetailPanel(this.pendingFocusId);
    this.pendingFocusId = null;
  }

  buildOverviewUrl() {
    const workspaceId = this.refs.workspaceInput.value.trim();
    const params = new URLSearchParams();
    if (workspaceId) {
      params.set("workspace_id", workspaceId);
    }
    if (this.topoMode) {
      params.set("topology", "true");
    }
    return params.toString() ? `/graph/overview?${params.toString()}` : "/graph/overview";
  }

  openMemoryDetail(nodeId) {
    const destination = `/ui/index.html#memory/${encodeURIComponent(nodeId)}`;
    if (this.embedded && window.parent && window.parent !== window) {
      try {
        window.parent.location.href = destination;
        return;
      } catch {}
    }
    window.location.href = destination;
  }

  async load() {
    this.focusNodeId = null;
    this.refs.focusIndicator.classList.remove("visible");
    this.closeDetailPanel();
    this.refs.loadingOverlay.style.display = "flex";
    this.refs.errorPanel.style.display = "none";
    this.refs.refreshButton.disabled = true;
    this.refs.loadingHint.textContent = this.topoMode
      ? "Topology mode may take a moment for large graphs…"
      : "";

    try {
      const response = await fetch(this.buildOverviewUrl());
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      this.rawData = await response.json();
      this.updateSummary(this.rawData.summary);
      this.applyFilters();
      this.applyPendingFocus();
      this.refs.loadingOverlay.style.display = "none";
    } catch (error) {
      this.refs.loadingOverlay.style.display = "none";
      this.refs.errorMessage.textContent = `Failed to load: ${error.message}`;
      this.refs.errorPanel.style.display = "flex";
    } finally {
      this.refs.refreshButton.disabled = false;
    }
  }

  setMode(topology) {
    this.topoMode = topology;
    this.applyInitialMode();
    this.load();
  }

  togglePhysics() {
    if (!this.network) {
      return;
    }
    this.physicsOn = !this.physicsOn;
    this.network.setOptions({ physics: { enabled: this.physicsOn } });
    this.refs.physicsButton.textContent = this.physicsOn ? "⚡ Physics ON" : "⚡ Physics";
    this.refs.physicsButton.classList.toggle("physics-on", this.physicsOn);
  }

  handleGlobalKeyDown(event) {
    if (this.document.activeElement?.tagName === "INPUT") {
      return;
    }
    if (event.key === "Escape") {
      if (this.focusNodeId !== null) {
        this.exitFocus();
        return;
      }
      this.closeDetailPanel();
      return;
    }
    if (event.key === "f" || event.key === "F") {
      if (this.focusNodeId !== null) {
        this.exitFocus();
        return;
      }
      const selected = this.network?.getSelectedNodes() || [];
      if (selected.length > 0) {
        if (this.isClusterNode(selected[0])) {
          this.expandCluster(selected[0]);
          return;
        }
        this.activateFocus(selected[0]);
      }
    }
  }
}

window.GraphOverviewApp = GraphOverviewApp;
window.graphOverviewApp = new GraphOverviewApp();
window.graphOverviewApp.init();
