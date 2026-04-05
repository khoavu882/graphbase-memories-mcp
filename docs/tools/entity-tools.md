# Entity Tools

Tools for managing entities and entity relationships.

## upsert_entity

Create or update an entity by `(name, type, project)` key. Full metadata replacement — not a partial merge.

**Parameters**:

| Name | Type | Required | Description |
|---|---|---|---|
| `project` | str | yes | Project slug |
| `name` | str | yes | Entity name |
| `type` | str | yes | `service` \| `file` \| `feature` \| `concept` \| `table` \| `topic` |
| `metadata` | dict | no | Arbitrary metadata (replaces existing metadata entirely) |

**Returns**: `{id, name, type, project, metadata, created_at, updated_at}`

The `upsert_entity` tool represents current real-world state — it is the intentional exception to the append-only design. Prior metadata values are not preserved.

## get_entity

Direct entity lookup by `(name, type, project)`.

**Parameters**:

| Name | Type | Description |
|---|---|---|
| `project` | str | Project slug |
| `name` | str | Entity name |
| `type` | str | Entity type |

**Returns**: entity dict or `null` if not found.

## link_entities

Create a directed entity→entity edge. Idempotent — duplicate `(from, to, type)` returns the existing edge.

**Parameters**:

| Name | Type | Required | Description |
|---|---|---|---|
| `project` | str | yes | Project slug |
| `from_name` | str | yes | Source entity name |
| `from_type` | str | yes | Source entity type |
| `to_name` | str | yes | Target entity name |
| `to_type` | str | yes | Target entity type |
| `edge_type` | str | yes | `DEPENDS_ON` \| `IMPLEMENTS` |
| `properties` | dict | no | Edge metadata |

Both entities must already exist — `link_entities` does not auto-create. Use `upsert_entity` first.

## unlink_entities

Delete the entity→entity edge matching `(from, to, edge_type)`. Hard-delete — not soft-delete.

**Parameters**: same as `link_entities` minus `properties`.

**Returns**: `{deleted: true}` if found and deleted, `{deleted: false}` if no matching edge.

## upsert_entity_with_deps

Upsert an entity and create its dependency edges in a single atomic call. Prefer this over calling `upsert_entity` + `link_entities` in a loop when you know the dependency list up front.

**Parameters**:

| Name | Type | Required | Description |
|---|---|---|---|
| `project` | str | yes | Project slug |
| `name` | str | yes | Entity name |
| `type` | str | yes | `service` \| `file` \| `feature` \| `concept` \| `table` \| `topic` |
| `metadata` | dict | yes | Entity metadata — full replacement on the focal entity |
| `depends_on` | list[str] | yes | Names of dep entities to link from the focal entity |
| `dep_type` | str | yes | Entity type for all deps (required — no default to prevent phantom entities) |
| `edge_type` | str | no | `DEPENDS_ON` (default) \| `IMPLEMENTS` |

**Returns**: `{entity_id, created_edges: [{from_id, to_id, type}], errors: [{index, message}]}`

**Behaviour**:
- Missing dep entities are auto-created with `{}` metadata.
- If a dep entity already exists, its metadata is **not overwritten** — a `get_entity` guard preserves it.
- `DEPENDS_ON` edges are idempotent — calling twice produces no duplicate edge.
- Validation (`type`, `dep_type`, `edge_type`) runs before any writes; invalid values raise immediately with no partial writes.
- `errors` lists failed deps by index; the focal entity and successful deps are not rolled back.

## get_context

Return a YAML context summary for the project — used by the hook for automatic injection.

**Parameters**:

| Name | Type | Default | Description |
|---|---|---|---|
| `project` | str | — | Project slug |
| `entity` | str | `null` | Focus on memories referencing this entity |
| `max_tokens` | int | `500` | Token budget |

**Returns**: YAML string (token-budgeted, stale memories flagged).
