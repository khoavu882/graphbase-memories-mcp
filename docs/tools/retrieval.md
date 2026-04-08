# Retrieval Tools

Two tools for loading memory before an agent begins reasoning.

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
