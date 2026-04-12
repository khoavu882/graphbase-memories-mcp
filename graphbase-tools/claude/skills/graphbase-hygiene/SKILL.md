---
name: graphbase-hygiene
description: Keep the memory graph clean. Use when the graph is accumulating duplicates, when decisions are stale, or when pending saves are piling up. Run after major refactors.
version: 1.0.0
tools:
  - run_hygiene
  - memory_freshness
  - get_save_status
---

# graphbase-hygiene — Memory Hygiene Skill

## What hygiene does

The hygiene cycle runs four phases:
1. **Duplicate detection** — finds nodes with identical or near-identical content
2. **Outdated decisions** — flags decisions not updated in `freshness_stale_days`
3. **Obsolete patterns** — flags patterns no longer referenced in session notes
4. **Entity drift** — detects EntityFacts whose fact text diverges across duplicate nodes

## When to run

- After a major refactor (many files changed)
- When `memory_freshness` reports `stale_count > 5`
- Before starting a new planning session after a long break
- When `run_hygiene` advisory appears in PostToolUse hook output

## Hygiene Workflow

```
1. memory_freshness(project_id="<project>", stale_after_days=30)
   → FreshnessReport — how many stale nodes?

2. run_hygiene(project_id="<project>", scope="project")
   → HygieneReport — duplicates, outdated, obsolete, drift counts
   → candidate_ids — node IDs to review

3. For each candidate: review and either update or delete.

4. (Optionally) run_hygiene(scope="global") for workspace-level hygiene.
```

## CLI Shortcut

```bash
graphbase-memories-mcp hygiene --scope project --project-id <project>
```

Prints `HygieneReport` as JSON. Useful in CI or scheduled scripts.

## Pending Saves

```
get_save_status(project_id="<project>")
```

Returns `SaveStatusSummary` — if `status == "pending"`, call `end_session` to flush
unresolved writes before running hygiene.
