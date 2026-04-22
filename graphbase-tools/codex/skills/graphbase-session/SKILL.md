---
name: graphbase-session
description: Use at Codex session start or end to load scoped memory and persist session summaries, decisions, patterns, and next actions.
---

# Graphbase Session

## Start

Call:

```text
retrieve_context(project_id="<project>", scope="project")
```

Interpret `scope_state`:

| State | Meaning | Action |
|---|---|---|
| `resolved` | Project exists | Continue with loaded memory |
| `uncertain` | Project id provided, no `Project` node exists | Register service/project before writing |
| `unresolved` | No project id | Ask for or infer the project id before memory calls |

Use `memory_surface(query="<topic>", project_id="<project>")` when the task is narrow or you need symbol-specific memory.

## End

Call `store_session_with_learnings`:

```json
{
  "session": {
    "objective": "What this session attempted",
    "actions_taken": ["Concrete actions"],
    "decisions_made": ["Decisions reached"],
    "open_items": ["Open issues"],
    "next_actions": ["Next session actions"],
    "save_scope": "project"
  },
  "project_id": "<project>",
  "decisions": [],
  "patterns": []
}
```

Add `governance_token` only when any batched decision has `scope="global"`.
