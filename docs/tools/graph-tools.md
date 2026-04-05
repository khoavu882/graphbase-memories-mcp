# Graph Tools

Tools for graph analysis and visualization.

## graph_view

Return a graph snapshot suitable for D3.js rendering or structural analysis.

**Parameters**:

| Name | Type | Default | Description |
|---|---|---|---|
| `project` | str | — | Project slug |
| `limit` | int | `200` | Max memories to include (newest first) |
| `entity_filter` | str | `null` | If set, return only memories referencing this entity |

**Returns**:
```json
{
  "project": "my-project",
  "total_memories": 42,
  "generated_at": "2026-04-06T00:00:00",
  "nodes": [
    {"id": "...", "label": "...", "node_type": "memory", "type": "decision", "tags": [], "project": "...", "updated_at": "...", "is_expired": false},
    {"id": "...", "label": "auth-service", "node_type": "entity", "type": "service", "project": "..."}
  ],
  "links": [
    {"source": "memory-uuid", "target": "entity-uuid", "type": "REFERENCES"},
    {"source": "entity-a", "target": "entity-b", "type": "DEPENDS_ON"}
  ]
}
```

Memory nodes and entity nodes share the `nodes` array, distinguished by `node_type`.

`total_memories` reflects the project's full non-deleted count — `nodes` filtered to `memory` may be fewer if `limit` was applied.

## get_blast_radius

Analyse the impact radius of a named entity by traversing the memory graph.

**Parameters**:

| Name | Type | Default | Description |
|---|---|---|---|
| `entity_name` | str | — | Entity name to analyse |
| `project` | str | — | Project slug |
| `depth` | int | `2` | Hop depth for traversal |

**Returns**:
```json
{
  "entity_name": "auth-service",
  "project": "my-project",
  "depth": 2,
  "memories": [...],
  "related_entities": [...],
  "total_references": 12
}
```

Use before refactoring a shared service or database table to understand which memories and entities would be affected.
