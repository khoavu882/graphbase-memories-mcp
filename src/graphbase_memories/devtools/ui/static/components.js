(function () {
  const ui = window.DevtoolsUI;

  function relativeTime(value) {
    if (!value) {
      return "Unknown";
    }
    let parsedValue = value;
    if (typeof value === "object") {
      const datePart = value._DateTime__date;
      const timePart = value._DateTime__time;
      if (datePart && timePart) {
        const year = datePart._Date__year;
        const month = String(datePart._Date__month).padStart(2, "0");
        const day = String(datePart._Date__day).padStart(2, "0");
        const hour = String(timePart._Time__hour).padStart(2, "0");
        const minute = String(timePart._Time__minute).padStart(2, "0");
        const second = String(timePart._Time__second).padStart(2, "0");
        parsedValue = `${year}-${month}-${day}T${hour}:${minute}:${second}Z`;
      }
    }
    const date = new Date(parsedValue);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    const diffMs = date.getTime() - Date.now();
    const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
    const minutes = Math.round(diffMs / 60000);
    const hours = Math.round(minutes / 60);
    const days = Math.round(hours / 24);
    if (Math.abs(minutes) < 60) {
      return formatter.format(minutes, "minute");
    }
    if (Math.abs(hours) < 48) {
      return formatter.format(hours, "hour");
    }
    return formatter.format(days, "day");
  }

  function projectState(project) {
    if (project?.is_stale) {
      return "stale";
    }
    return project?.status === "active" ? "active" : "idle";
  }

  function sortProjects(projects, sortBy) {
    const copy = [...projects];
    copy.sort((left, right) => {
      if (sortBy === "name") {
        return String(left.name || left.id).localeCompare(String(right.name || right.id));
      }
      if (sortBy === "last_seen") {
        return String(right.last_seen || "").localeCompare(String(left.last_seen || ""));
      }
      if (sortBy === "entity_count") {
        return (right.node_counts?.EntityFact || 0) - (left.node_counts?.EntityFact || 0);
      }
      return (right.staleness_days ?? -1) - (left.staleness_days ?? -1);
    });
    return copy;
  }

  function normaliseListResponse(payload) {
    if (Array.isArray(payload)) {
      return payload;
    }
    return payload.items || [];
  }

  function getSchemaProperties(tool) {
    return Object.entries(tool?.input_schema?.properties || {});
  }

  function getToolHistory() {
    try {
      return JSON.parse(window.sessionStorage.getItem("devtools.toolHistory") || "{}");
    } catch {
      return {};
    }
  }

  function saveToolHistory(history) {
    window.sessionStorage.setItem("devtools.toolHistory", JSON.stringify(history));
  }

  document.addEventListener("alpine:init", () => {
    Alpine.data("projectsView", () => ({
      initialised: false,
      loading: false,
      error: "",
      projects: [],
      sortBy: "staleness",
      statusFilter: "all",
      detailLoading: false,
      detailProject: null,
      detailItems: [],
      detailPage: 1,
      detailPageSize: 10,
      init() {
        if (this.initialised) {
          return;
        }
        this.initialised = true;
        this.loadProjects();
        this.$watch("$store.nav.subView", async (projectId) => {
          if (Alpine.store("nav").view !== "projects") {
            return;
          }
          if (projectId) {
            await this.loadProjectDetail(projectId);
          } else {
            this.detailProject = null;
            this.detailItems = [];
          }
        });
      },
      async loadProjects() {
        this.loading = true;
        this.error = "";
        try {
          this.projects = await ui.fetchJson("/projects");
          if (Alpine.store("nav").subView) {
            await this.loadProjectDetail(Alpine.store("nav").subView);
          }
        } catch (error) {
          this.error = error.message || "Failed to load projects";
        } finally {
          this.loading = false;
        }
      },
      async loadProjectDetail(projectId) {
        this.detailLoading = true;
        try {
          const [project, items] = await Promise.all([
            ui.fetchJson(`/projects/${encodeURIComponent(projectId)}`),
            ui.fetchJson(`/memory?project_id=${encodeURIComponent(projectId)}&limit=100`),
          ]);
          this.detailProject = project;
          this.detailItems = normaliseListResponse(items);
          this.detailPage = 1;
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Failed to load project detail");
        } finally {
          this.detailLoading = false;
        }
      },
      filteredProjects() {
        const filtered = this.projects.filter((project) => {
          if (this.statusFilter === "all") {
            return true;
          }
          return projectState(project) === this.statusFilter;
        });
        return sortProjects(filtered, this.sortBy);
      },
      openProject(project) {
        Alpine.store("nav").navigate("projects", project.id);
      },
      closeProjectDetail() {
        Alpine.store("nav").navigate("projects", null);
      },
      projectStatusClass(project) {
        const state = projectState(project);
        return state === "stale"
          ? "badge badge--warning"
          : state === "active"
            ? "badge badge--success"
            : "badge badge--info";
      },
      projectStatusLabel(project) {
        return projectState(project);
      },
      pagedDetailItems() {
        const start = (this.detailPage - 1) * this.detailPageSize;
        return this.detailItems.slice(start, start + this.detailPageSize);
      },
      detailPageCount() {
        return Math.max(1, Math.ceil(this.detailItems.length / this.detailPageSize));
      },
      nextDetailPage() {
        this.detailPage = Math.min(this.detailPage + 1, this.detailPageCount());
      },
      prevDetailPage() {
        this.detailPage = Math.max(1, this.detailPage - 1);
      },
      openMemorySearch() {
        Alpine.store("nav").navigate("memory");
      },
      openOperations() {
        Alpine.store("nav").navigate("operations");
      },
      openGraph() {
        window.location.href = "/ui/graph.html";
      },
      relativeTime,
      labelClass: ui.labelToBadgeClass,
    }));

    Alpine.data("memoryBrowser", () => ({
      initialised: false,
      query: "",
      label: "",
      projectId: "",
      sinceDays: "",
      sortBy: "created_at",
      sortOrder: "desc",
      projects: [],
      results: [],
      page: 1,
      pageSize: 12,
      totalCount: 0,
      loading: false,
      error: "",
      _debounceHandle: null,
      init() {
        if (this.initialised) {
          return;
        }
        this.initialised = true;
        this.loadProjects();
        this.search();
        ["query", "label", "projectId", "sinceDays", "sortBy", "sortOrder"].forEach((key) => {
          this.$watch(key, () => this.queueSearch());
        });
      },
      async loadProjects() {
        try {
          this.projects = await ui.fetchJson("/projects");
        } catch {
          this.projects = [];
        }
      },
      queueSearch() {
        this.page = 1;
        window.clearTimeout(this._debounceHandle);
        this._debounceHandle = window.setTimeout(() => this.search(), 500);
      },
      async search() {
        this.loading = true;
        this.error = "";
        try {
          let payload;
          if (this.query.trim()) {
            payload = await ui.fetchJson("/memory/search", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                query: this.query.trim(),
                label: this.label || undefined,
                project_id: this.projectId || undefined,
                since_days: this.sinceDays ? Number(this.sinceDays) : undefined,
                limit: 100,
              }),
            });
          } else {
            const params = new URLSearchParams({ limit: "100" });
            if (this.label) {
              params.set("label", this.label);
            }
            if (this.projectId) {
              params.set("project_id", this.projectId);
            }
            payload = await ui.fetchJson(`/memory?${params.toString()}`);
          }
          const list = normaliseListResponse(payload)
            .filter((item) => {
              if (!this.sinceDays) {
                return true;
              }
              const createdAt = new Date(item.created_at);
              if (Number.isNaN(createdAt.getTime())) {
                return true;
              }
              const threshold = Date.now() - Number(this.sinceDays) * 86400000;
              return createdAt.getTime() >= threshold;
            })
            .sort((left, right) => {
              const leftValue =
                this.sortBy === "title"
                  ? String(left.title || left.entity_name || left.id)
                  : String(left.created_at || "");
              const rightValue =
                this.sortBy === "title"
                  ? String(right.title || right.entity_name || right.id)
                  : String(right.created_at || "");
              return this.sortOrder === "asc"
                ? leftValue.localeCompare(rightValue)
                : rightValue.localeCompare(leftValue);
            });
          this.results = list;
          this.totalCount = list.length;
        } catch (error) {
          this.results = [];
          this.totalCount = 0;
          this.error = error.message || "Failed to load memory";
        } finally {
          this.loading = false;
        }
      },
      pageCount() {
        return Math.max(1, Math.ceil(this.totalCount / this.pageSize));
      },
      visibleResults() {
        const start = (this.page - 1) * this.pageSize;
        return this.results.slice(start, start + this.pageSize);
      },
      hasMore() {
        return this.page < this.pageCount();
      },
      nextPage() {
        this.page = Math.min(this.page + 1, this.pageCount());
      },
      prevPage() {
        this.page = Math.max(1, this.page - 1);
      },
      selectNode(nodeId) {
        Alpine.store("inspector").open(nodeId);
      },
      preview(item) {
        return (item.content || item.summary || item.fact || "").slice(0, 160) || "No preview";
      },
      relativeTime,
      labelClass: ui.labelToBadgeClass,
    }));

    Alpine.data("toolsView", () => ({
      initialised: false,
      loading: false,
      tools: [],
      filter: "",
      selected: null,
      params: {},
      result: null,
      invoking: false,
      awaitingConfirm: false,
      openModules: {},
      init() {
        if (this.initialised) {
          return;
        }
        this.initialised = true;
        this.loadTools();
      },
      async loadTools() {
        this.loading = true;
        try {
          this.tools = await ui.fetchJson("/tools");
          for (const tool of this.tools) {
            if (!(tool.module in this.openModules)) {
              this.openModules[tool.module] = true;
            }
          }
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Failed to load tools");
        } finally {
          this.loading = false;
        }
      },
      groupedTools() {
        const query = this.filter.trim().toLowerCase();
        const filtered = this.tools.filter((tool) => {
          if (!query) {
            return true;
          }
          return (
            tool.name.toLowerCase().includes(query) ||
            tool.module.toLowerCase().includes(query) ||
            tool.description.toLowerCase().includes(query)
          );
        });
        const groups = {};
        for (const tool of filtered) {
          groups[tool.module] ||= [];
          groups[tool.module].push(tool);
        }
        return Object.entries(groups).sort(([left], [right]) => left.localeCompare(right));
      },
      select(tool) {
        this.selected = tool;
        this.params = {};
        this.result = null;
        this.awaitingConfirm = false;
      },
      schemaProperties() {
        return getSchemaProperties(this.selected);
      },
      toggleModule(name) {
        this.openModules[name] = !this.openModules[name];
      },
      async invoke(confirm = false) {
        if (!this.selected?.http_invocable) {
          return;
        }
        this.invoking = true;
        try {
          const startedAt = performance.now();
          const response = await ui.fetchJson(`/tools/${this.selected.name}/invoke`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              params: this.coerceParams(),
              confirm,
            }),
          });
          this.result = response;
          this.awaitingConfirm = response.status === "preview";
          if (!this.awaitingConfirm) {
            this.recordHistory({
              timestamp: new Date().toISOString(),
              duration_ms: Math.round(performance.now() - startedAt),
              status: response.status || "ok",
            });
          }
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Tool invocation failed");
        } finally {
          this.invoking = false;
        }
      },
      coerceParams() {
        const schema = this.selected?.input_schema?.properties || {};
        const payload = {};
        for (const [key, rawValue] of Object.entries(this.params)) {
          const type = schema[key]?.type;
          if (rawValue === "") {
            continue;
          }
          if (type === "integer" || type === "number") {
            payload[key] = Number(rawValue);
          } else if (type === "boolean") {
            payload[key] = rawValue === true || rawValue === "true";
          } else {
            payload[key] = rawValue;
          }
        }
        return payload;
      },
      recordHistory(entry) {
        const history = getToolHistory();
        history[this.selected.name] = [entry, ...(history[this.selected.name] || [])].slice(0, 5);
        saveToolHistory(history);
      },
      invocationHistory() {
        if (!this.selected) {
          return [];
        }
        const history = getToolHistory();
        return history[this.selected.name] || [];
      },
      statusClass(tool) {
        return tool.http_invocable ? "badge badge--success" : "badge badge--warning";
      },
      statusLabel(tool) {
        return tool.http_invocable ? "http" : "stdio";
      },
    }));

    Alpine.data("operationsView", () => ({
      initialised: false,
      stats: null,
      status: null,
      workspaceId: "",
      workspaceReport: null,
      loadingWorkspace: false,
      runProjectId: "",
      runScope: "global",
      checkPendingOnly: false,
      running: false,
      report: null,
      repairResult: null,
      init() {
        if (this.initialised) {
          return;
        }
        this.initialised = true;
        this.load();
      },
      async load() {
        try {
          const [stats, status] = await Promise.all([
            ui.fetchJson("/graph/stats"),
            ui.fetchJson("/hygiene/status"),
          ]);
          this.stats = stats;
          this.status = status;
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Failed to load operations");
        }
      },
      async loadWorkspaceHealth() {
        if (!this.workspaceId.trim()) {
          Alpine.store("toast").add("warning", "Workspace ID is required");
          return;
        }
        this.loadingWorkspace = true;
        this.repairResult = null;
        try {
          this.workspaceReport = await ui.fetchJson(
            `/graph/stats/workspace/${encodeURIComponent(this.workspaceId.trim())}`
          );
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Workspace health failed");
        } finally {
          this.loadingWorkspace = false;
        }
      },
      async repairOrphans() {
        if (!this.workspaceId.trim()) {
          Alpine.store("toast").add("warning", "Load a workspace before repairing");
          return;
        }
        try {
          this.repairResult = await ui.fetchJson(
            `/graph/repair/orphaned-entities/${encodeURIComponent(this.workspaceId.trim())}`,
            { method: "POST" }
          );
          Alpine.store("toast").add("success", this.repairResult.message || "Repair completed");
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Repair failed");
        }
      },
      async runHygiene() {
        this.running = true;
        try {
          this.report = await ui.fetchJson("/hygiene/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              project_id: this.runProjectId || null,
              scope: this.runScope,
              check_pending_only: this.checkPendingOnly,
            }),
          });
          Alpine.store("toast").add("success", "Hygiene run completed");
          this.status = await ui.fetchJson("/hygiene/status");
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Hygiene run failed");
        } finally {
          this.running = false;
        }
      },
    }));
  });
})();
