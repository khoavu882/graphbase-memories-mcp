(function () {
  const ui = window.DevtoolsUI;

  function relativeTime(value) {
    if (!value) {
      return "Unknown";
    }
    const parsedValue = ui.normaliseApiValue(value);
    const date = new Date(parsedValue);
    if (Number.isNaN(date.getTime())) {
      return String(parsedValue);
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
        Alpine.store("nav").navigate("graph");
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
      selectedIds: [],
      loading: false,
      error: "",
      bulkDeleteModalOpen: false,
      bulkDeleteConfirmValue: "",
      bulkDeleting: false,
      _debounceHandle: null,
      _navHandler: null,
      _updateHandler: null,
      _removeHandler: null,
      init() {
        if (this.initialised) {
          return;
        }
        this.initialised = true;
        this.loadProjects();
        this.search();
        Alpine.store("nav").selectedIndex = -1;
        ["query", "label", "projectId", "sinceDays", "sortBy", "sortOrder"].forEach((key) => {
          this.$watch(key, () => this.queueSearch());
        });
        this._navHandler = (event) => {
          const action = event.detail?.action;
          if (Alpine.store("nav").view !== "memory") {
            return;
          }
          if (action === "next") {
            this.moveSelection(1);
          } else if (action === "prev") {
            this.moveSelection(-1);
          } else if (action === "open") {
            this.openSelected();
          }
        };
        document.addEventListener("devtools:memory-nav", this._navHandler);
        this._updateHandler = (event) => {
          const node = event.detail?.node;
          if (!node?.id) {
            return;
          }
          this.results = this.results.map((item) => (item.id === node.id ? { ...item, ...node } : item));
        };
        this._removeHandler = (event) => {
          const nodeId = event.detail?.nodeId;
          if (!nodeId) {
            return;
          }
          this.results = this.results.filter((item) => item.id !== nodeId);
          this.selectedIds = this.selectedIds.filter((id) => id !== nodeId);
          this.totalCount = Math.max(0, this.totalCount - 1);
          if (!this.results.length) {
            Alpine.store("nav").selectedIndex = -1;
            return;
          }
          Alpine.store("nav").selectedIndex = Math.min(
            Alpine.store("nav").selectedIndex,
            this.results.length - 1
          );
        };
        document.addEventListener("devtools:memory-updated", this._updateHandler);
        document.addEventListener("devtools:memory-removed", this._removeHandler);
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
        this.clearSelection();
        Alpine.store("nav").selectedIndex = -1;
        window.clearTimeout(this._debounceHandle);
        this._debounceHandle = window.setTimeout(() => this.search(), 500);
      },
      async search(allowRepage = true) {
        this.loading = true;
        this.error = "";
        try {
          const offset = (this.page - 1) * this.pageSize;
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
                limit: this.pageSize,
                offset,
                sort_by: this.sortBy,
                sort_order: this.sortOrder,
              }),
            });
          } else {
            const params = new URLSearchParams({
              limit: String(this.pageSize),
              offset: String(offset),
              sort_by: this.sortBy,
              sort_order: this.sortOrder,
            });
            if (this.label) {
              params.set("label", this.label);
            }
            if (this.projectId) {
              params.set("project_id", this.projectId);
            }
            if (this.sinceDays) {
              params.set("since_days", this.sinceDays);
            }
            payload = await ui.fetchJson(`/memory?${params.toString()}`);
          }
          const results = normaliseListResponse(payload);
          const totalCount = payload.total || 0;
          const maxPage = Math.max(1, Math.ceil(totalCount / this.pageSize));
          if (allowRepage && !results.length && totalCount > 0 && this.page > maxPage) {
            this.page = maxPage;
            await this.search(false);
            return;
          }
          this.results = results;
          this.totalCount = totalCount;
          Alpine.store("nav").selectedIndex = this.results.length ? 0 : -1;
        } catch (error) {
          this.results = [];
          this.totalCount = 0;
          Alpine.store("nav").selectedIndex = -1;
          this.error = error.message || "Failed to load memory";
        } finally {
          this.loading = false;
        }
      },
      pageCount() {
        return Math.max(1, Math.ceil(this.totalCount / this.pageSize));
      },
      visibleResults() {
        return this.results;
      },
      hasMore() {
        return this.page < this.pageCount();
      },
      selectedCount() {
        return this.selectedIds.length;
      },
      clearSelection() {
        this.selectedIds = [];
      },
      isChecked(nodeId) {
        return this.selectedIds.includes(nodeId);
      },
      toggleSelection(nodeId) {
        if (this.isChecked(nodeId)) {
          this.selectedIds = this.selectedIds.filter((id) => id !== nodeId);
          return;
        }
        this.selectedIds = [...this.selectedIds, nodeId];
      },
      visibleIds() {
        return this.visibleResults().map((item) => item.id);
      },
      allVisibleSelected() {
        const visibleIds = this.visibleIds();
        return visibleIds.length > 0 && visibleIds.every((id) => this.selectedIds.includes(id));
      },
      toggleVisibleSelection() {
        const visibleIds = this.visibleIds();
        if (!visibleIds.length) {
          return;
        }
        if (this.allVisibleSelected()) {
          this.selectedIds = this.selectedIds.filter((id) => !visibleIds.includes(id));
          return;
        }
        const selected = new Set(this.selectedIds);
        visibleIds.forEach((id) => selected.add(id));
        this.selectedIds = [...selected];
      },
      selectionPreview() {
        const preview = this.selectedIds.slice(0, 5).join("\n");
        return this.selectedIds.length > 5 ? `${preview}\n...` : preview;
      },
      openBulkDeleteModal() {
        if (!this.selectedIds.length) {
          Alpine.store("toast").add("warning", "Select at least one memory node");
          return;
        }
        this.bulkDeleteConfirmValue = "";
        this.bulkDeleteModalOpen = true;
      },
      closeBulkDeleteModal() {
        this.bulkDeleteModalOpen = false;
        this.bulkDeleteConfirmValue = "";
      },
      canBulkDelete() {
        return this.selectedIds.length > 0 && this.bulkDeleteConfirmValue === "DELETE";
      },
      async bulkDeleteSelected() {
        if (!this.canBulkDelete()) {
          Alpine.store("toast").add("warning", "Type DELETE to confirm bulk deletion");
          return;
        }
        this.bulkDeleting = true;
        const selectedIds = [...this.selectedIds];
        try {
          const payload = await ui.fetchJson("/memory/bulk-delete", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...Alpine.store("auth").headers(),
            },
            body: JSON.stringify({ ids: selectedIds, confirm: true }),
          });
          for (const nodeId of payload.deleted || []) {
            document.dispatchEvent(
              new CustomEvent("devtools:memory-removed", {
                detail: { nodeId },
              })
            );
          }
          if ((payload.deleted || []).includes(Alpine.store("inspector").nodeId)) {
            Alpine.store("inspector").close();
          }
          this.selectedIds = this.selectedIds.filter((id) => !(payload.deleted || []).includes(id));
          this.closeBulkDeleteModal();
          await this.search();
          const missingCount = payload.missing?.length || 0;
          const message = missingCount
            ? `Deleted ${payload.deleted_count} nodes (${missingCount} already missing)`
            : `Deleted ${payload.deleted_count} nodes`;
          Alpine.store("toast").add("success", message);
        } catch (error) {
          const message = ui.isInvalidTokenMessage(error.message)
            ? "Invalid token. Paste the startup token from console."
            : error.message || "Failed to delete selected nodes";
          Alpine.store("toast").add("danger", message);
        } finally {
          this.bulkDeleting = false;
        }
      },
      nextPage() {
        this.page = Math.min(this.page + 1, this.pageCount());
        this.search();
      },
      prevPage() {
        this.page = Math.max(1, this.page - 1);
        this.search();
      },
      selectNode(nodeId) {
        Alpine.store("inspector").open(nodeId);
      },
      moveSelection(delta) {
        if (!this.results.length) {
          Alpine.store("nav").selectedIndex = -1;
          return;
        }
        const current = Alpine.store("nav").selectedIndex;
        const next =
          current < 0 ? 0 : Math.max(0, Math.min(current + delta, this.results.length - 1));
        Alpine.store("nav").selectedIndex = next;
      },
      openSelected() {
        const index = Alpine.store("nav").selectedIndex;
        if (index >= 0 && this.results[index]) {
          this.selectNode(this.results[index].id);
        }
      },
      isSelected(localIndex) {
        return Alpine.store("nav").selectedIndex === localIndex;
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
      historyEntries: [],
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
        this.historyEntries = this.readHistory(tool.name);
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
        this.historyEntries = history[this.selected.name];
      },
      readHistory(toolName) {
        const history = getToolHistory();
        return history[toolName] || [];
      },
      invocationHistory() {
        return this.historyEntries;
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
      repairing: false,
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
      async loadWorkspaceHealth(options = {}) {
        if (!this.workspaceId.trim()) {
          Alpine.store("toast").add("warning", "Workspace ID is required");
          return;
        }
        this.loadingWorkspace = true;
        if (!options.preserveRepairResult) {
          this.repairResult = null;
        }
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
      currentWorkspaceId() {
        return (this.workspaceReport?.workspace_id || this.workspaceId || "").trim();
      },
      hasOrphans() {
        return (this.workspaceReport?.orphaned_entity_count || 0) > 0;
      },
      async repairOrphans() {
        const workspaceId = this.currentWorkspaceId();
        if (!workspaceId) {
          Alpine.store("toast").add("warning", "Load a workspace before repairing");
          return;
        }
        if (!this.hasOrphans()) {
          Alpine.store("toast").add("info", "No orphaned entities detected");
          return;
        }
        this.repairing = true;
        this.repairResult = null;
        try {
          this.repairResult = await ui.fetchJson(
            `/graph/repair/orphaned-entities/${encodeURIComponent(workspaceId)}`,
            { method: "POST" }
          );
          await this.loadWorkspaceHealth({ preserveRepairResult: true });
          Alpine.store("toast").add("success", this.repairResult.message || "Repair completed");
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Repair failed");
        } finally {
          this.repairing = false;
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
