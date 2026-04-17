# Hygiene Tools

Three tools for memory maintenance and health monitoring.

---

## `run_hygiene`

Run a full memory hygiene scan on a project or the global scope. Detects duplicates, stale decisions,
obsolete patterns, entity drift, and unresolved saves.

!!! important "Read-only — never auto-mutates"
    `run_hygiene` **only reports** problems. It never deletes, merges, or supersedes nodes automatically.
    All mutations require explicit confirmation from the caller.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `project_id` | `string \| null` | No | Specific project to scan; `null` scans all projects + global |
| `scope` | `"global" \| "project" \| "focus" \| null` | No | Scope filter |

### Returns: `HygieneReport`

```json
{
  "project_id": "my-project",
  "scope": "project",
  "duplicates_found": 2,
  "outdated_decisions": 1,
  "obsolete_patterns": 0,
  "entity_drift_count": 3,
  "unresolved_saves": 0,
  "candidate_ids": {
    "duplicates": ["uuid-a", "uuid-b"],
    "outdated_decisions": ["uuid-c"],
    "entity_drift": ["uuid-d", "uuid-e", "uuid-f"]
  },
  "checked_at": "2026-04-08T10:00:00Z"
}
```

### What hygiene checks

| Check | Condition | Action needed |
|---|---|---|
| **Duplicate detection** | Full-text similarity > 0.9 between two nodes | Review and manually supersede or delete one |
| **Outdated decisions** | Decision `date` older than 180 days with no outgoing `[:SUPERSEDES]` | Review and either supersede or confirm still valid |
| **Obsolete patterns** | Pattern `last_validated_at` older than 90 days | Re-validate or delete |
| **Entity drift** | Multiple `EntityFact` nodes with same `entity_name` | Merge into canonical node |
| **Unresolved saves** | Nodes with `status IN [pending_retry, failed]` | Retry or delete failed artifacts |

### 30-day hygiene cycle

The server tracks `last_hygiene_at` on each Project and GlobalScope node. If it has been more than 30 days since the last hygiene run, `retrieve_context` returns `hygiene_due: true` in the `ContextBundle` to prompt the agent to run hygiene.

---

## `get_save_status`

List pending or failed saves for a project. Useful for diagnosing write failures without running a full hygiene scan.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `project_id` | `string` | Yes | Project identifier |
| `session_id` | `string \| null` | No | Filter to a specific session |

### Returns: `SaveStatusSummary`

```json
{
  "status": "pending_retry",
  "count": 2,
  "oldest_pending_at": "2026-04-07T08:30:00Z",
  "artifact_ids": ["uuid-x", "uuid-y"]
}
```

| `status` | Meaning |
|---|---|
| `saved` | All saves for this project succeeded |
| `pending_retry` | Some saves are queued for retry |
| `failed` | Some saves failed permanently |
| `partial` | Mix of saved and failed |

---

## `memory_freshness`

Preview nodes approaching or past the staleness threshold, ranked oldest-first. Use this before
`run_hygiene` to understand which nodes are at risk of being flagged, without triggering a full
hygiene scan.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `project_id` | `string \| null` | No | Project to scan; `null` scans all projects |
| `scope` | `"global" \| "project" \| "focus"` | No | Scope filter (default: `project`) |
| `stale_after_days` | `integer \| null` | No | Override the staleness threshold (default: `GRAPHBASE_FRESHNESS_STALE_DAYS`, i.e. 30) |
| `limit` | `integer` | No | Max nodes to return (default: `50`, max: `200`) |

### Returns: `FreshnessReport`

```json
{
  "stale_count": 2,
  "recent_count": 5,
  "current_count": 18,
  "stale_items": [
    {
      "node_id": "uuid-a",
      "label": "Decision",
      "title": "Use SHA-256 for dedup",
      "age_days": 45,
      "freshness": "stale",
      "project_id": "my-project"
    }
  ],
  "checked_at": "2026-04-17T10:00:00Z",
  "next_step": "Run run_hygiene() to get full candidate_ids for mutation."
}
```

| `freshness` | Meaning |
|---|---|
| `current` | Updated within the threshold (≤ `stale_after_days` days ago) |
| `recent` | Between threshold and 2× threshold |
| `stale` | Older than 2× threshold — likely to be flagged by hygiene |

### Recommended workflow

```python
# 1. Preview which nodes are at risk
memory_freshness(project_id="my-project", stale_after_days=30)

# 2. If stale_count > 0, run a full hygiene scan for actionable candidate IDs
run_hygiene(project_id="my-project")
```

---

## CLI hygiene

Run hygiene from the command line without an agent:

```bash
# Scan a specific project
graphbase hygiene --project-id my-project

# Scan global scope
graphbase hygiene --scope global

# Scan everything
graphbase hygiene
```

Output is printed as JSON to stdout.
