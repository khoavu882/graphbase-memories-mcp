---
name: graphbase-session
description: Manage Claude Code session lifecycle with graphbase. Use at session start to load context, and at session end to persist decisions, patterns, and open items.
version: 1.0.0
tools:
  - start_session
  - end_session
  - get_scope_state
  - memory_surface
  - get_pending_saves
---

# graphbase-session — Session Lifecycle Skill

## Session Start Protocol

```
1. get_scope_state(project_id="<project>")
   → if scope_state == "unresolved": ask user for project_id
   → if scope_state == "uncertain": proceed with caution

2. memory_surface(query="<task topic>", project_id="<project>")
   → review matches for relevant prior decisions or patterns

3. retrieve_context(project_id="<project>", scope="project")
   → load full context bundle before making changes
```

## Session End Protocol

```
end_session(
  objective="<what you set out to do>",
  actions_taken=["<list of concrete actions>"],
  decisions_made=["<decisions recorded this session>"],
  open_items=["<unresolved items>"],
  next_actions=["<what to do next session>"],
  project_id="<project>",
  save_scope="project"
)
```

## Pending Saves

If `end_session` returns `status=blocked_scope`, call `get_scope_state` first.
If saves are pending from a previous session, call `get_pending_saves` to review them.

## Scope Rules

| Scope | When to use |
|-------|------------|
| `project` | Decisions and patterns specific to this service/repo |
| `global` | Cross-service standards (requires governance token) |
| `focus` | Focus area (e.g., "auth", "payments") within a project |
