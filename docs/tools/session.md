# Session Tools

Two tools for persisting session summaries at the end of a coding or reasoning session.

---

## `save_session`

Persist a single session summary with objective, actions, decisions, and next steps.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `session` | `SessionSchema` | Yes | Session data (see schema below) |
| `project_id` | `string` | Yes | Project identifier |

### `SessionSchema`

```json
{
  "objective": "Implement dedup engine for decisions",
  "actions_taken": [
    "Read ARCHITECTURE.md",
    "Implemented SHA-256 hash check",
    "Added Jaccard similarity fallback"
  ],
  "decisions_made": [
    "Use hash-only dedup for patterns (exact match sufficient)",
    "Jaccard threshold 0.70 for supersede"
  ],
  "open_items": [
    "Add integration test for manual_review path"
  ],
  "next_actions": [
    "Write tests for dedup engine",
    "Review WriteEngine retry logic"
  ],
  "save_scope": "project"
}
```

| Field | Type | Description |
|---|---|---|
| `objective` | `string` | What this session aimed to accomplish |
| `actions_taken` | `list[string]` | What was actually done |
| `decisions_made` | `list[string]` | Key decisions reached (brief — save full decisions with `save_decision`) |
| `open_items` | `list[string]` | Unresolved questions or blockers |
| `next_actions` | `list[string]` | Concrete next steps |
| `save_scope` | `"global" \| "project" \| "focus"` | Where to save this session |

### Returns: `SaveResult`

```json
{
  "status": "saved",
  "artifact_id": "3f2a1b4c-...",
  "dedup_outcome": null,
  "message": null
}
```

---

## `store_session_with_learnings`

Batch save: session summary + related decisions + patterns in one atomic-ish call. Preferred over calling `save_session` + `save_decision` + `save_pattern` separately, as it links them via `[:PRODUCED]` edges automatically.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `session` | `SessionSchema` | Yes | Session data |
| `decisions` | `list[DecisionSchema]` | No | Decisions made this session |
| `patterns` | `list[PatternSchema]` | No | Patterns observed or validated |
| `project_id` | `string` | Yes | Project identifier |

### Returns: `BatchSaveResult`

```json
{
  "session": { "status": "saved", "artifact_id": "..." },
  "decisions": [
    { "status": "saved", "artifact_id": "...", "dedup_outcome": "new" },
    { "status": "saved", "artifact_id": "...", "dedup_outcome": "supersede" }
  ],
  "patterns": [
    { "status": "saved", "artifact_id": "...", "dedup_outcome": "duplicate_skip" }
  ],
  "overall": "saved"
}
```

`overall` is `partial` if any sub-result has status `failed`. The session node is always attempted first; if it fails, decisions and patterns are still attempted.

!!! tip "End-of-session pattern"
    Calling `store_session_with_learnings` at the end of every session is the recommended pattern.
    It creates a complete traceable record: session node → decision nodes → pattern nodes,
    all linked by `[:PRODUCED]` edges.
