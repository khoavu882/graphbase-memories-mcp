# Artifact Tools

Three tools for saving structured knowledge artifacts: decisions, patterns, and free-form context.

---

## `save_decision`

Save an architectural or technical decision with automatic deduplication and supersession.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `decision` | `DecisionSchema` | Yes | Decision data |
| `project_id` | `string` | Yes | Project identifier |
| `focus` | `string \| null` | No | Focus area within the project |
| `governance_token` | `string \| null` | Conditional | Required when `scope="global"` |

### `DecisionSchema`

```json
{
  "title": "Use SHA-256 + Jaccard for decision dedup",
  "rationale": "BM25 score thresholds were fragile; hash gives exact-match certainty and Jaccard similarity gives semantic supersession for near-duplicates.",
  "owner": "Kai Vu",
  "date": "2026-04-08",
  "scope": "project",
  "supersedes": null,
  "confidence": 0.95
}
```

| Field | Type | Description |
|---|---|---|
| `title` | `string` | Short decision title (used for dedup full-text index) |
| `rationale` | `string` | Why this decision was made |
| `owner` | `string` | Who made or owns the decision |
| `date` | `date` | When the decision was made |
| `scope` | `"global" \| "project" \| "focus"` | Memory scope |
| `supersedes` | `string \| null` | ID of an older decision this replaces |
| `confidence` | `float [0.0–1.0]` | Confidence level |

### Deduplication behavior

Before writing, the engine runs a two-step dedup check:

1. **Exact hash** — SHA-256 of `normalize(title + rationale)` — if matched: `duplicate_skip`
2. **Full-text + Jaccard** on top-5 candidates:
    - Jaccard ≥ 0.70 → `supersede` (new node created, `[:SUPERSEDES]` edge added to old)
    - Jaccard 0.50–0.69 → `manual_review` (write blocked, candidate ID returned)
    - Jaccard < 0.50 → `new` (write proceeds normally)

### Returns: `SaveResult`

```json
{
  "status": "saved",
  "artifact_id": "uuid",
  "dedup_outcome": "new",
  "message": null
}
```

!!! warning "Global scope requires approval"
    Saving a decision with `scope="global"` requires a `governance_token` obtained from
    `request_global_write_approval`. See [Governance](governance.md).

---

## `save_pattern`

Save a repeatable workflow pattern. Uses hash-only dedup (exact match) — patterns are structured
enough that Jaccard similarity is not needed.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `pattern` | `PatternSchema` | Yes | Pattern data |
| `project_id` | `string` | Yes | Project identifier |
| `focus` | `string \| null` | No | Focus area |

### `PatternSchema`

```json
{
  "trigger": "When starting a new session on a known project",
  "repeatable_steps": [
    "Call get_scope_state(project_id)",
    "Call retrieve_context(project_id, scope='project')",
    "Review decisions and patterns before reasoning"
  ],
  "exclusions": [
    "Skip if Neo4j is unavailable — continue in local mode"
  ],
  "scope": "global",
  "last_validated_at": "2026-04-08T10:00:00Z"
}
```

### Returns: `SaveResult`

Same shape as `save_decision`. `dedup_outcome` is `duplicate_skip` or `new` (no `supersede` for patterns).

---

## `save_context`

Save a free-form context snippet with a relevance score. Useful for capturing reference material,
background context, or notes that do not fit the structured decision or pattern formats.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `context` | `ContextSchema` | Yes | Context data |
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

| Field | Description |
|---|---|
| `content` | The context text (searchable via full-text index) |
| `topic` | Short tag used for filtering |
| `scope` | Memory scope |
| `relevance_score` | Float 0.0–1.0; higher = more likely to be surfaced in retrieval |

### Returns: `SaveResult`

Same shape as other artifact tools. No dedup is applied to context snippets.
