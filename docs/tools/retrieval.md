# Retrieval Tools

Three tools for loading memory before an agent begins reasoning.

---

## `retrieve_context`

Load memory with priority merge: **focus > project > global**.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `project_id` | `string` | Yes | Project identifier |
| `scope` | `"global" \| "project" \| "focus"` | Yes | Minimum scope to query |
| `focus` | `string \| null` | No | Focus area name within the project |
| `categories` | `list[string] \| null` | No | Filter by node labels (e.g. `["Decision", "Pattern"]`) |
| `topic` | `string \| null` | No | Keyword filter applied to content fields |

### Returns: `ContextBundle`

```json
{
  "items": [
    {
      "id": "uuid",
      "label": "Decision",
      "title": "Use SHA-256 for dedup",
      "rationale": "...",
      "scope": "project",
      "created_at": "2026-04-08T10:00:00Z"
    }
  ],
  "retrieval_status": "succeeded",
  "scope_state": "resolved",
  "conflicts_found": false,
  "hygiene_due": false
}
```

| Field | Values | Meaning |
|---|---|---|
| `retrieval_status` | `succeeded` | Results returned |
| | `empty` | No matching nodes found (not an error) |
| | `timed_out` | Query exceeded 5s timeout; retry was attempted |
| | `failed` | Neo4j error; agent should continue without memory |
| | `conflicted` | Results include nodes connected by `[:CONFLICTS_WITH]` |
| `hygiene_due` | `true` | Project has not been cleaned up in 30+ days |

### Priority merge

When `focus` is set, the engine queries three scopes in sequence and merges results:

1. `scope=focus` — up to 10 items
2. `scope=project` — up to 10 items
3. `scope=global` — up to 5 items

Superseded decisions (connected by `[:SUPERSEDES]` from a newer node) are excluded automatically.

### Example

```python
retrieve_context(
    project_id="my-project",
    scope="project",
    focus="auth-refactor",
    categories=["Decision", "Pattern"],
    topic="authentication"
)
```

---

## `get_scope_state`

Resolve the scope state for a given `project_id` and optional focus. Call this before any read or write to understand what operations are permitted.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `project_id` | `string \| null` | No | Project identifier |
| `focus` | `string \| null` | No | Focus area name |

### Returns

```json
{
  "scope_state": "resolved",
  "project_exists": true
}
```

| `scope_state` | Meaning | Write permitted? |
|---|---|---|
| `resolved` | Project exists; focus (if given) exists | Yes |
| `uncertain` | Project does not exist in graph yet | No — first `save_session` creates it |
| `unresolved` | No `project_id` provided | No |

!!! tip "When to call this"
    Call `get_scope_state` at the start of every session before loading or saving memory.
    It is cheap (one graph lookup) and prevents wasted write attempts with `blocked_scope` results.

---

## `memory_surface`

Lightweight BM25 keyword lookup for a specific topic — faster and narrower than `retrieve_context`.
Use this before editing a file, starting a sub-task, or when you have a precise keyword and do not
need a full scope-aware context bundle.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | BM25 search query — keyword or short phrase |
| `project_id` | `string \| null` | No | Restrict search to a specific project; `null` searches across all projects |
| `limit` | `integer` | No | Max results to return (default: `5`) |

### Returns: `SurfaceResult`

```json
{
  "matches": [
    {
      "id": "uuid",
      "label": "Decision",
      "name": "Use SHA-256 for dedup",
      "content": "Deterministic and explainable without embeddings.",
      "scope": "project",
      "freshness": "current",
      "bm25_score": 4.23,
      "project_id": "my-project"
    }
  ],
  "query_used": "dedup hash",
  "total_found": 1,
  "next_step": null
}
```

| Field | Values | Meaning |
|---|---|---|
| `label` | `Decision`, `Pattern`, `Context`, `EntityFact` | Node type matched |
| `freshness` | `current`, `recent`, `stale` | Age relative to the freshness threshold |
| `bm25_score` | float | Relevance score from Neo4j full-text index |

### When to use `memory_surface` vs `retrieve_context`

| Use case | Recommended tool |
|---|---|
| "What do we know about authentication?" | `memory_surface(query="authentication")` |
| Load full context before starting a session | `retrieve_context(scope="project")` |
| Quick topic scan before editing a single file | `memory_surface` |
| Need conflict detection and hygiene signals | `retrieve_context` |

### Example

```python
memory_surface(
    query="dedup jaccard threshold",
    project_id="my-project",
    limit=3
)
```
