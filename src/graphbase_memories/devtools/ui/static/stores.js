(function () {
  const THEME_KEY = "graphbase-theme";
  const DEFAULT_VIEW = "projects";
  const VIEW_LABELS = {
    projects: "Projects",
    memory: "Memory",
    tools: "Tools",
    operations: "Operations",
  };
  const ICONS = {
    search:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>',
    folder:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4H10l2 2h6.5A2.5 2.5 0 0 1 21 8.5v9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"></path></svg>',
    database:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="5" rx="7" ry="3"></ellipse><path d="M5 5v14c0 1.66 3.13 3 7 3s7-1.34 7-3V5"></path><path d="M5 12c0 1.66 3.13 3 7 3s7-1.34 7-3"></path></svg>',
    "share-2":
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><path d="m8.6 10.7 6.8-3.9"></path><path d="m8.6 13.3 6.8 3.9"></path></svg>',
    wrench:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14.7 6.3a4 4 0 0 0 3.4 5.8l-8.8 8.8a2 2 0 1 1-2.8-2.8l8.8-8.8a4 4 0 0 0 5.8-3.4l-3 1-2.4-2.4z"></path></svg>',
    activity:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 12h4l2-5 4 10 2-5h4"></path></svg>',
    x:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></svg>',
    "chevron-right":
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m9 18 6-6-6-6"></path></svg>',
    copy:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15V6a2 2 0 0 1 2-2h9"></path></svg>',
    download:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12"></path><path d="m7 10 5 5 5-5"></path><path d="M5 21h14"></path></svg>',
    "external-link":
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 5h5v5"></path><path d="M10 14 19 5"></path><path d="M19 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"></path></svg>',
    refresh:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12a9 9 0 1 1-2.64-6.36"></path><path d="M21 3v6h-6"></path></svg>',
    "check-circle":
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"></circle><path d="m9 12 2 2 4-4"></path></svg>',
    "alert-triangle":
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10.3 3.8 1.8 18.1A2 2 0 0 0 3.5 21h17a2 2 0 0 0 1.7-2.9L13.7 3.8a2 2 0 0 0-3.4 0Z"></path><path d="M12 9v4"></path><path d="M12 17h.01"></path></svg>',
    trash:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"></path><path d="M10 11v6"></path><path d="M14 11v6"></path></svg>',
    edit:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m4 20 4.5-1 9.9-9.9a2.1 2.1 0 0 0-3-3L5.5 16 4 20Z"></path></svg>',
    moon:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"></path></svg>',
    sun:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.9 4.9 1.4 1.4"></path><path d="m17.7 17.7 1.4 1.4"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m4.9 19.1 1.4-1.4"></path><path d="m17.7 6.3 1.4-1.4"></path></svg>',
    menu:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16"></path><path d="M4 12h16"></path><path d="M4 17h16"></path></svg>',
    help:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"></circle><path d="M9.5 9a2.5 2.5 0 1 1 4.2 1.8c-.9.8-1.7 1.3-1.7 2.7"></path><path d="M12 17h.01"></path></svg>',
  };

  let routerInitialised = false;
  let keyboardInitialised = false;
  let heartbeatSource = null;

  function parseHash(rawHash = window.location.hash) {
    const raw = rawHash.replace(/^#/, "").replace(/^\/+|\/+$/g, "");
    if (!raw) {
      return { view: DEFAULT_VIEW, subView: null };
    }
    const parts = raw.split("/");
    const view = Object.hasOwn(VIEW_LABELS, parts[0]) ? parts[0] : DEFAULT_VIEW;
    const subView = parts.length > 1 ? decodeURIComponent(parts.slice(1).join("/")) : null;
    return { view, subView };
  }

  function buildHash(view, subView) {
    if (!view) {
      return `#${DEFAULT_VIEW}`;
    }
    if (!subView) {
      return `#${view}`;
    }
    return `#${view}/${encodeURIComponent(subView)}`;
  }

  function setHash(view, subView, replace = false) {
    const hash = buildHash(view, subView);
    if (replace) {
      window.history.replaceState(null, "", hash);
    } else if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
  }

  function getTheme() {
    return document.documentElement.dataset.theme || "dark";
  }

  function applyTheme(theme) {
    const next = theme === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem(THEME_KEY, next);
    return next;
  }

  function toggleTheme() {
    const next = getTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    return next;
  }

  function icon(name) {
    return ICONS[name] || "";
  }

  function labelToBadgeClass(label) {
    return {
      Session: "badge badge--session",
      Decision: "badge badge--decision",
      Pattern: "badge badge--pattern",
      Context: "badge badge--context",
      EntityFact: "badge badge--entityfact",
      Project: "badge badge--project",
      Workspace: "badge badge--workspace",
    }[label] || "badge badge--info";
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      const message = typeof payload === "string" ? payload : payload?.message || payload?.detail;
      throw new Error(message || `Request failed: ${response.status}`);
    }
    return payload;
  }

  function emitHelpToggle() {
    document.dispatchEvent(new CustomEvent("devtools:toggle-help"));
  }

  function shouldIgnoreShortcut(target) {
    if (!target) {
      return false;
    }
    const tag = target.tagName?.toLowerCase();
    return (
      target.isContentEditable ||
      tag === "input" ||
      tag === "textarea" ||
      tag === "select"
    );
  }

  function focusMemorySearch() {
    window.setTimeout(() => {
      document.querySelector('input[name="memory-query"]')?.focus();
    }, 30);
  }

  function initKeyboardShortcuts() {
    if (keyboardInitialised) {
      return;
    }
    keyboardInitialised = true;
    document.addEventListener("keydown", (event) => {
      if (shouldIgnoreShortcut(event.target)) {
        return;
      }
      const nav = window.Alpine?.store("nav");
      const inspector = window.Alpine?.store("inspector");
      if (!nav || !inspector) {
        return;
      }
      if (event.key >= "1" && event.key <= "5") {
        event.preventDefault();
        const view = ["projects", "memory", "graph", "tools", "operations"][Number(event.key) - 1];
        if (view === "graph") {
          window.location.href = "/ui/graph.html";
          return;
        }
        nav.navigate(view);
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        nav.navigate("memory");
        focusMemorySearch();
        return;
      }
      if (event.key === "/") {
        event.preventDefault();
        nav.navigate("memory");
        focusMemorySearch();
        return;
      }
      if (nav.view === "memory" && ["j", "k", "Enter"].includes(event.key)) {
        event.preventDefault();
        document.dispatchEvent(
          new CustomEvent("devtools:memory-nav", {
            detail: {
              action:
                event.key === "j" ? "next" : event.key === "k" ? "prev" : "open",
            },
          })
        );
        return;
      }
      if (event.key === "Escape") {
        if (inspector.isOpen) {
          inspector.close();
          event.preventDefault();
        }
        return;
      }
      if (event.key === "?") {
        event.preventDefault();
        emitHelpToggle();
      }
    });
  }

  function initRouter() {
    if (routerInitialised) {
      return;
    }
    routerInitialised = true;
    const applyRoute = async () => {
      const nav = window.Alpine?.store("nav");
      const inspector = window.Alpine?.store("inspector");
      if (!nav || !inspector) {
        return;
      }
      const route = parseHash();
      nav.view = route.view;
      nav.subView = route.subView;
      if (route.view === "memory" && route.subView) {
        await inspector.open(route.subView, { pushHistory: false, syncHash: false });
      } else if (route.view === "memory" && !route.subView && inspector.isOpen) {
        inspector.close({ syncHash: false });
      }
    };
    window.addEventListener("hashchange", applyRoute);
    applyRoute();
  }

  function statusMeta(status) {
    return {
      ok: { label: "Connected", badge: "badge badge--success" },
      degraded: { label: "Degraded", badge: "badge badge--warning" },
      disconnected: { label: "Disconnected", badge: "badge badge--danger" },
      connecting: { label: "Connecting", badge: "badge badge--info" },
    }[status] || { label: status || "Unknown", badge: "badge badge--info" };
  }

  const savedTheme = window.localStorage.getItem(THEME_KEY);
  if (savedTheme) {
    applyTheme(savedTheme);
  }

  window.toggleTheme = toggleTheme;
  window.DevtoolsUI = {
    ICONS,
    icon,
    fetchJson,
    buildHash,
    parseHash,
    setHash,
    applyTheme,
    toggleTheme,
    getTheme,
    statusMeta,
    labelToBadgeClass,
    viewLabel(view) {
      return VIEW_LABELS[view] || view;
    },
  };

  document.addEventListener("alpine:init", () => {
    Alpine.store("nav", {
      view: DEFAULT_VIEW,
      subView: null,
      sidebarCollapsed: window.innerWidth < 820,
      selectedIndex: -1,
      navigate(view, subView = null, options = {}) {
        if (view === "graph") {
          window.location.href = "/ui/graph.html";
          return;
        }
        this.view = view || DEFAULT_VIEW;
        this.subView = subView;
        if (this.view !== "memory") {
          this.selectedIndex = -1;
        }
        if (!options.skipHash) {
          setHash(this.view, this.subView, options.replaceHash);
        }
      },
      toggleSidebar() {
        this.sidebarCollapsed = !this.sidebarCollapsed;
      },
      setSelectedIndex(index) {
        this.selectedIndex = index;
      },
      contextLabel() {
        if (!this.subView) {
          return window.DevtoolsUI.viewLabel(this.view);
        }
        return `${window.DevtoolsUI.viewLabel(this.view)} > ${this.subView}`;
      },
    });

    Alpine.store("neo4j", {
      status: "connecting",
      toolCount: 0,
      lastHeartbeat: null,
      uri: "bolt://localhost:7687",
      init() {
        if (heartbeatSource) {
          return;
        }
        heartbeatSource = new EventSource("/events");
        heartbeatSource.addEventListener("heartbeat", (event) => {
          const payload = JSON.parse(event.data);
          this.status = payload.neo4j_connected ? "ok" : "degraded";
          this.toolCount = payload.tool_count || 0;
          this.lastHeartbeat = new Date().toISOString();
        });
        heartbeatSource.onerror = () => {
          this.status = "disconnected";
        };
      },
      statusLabel() {
        return statusMeta(this.status).label;
      },
      badgeClass() {
        return statusMeta(this.status).badge;
      },
    });

    Alpine.store("inspector", {
      isOpen: false,
      nodeId: null,
      nodeData: null,
      relationships: { incoming: [], outgoing: [] },
      loading: false,
      history: [],
      async open(nodeId, options = {}) {
        if (!nodeId) {
          return;
        }
        const { pushHistory = true, syncHash = true } = options;
        if (this.nodeId && this.nodeId !== nodeId && pushHistory) {
          this.history.push(this.nodeId);
        }
        this.isOpen = true;
        this.loading = true;
        this.nodeId = nodeId;
        try {
          const payload = await fetchJson(`/memory/${encodeURIComponent(nodeId)}/relationships`);
          this.nodeData = payload.node;
          this.relationships = {
            incoming: payload.incoming || [],
            outgoing: payload.outgoing || [],
          };
          if (syncHash && Alpine.store("nav").view === "memory") {
            Alpine.store("nav").subView = nodeId;
            setHash("memory", nodeId, true);
          }
        } catch (error) {
          Alpine.store("toast").add("danger", error.message || "Failed to load inspector");
        } finally {
          this.loading = false;
        }
      },
      close(options = {}) {
        const { syncHash = true } = options;
        this.isOpen = false;
        this.loading = false;
        this.nodeId = null;
        this.nodeData = null;
        this.relationships = { incoming: [], outgoing: [] };
        if (syncHash && Alpine.store("nav").view === "memory") {
          Alpine.store("nav").subView = null;
          setHash("memory", null, true);
        }
      },
      back() {
        const previous = this.history.pop();
        if (previous) {
          return this.open(previous, { pushHistory: false });
        }
      },
    });

    Alpine.store("toast", {
      items: [],
      _counter: 0,
      add(type, message, duration = 3200) {
        const id = ++this._counter;
        const item = { id, type, message };
        this.items = [...this.items, item];
        if (duration > 0) {
          window.setTimeout(() => this.remove(id), duration);
        }
        return id;
      },
      remove(id) {
        this.items = this.items.filter((item) => item.id !== id);
      },
    });

    initRouter();
    initKeyboardShortcuts();
  });
})();
