// Graphbase Devtools — Alpine.js data stores
// Served as static file from devtools/ui/static/app.js

document.addEventListener('alpine:init', () => {
  Alpine.store('neo4j', {
    status: 'connecting',
    toolCount: 0,
    get connected() { return this.status === 'ok' || this.status === 'degraded'; },
  });
});

function appRoot() {
  return { tab: "projects" };
}

function connectionStatus() {
  return {
    get status()    { return Alpine.store('neo4j').status; },
    get toolCount() { return Alpine.store('neo4j').toolCount; },
    statusLabel() {
      return { connecting: "Connecting", ok: "Connected", degraded: "Degraded", disconnected: "Disconnected" }[this.status] || this.status;
    },
    init() {
      const es = new EventSource("/events");
      es.addEventListener("heartbeat", (e) => {
        const d = JSON.parse(e.data);
        Alpine.store('neo4j').status    = d.neo4j_connected ? "ok" : "degraded";
        Alpine.store('neo4j').toolCount = d.tool_count || 0;
      });
      es.onerror = () => { Alpine.store('neo4j').status = "disconnected"; };
    },
  };
}

function projectsPanel() {
  return {
    projects: [],
    loading: false,
    async init() {
      this.loading = true;
      try {
        const r = await fetch("/projects");
        this.projects = await r.json();
      } finally {
        this.loading = false;
      }
    },
  };
}

function toolsPanel() {
  return {
    tools: [],
    selected: null,
    filter: "",
    params: {},
    result: null,
    invoking: false,
    awaitingConfirm: false,
    async init() {
      const r = await fetch("/tools");
      this.tools = await r.json();
    },
    filteredTools() {
      if (!this.filter) return this.tools;
      const q = this.filter.toLowerCase();
      return this.tools.filter((t) => t.name.includes(q) || t.module.includes(q));
    },
    select(tool) {
      this.selected = tool;
      this.params = {};
      this.result = null;
      this.awaitingConfirm = false;
    },
    async invoke() {
      if (!this.selected || !this.selected.http_invocable) return;
      this.invoking = true;
      this.awaitingConfirm = false;
      try {
        const r = await fetch(`/tools/${this.selected.name}/invoke`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ params: this._coerceParams(), confirm: false }),
        });
        this.result = await r.json();
        if (this.result.status === "preview") this.awaitingConfirm = true;
      } finally {
        this.invoking = false;
      }
    },
    async confirm() {
      this.invoking = true;
      this.awaitingConfirm = false;
      try {
        const r = await fetch(`/tools/${this.selected.name}/invoke`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ params: this._coerceParams(), confirm: true }),
        });
        this.result = await r.json();
      } finally {
        this.invoking = false;
      }
    },
    _coerceParams() {
      // Attempt to parse numeric/boolean strings
      const out = {};
      const schema = this.selected?.input_schema?.properties || {};
      for (const [k, v] of Object.entries(this.params)) {
        const type = schema[k]?.type;
        if (type === "integer" || type === "number") {
          out[k] = Number(v);
        } else if (type === "boolean") {
          out[k] = v === "true" || v === true;
        } else {
          out[k] = v;
        }
      }
      return out;
    },
  };
}

function healthPanel() {
  return {
    stats: null,
    workspaceId: "",
    workspaceReport: null,
    loadingWorkspace: false,
    async init() {
      const r = await fetch("/graph/stats");
      this.stats = await r.json();
    },
    async loadWorkspaceHealth() {
      if (!this.workspaceId.trim()) return;
      this.loadingWorkspace = true;
      this.workspaceReport = null;
      try {
        const r = await fetch(`/graph/stats/workspace/${encodeURIComponent(this.workspaceId.trim())}`);
        this.workspaceReport = await r.json();
      } finally {
        this.loadingWorkspace = false;
      }
    },
  };
}

function memoryPanel() {
  return {
    query: "",
    label: "",
    results: [],
    searching: false,
    searched: false,
    async search() {
      if (!this.query.trim()) return;
      this.searching = true;
      try {
        const r = await fetch("/memory/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: this.query,
            label: this.label || undefined,
            limit: 30,
          }),
        });
        this.results = await r.json();
        this.searched = true;
      } finally {
        this.searching = false;
      }
    },
  };
}

function hygienePanel() {
  return {
    status: null,
    report: null,
    running: false,
    runProjectId: "",
    runScope: "global",
    checkPendingOnly: false,
    async init() {
      const r = await fetch("/hygiene/status");
      this.status = await r.json();
    },
    async runHygiene() {
      this.running = true;
      try {
        const r = await fetch("/hygiene/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: this.runProjectId || null,
            scope: this.runScope,
            check_pending_only: this.checkPendingOnly,
          }),
        });
        this.report = await r.json();
      } finally {
        this.running = false;
      }
    },
  };
}
