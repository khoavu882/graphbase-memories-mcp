---
name: graphbase-hygiene
description: Keep the memory graph clean. Use when the graph is accumulating duplicates, when decisions are stale, or when pending saves are piling up. Run after major refactors.
version: 2.0.0
tools:
  - run_hygiene
---

# graphbase-hygiene — Memory Hygiene Skill

## What hygiene does

A single `run_hygiene` call covers all maintenance dimensions:

1. **Duplicate detection** — nodes with identical or near-identical content
2. **Outdated decisions** — decisions not updated in >180 days
3. **Obsolete patterns** — patterns not referenced in session notes for >90 days
4. **Entity drift** — EntityFacts whose content diverges across duplicate nodes
5. **Freshness scan** — nodes ordered by age with `FreshnessLevel` labels (`current` / `recent` / `stale`)
6. **Pending saves** — unresolved write failures from previous sessions

## When to run

- After a major refactor (many files changed)
- When `HygieneReport.stale_items` has `freshness == "stale"` entries
- Before starting a new planning session after a long break
- When the PostToolUse hook advisory fires after a git commit

## Hygiene Workflows

### Full scan

```
run_hygiene(project_id="<project>", scope="project")
→ HygieneReport {
    duplicates_found,
    outdated_decisions,
    obsolete_patterns,
    entity_drift_count,
    stale_items: [{ node_id, label, title, age_days, freshness, project_id }],
    pending_artifact_ids,
    oldest_pending_at,
    candidate_ids: { "<category>": ["<node_id>", ...] },
    checked_at,
    next_step
  }
```

Review `candidate_ids` and manually update or delete stale nodes.
`run_hygiene` never auto-mutates — all changes must be applied explicitly.

### Pending-saves check (fast path)

Use when you only want to know if there are unresolved writes without running a full scan:

```
run_hygiene(project_id="<project>", check_pending_only=True)
→ HygieneReport {
    pending_artifact_ids,
    oldest_pending_at,
    pending_only: True   ← confirms fast-path was used
  }
```

`check_pending_only=True` does **not** update `last_hygiene_at` and skips all content scans.

### Global hygiene

```
run_hygiene(scope="global")
```

Scans across all projects in the workspace. Useful after cross-service refactors.

## CLI Shortcut

```bash
graphbase hygiene --scope project --project-id <project>
```

Prints `HygieneReport` as JSON. Useful in CI or scheduled maintenance scripts.

## Freshness levels

| Level | Age | Action |
|---|---|---|
| `current` | ≤ 7 days | No action needed |
| `recent` | 7–30 days | Monitor; may become stale |
| `stale` | > 30 days | Review and update or delete |
