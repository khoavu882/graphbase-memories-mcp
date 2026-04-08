# Hygiene Tools

Two tools for memory maintenance and health monitoring.

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

## CLI hygiene

Run hygiene from the command line without an agent:

```bash
# Scan a specific project
graphbase-memories-mcp hygiene --project-id my-project

# Scan global scope
graphbase-memories-mcp hygiene --scope global

# Scan everything
graphbase-memories-mcp hygiene
```

Output is printed as JSON to stdout.
