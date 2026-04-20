(function () {
  const ui = window.DevtoolsUI;
  const EDITABLE_FIELDS = [
    { key: "title", label: "Title", multiline: false },
    { key: "content", label: "Content", multiline: true },
    { key: "summary", label: "Summary", multiline: true },
    { key: "fact", label: "Fact", multiline: true },
  ];
  const EDITABLE_FIELD_KEYS = new Set(EDITABLE_FIELDS.map((field) => field.key));

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
        return Object.entries(data).filter(
          ([key]) => !key.startsWith("_") && !EDITABLE_FIELD_KEYS.has(key)
        );
      },
      editableFields() {
        return EDITABLE_FIELDS;
      },
      fieldValue(key) {
        return Alpine.store("inspector").nodeData?.[key];
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
        Alpine.store("toast").add("success", "JSON copied");
      },
      downloadJson() {
        const inspector = Alpine.store("inspector");
        if (!inspector.nodeId || !inspector.nodeData) {
          return;
        }
        const payload = JSON.stringify(
          {
            node: inspector.nodeData,
            relationships: inspector.relationships,
          },
          null,
          2
        );
        const blob = new Blob([payload], { type: "application/json" });
        const objectUrl = window.URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = `${inspector.nodeId}.json`;
        anchor.click();
        window.URL.revokeObjectURL(objectUrl);
        Alpine.store("toast").add("success", "JSON downloaded");
      },
      viewInGraph() {
        const inspector = Alpine.store("inspector");
        const data = inspector.nodeData || {};
        const projectAnchor = inspector.relationships?.outgoing?.find(
          (relation) => relation.type === "BELONGS_TO"
        )?.to_id;
        const subView = ui.buildGraphSubView({
          focus: inspector.nodeId,
          workspace: data.workspace_id || projectAnchor,
        });
        inspector.close({ syncHash: false });
        Alpine.store("nav").navigate("graph", subView);
      },
    }));
  });
})();
