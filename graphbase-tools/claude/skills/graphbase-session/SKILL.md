---
name: graphbase-session
description: Manage Claude Code session lifecycle with graphbase. Use at session start to load context, and at session end to persist decisions, patterns, and open items.
version: 2.1.0
tools:
  - retrieve_context
  - memory_surface
  - store_session_with_learnings
  - run_hygiene
---

# graphbase-session — Session Lifecycle Skill

## Session Start Protocol

```
1. retrieve_context(project_id="<project>", scope="project")
   → ContextBundle.scope_state:
     "resolved"   — project exists, context loaded
     "uncertain"  — project_id was provided but no Project node exists
     "unresolved" — no project_id was provided

2. (Optional) memory_surface(query="<task topic>", project_id="<project>")
   → targeted BM25 lookup for a specific symbol or topic
   → use when retrieve_context returns many items and you need to narrow focus
```

**Scope-state decision tree:**

| `scope_state` | Action |
|---|---|
| `resolved` | Proceed — full context loaded |
| `uncertain` | Register the service/project first; writes return `blocked_scope` |
| `unresolved` | Provide a project_id before reading or writing |

## Session End Protocol

```
store_session_with_learnings(
  session={
    "objective":    "<what you set out to do>",
    "actions_taken": ["<list of concrete actions>"],
    "decisions_made": ["<decisions recorded this session>"],
    "open_items":   ["<unresolved items>"],
    "next_actions": ["<what to do next session>"],
    "save_scope":   "project"
  },
  project_id="<project>",
  decisions=[
    {
      "title":     "<decision title>",
      "rationale": "<why>",
      "owner":     "<who>",
      "date":      "YYYY-MM-DD",
      "scope":     "project",
      "confidence": 0.9
    }
  ],
  patterns=[]   # omit or pass [] if no new patterns this session
)
→ BatchSaveResult { session, decisions, patterns, overall }
```

Pass `decisions=[]` and `patterns=[]` (or omit them) to save a session-only summary.

## Checking Pending Saves

If a previous session was interrupted, check for unresolved writes before starting a new one:

```
run_hygiene(project_id="<project>", check_pending_only=True)
→ HygieneReport.pending_artifact_ids   — list of unresolved write IDs
→ HygieneReport.oldest_pending_at      — timestamp of oldest pending write
→ HygieneReport.pending_only == True   — confirms fast-path was used
```

This does **not** run a full hygiene scan and does **not** update `last_hygiene_at`.

## Scope Rules

| Scope | When to use |
|-------|------------|
| `project` | Decisions and patterns specific to this service/repo |
| `global` | Cross-service decisions (requires governance token when saved as a decision) |
| `focus` | Focus area (e.g. "auth", "payments") within a project |
