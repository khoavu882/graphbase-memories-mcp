(function () {
  const ui = window.DevtoolsUI;

  function serialiseValue(value) {
    if (value === null || value === undefined) {
      return "—";
    }
    if (typeof value === "object") {
      return JSON.stringify(value, null, 2);
    }
    return String(value);
  }

  document.addEventListener("alpine:init", () => {
    Alpine.data("inspectorDrawer", () => ({
      expanded: {},
      init() {
        this.$watch("$store.inspector.nodeId", () => {
          this.expanded = {};
        });
      },
      labelClass(label) {
        return ui.labelToBadgeClass(label);
      },
      propertyEntries() {
        const data = Alpine.store("inspector").nodeData || {};
        return Object.entries(data).filter(([key]) => !key.startsWith("_"));
      },
      relationItems(direction) {
        const rels = Alpine.store("inspector").relationships || { incoming: [], outgoing: [] };
        return direction === "incoming" ? rels.incoming || [] : rels.outgoing || [];
      },
      isLongValue(value) {
        return serialiseValue(value).length > 160;
      },
      visibleValue(key, value) {
        const text = serialiseValue(value);
        if (this.expanded[key] || text.length <= 160) {
          return text;
        }
        return `${text.slice(0, 160)}…`;
      },
      toggleValue(key) {
        this.expanded[key] = !this.expanded[key];
      },
      async copyId() {
        const nodeId = Alpine.store("inspector").nodeId;
        if (!nodeId) {
          return;
        }
        await navigator.clipboard.writeText(nodeId);
        Alpine.store("toast").add("success", "Node ID copied");
      },
      async copyJson() {
        const inspector = Alpine.store("inspector");
        const payload = JSON.stringify(
          {
            node: inspector.nodeData,
            relationships: inspector.relationships,
          },
          null,
          2
        );
        await navigator.clipboard.writeText(payload);
        Alpine.store("toast").add("success", "Node JSON copied");
      },
      viewInGraph() {
        const data = Alpine.store("inspector").nodeData || {};
        const params = new URLSearchParams();
        if (data.workspace_id) {
          params.set("workspace_id", data.workspace_id);
        }
        window.location.href = params.toString()
          ? `/ui/graph.html?${params.toString()}`
          : "/ui/graph.html";
      },
    }));
  });
})();
