---
name: graphbase-hygiene
description: Use when memory may contain stale decisions, duplicate records, entity drift, obsolete patterns, or pending/failed saves.
---

# Graphbase Hygiene

Run a full scan:

```text
run_hygiene(project_id="<project>", scope="project")
```

Run a fast pending-save check:

```text
run_hygiene(project_id="<project>", check_pending_only=true)
```

Use the report fields:

- `duplicates_found`
- `outdated_decisions`
- `obsolete_patterns`
- `entity_drift_count`
- `stale_items`
- `pending_artifact_ids`
- `candidate_ids`

`run_hygiene` reports issues only. It does not delete, merge, or supersede memory automatically.
