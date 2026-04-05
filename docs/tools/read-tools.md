# Read Tools

Tools for retrieving and searching memories.

## get_memory

Retrieve a single memory by ID, with its linked entities and outgoing edges.

**Parameters**:

| Name | Type | Default | Description |
|---|---|---|---|
| `project` | str | — | Project slug |
| `memory_id` | str | — | Memory UUID |
| `include_deleted` | bool | `false` | Include soft-deleted memories |

**Returns**: Full memory dict with `entities` and `edges` fields, or `null` if not found.

## list_memories

List memories in a project, newest first.

**Parameters**:

| Name | Type | Default | Description |
|---|---|---|---|
| `project` | str | — | Project slug |
| `type` | str | `null` | Filter by memory type |
| `limit` | int | `20` | Max results (capped at 100) |
| `offset` | int | `0` | Pagination offset |
| `include_deleted` | bool | `false` | Include soft-deleted |

**Returns**: `[{id, title, type, updated_at, tags, is_expired}]`

## search_memories

Full-text search using FTS5 BM25 ranking. Returns ranked results with a content snippet.

**Parameters**:

| Name | Type | Default | Description |
|---|---|---|---|
| `query` | str | — | Search terms. Supports FTS5 syntax: `"exact phrase"`, `term*`, `term1 OR term2` |
| `project` | str | `null` | Restrict to one project (omit for cross-project search) |
| `type` | str | `null` | Restrict to one memory type |
| `limit` | int | `10` | Max results (capped at 50) |

**Returns**: `[{id, title, type, project, score, snippet, updated_at}]`

Soft-deleted memories are always excluded from search results.

## delete_memory

Soft-delete a memory. Sets `is_deleted=1` — the memory remains readable via `get_memory(include_deleted=True)`.

**Parameters**:

| Name | Type | Description |
|---|---|---|
| `project` | str | Project slug |
| `memory_id` | str | Memory UUID |

**Returns**: `{memory_id, deleted, permanent: false}`

This is **not permanent**. To permanently remove memories, use `purge_expired_memories` after flagging with `flag_expired_memory`.
