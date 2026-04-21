# Artifact Tools

Three tools save structured knowledge artifacts: decisions, patterns, and free-form context.

---

## `save_decision`

Save an architectural or technical decision with automatic deduplication and optional governance approval for global scope.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `decision` | `DecisionSchema` | Yes | Decision payload |
| `project_id` | `string` | Yes | Project identifier |
| `focus` | `string \| null` | No | Focus area within the project |
| `governance_token` | `string \| null` | Conditional | Required when `decision.scope="global"` |

### `DecisionSchema`

```json
{
  "title": "Use SHA-256 + Jaccard for decision dedup",
  "rationale": "Hash gives exact certainty and Jaccard catches near-duplicate supersession cases.",
  "owner": "Kai Vu",
  "date": "2026-04-08",
  "scope": "project",
  "confidence": 0.95
}
```

### Dedup behavior

Decision writes use a two-stage dedup flow:

1. exact SHA-256 hash match
2. candidate search + Jaccard similarity

Possible `dedup_outcome` values:

- `new`
- `duplicate_skip`
- `supersede`
- `manual_review`

### Returns: `SaveResult`

```json
{
  "status": "saved",
  "artifact_id": "uuid",
  "dedup_outcome": "new",
  "message": null,
  "next_step": null
}
```

When the engine detects a near-duplicate that needs human review, it returns `status: "failed"` with `dedup_outcome: "manual_review"` and a guidance message in `message` / `next_step`.

!!! warning "Global scope requires approval"
    Saving a decision with `scope="global"` requires a `governance_token` obtained from
    `request_global_write_approval`.

---

## `save_pattern`

Save a repeatable workflow pattern. Pattern dedup uses exact hash matching only.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pattern` | `PatternSchema` | Yes | Pattern payload |
| `project_id` | `string` | Yes | Project identifier |
| `focus` | `string \| null` | No | Focus area |

### `PatternSchema`

```json
{
  "trigger": "When starting a new session on a known project",
  "repeatable_steps": [
    "Call retrieve_context(project_id, scope='project')",
    "Review recent decisions and patterns before editing"
  ],
  "exclusions": [
    "Skip if Neo4j is unavailable"
  ],
  "scope": "global",
  "last_validated_at": "2026-04-08T10:00:00Z"
}
```

Internally, the graph stores both:

- `repeatable_steps` as a string list
- `repeatable_steps_text` as a joined string for full-text search

### Returns

`save_pattern` returns the same `SaveResult` shape as `save_decision`.

---

## `save_context`

Save a free-form context snippet with a relevance score.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `context` | `ContextSchema` | Yes | Context payload |
| `project_id` | `string` | Yes | Project identifier |
| `focus` | `string \| null` | No | Focus area |

### `ContextSchema`

```json
{
  "content": "The Neo4j fulltext index uses Lucene query syntax. Wrap phrases in quotes for exact phrase search.",
  "topic": "neo4j-fulltext",
  "scope": "global",
  "relevance_score": 0.8
}
```

### Returns

`save_context` returns `SaveResult`. Context writes do not run the decision/pattern dedup flow.
