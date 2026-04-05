# Write Tools

Tools for creating and revising memories.

## store_memory

Store a new memory node. The graph is append-only — use `relate_memories(SUPERSEDES)` to revise an existing memory.

**Parameters**:

| Name | Type | Required | Description |
|---|---|---|---|
| `project` | str | yes | Project slug |
| `type` | str | yes | `session` \| `decision` \| `pattern` \| `context` \| `entity_fact` |
| `title` | str | yes | Short descriptive title |
| `content` | str | yes | Full memory content |
| `tags` | list[str] | no | Searchable tags (default: `[]`) |
| `valid_until` | str | no | ISO-8601 expiry date — sets `is_expired` after this date |

**Returns**: `{id, project, type, title, content, tags, created_at, updated_at, valid_until}`

## store_memory_with_entities

Store a memory and automatically link it to named entities. Use this instead of `store_memory` when the memory relates to specific services, files, or concepts.

**Parameters**: same as `store_memory`, plus:

| Name | Type | Required | Description |
|---|---|---|---|
| `entity_names` | list[str] | yes | Entity names to link (upserted by name) |
| `entity_type` | str | no | Type for auto-created entities (default: `concept`) |

**Returns**: same as `store_memory`

## relate_memories

Create a directed edge between two memories. Idempotent — calling twice with the same arguments returns the existing edge.

**Parameters**:

| Name | Type | Required | Description |
|---|---|---|---|
| `project` | str | yes | Project slug |
| `from_id` | str | yes | Source memory UUID |
| `to_id` | str | yes | Target memory UUID |
| `relationship` | str | yes | `SUPERSEDES` \| `RELATES_TO` \| `LEARNED_DURING` |

**Constraints**:
- `LEARNED_DURING`: `from_id` must be `decision` or `pattern`; `to_id` must be `session`
- Self-loops (`from_id == to_id`) are rejected
