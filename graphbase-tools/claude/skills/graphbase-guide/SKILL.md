---
name: graphbase-guide
description: Quick reference for all 22 graphbase-memories-mcp MCP tools, resources, and prompts. Use when you need to know which tool to call, what parameters it accepts, or what the server exposes.
version: 1.0.0
tools:
  - memory_surface
  - retrieve_context
  - get_scope_state
  - upsert_entity_with_deps
  - save_decision
  - save_pattern
  - save_context
  - end_session
  - get_pending_saves
  - run_hygiene
  - memory_freshness
  - propagate_impact
  - detect_conflicts
  - register_service
  - list_services
  - search_cross_service
  - graph_health
  - check_governance_policy
  - request_global_write_approval
  - get_save_status
  - analyze_memory_needs
  - start_session
---

# graphbase-memories-mcp — Quick Reference

## Memory Lifecycle

### Before starting work
1. `get_scope_state(project_id)` — confirm project exists
2. `retrieve_context(project_id, scope="project")` — load full context
3. Or `memory_surface(query="<topic>")` — lightweight targeted lookup

### While working
- `memory_surface(query)` — surface relevant memories for a symbol or topic
- `upsert_entity_with_deps(entity_name, fact, project_id)` — update an entity

### On save / session end
- `end_session(objective, actions_taken, decisions_made, ...)` — checkpoint

---

## Tool Reference

### Retrieval
| Tool | When to use |
|------|-------------|
| `retrieve_context` | Full scope-aware context bundle (focus > project > global) |
| `memory_surface` | Targeted BM25 lookup by keyword, symbol, or topic |
| `get_scope_state` | Check project exists before writing |
| `search_cross_service` | Find patterns shared across workspace services |

### Write
| Tool | When to use |
|------|-------------|
| `upsert_entity_with_deps` | Create/update EntityFact + link decisions/patterns |
| `save_decision` | Persist an architectural decision |
| `save_pattern` | Persist a recurring implementation pattern |
| `save_context` | Persist a context note (topic + content) |
| `end_session` | Save session summary with decisions and patterns |
| `start_session` | Open a new session with objective |

### Analysis
| Tool | When to use |
|------|-------------|
| `analyze_memory_needs` | Route: should you retrieve, write, or hygiene? |
| `propagate_impact` | Blast-radius from a changed entity |
| `detect_conflicts` | Find contradictions in project memories |
| `graph_health` | Workspace-level health across all services |

### Governance
| Tool | When to use |
|------|-------------|
| `check_governance_policy` | Evaluate a change against global policies |
| `request_global_write_approval` | Get governance token for global writes |

### Hygiene
| Tool | When to use |
|------|-------------|
| `run_hygiene` | Merge duplicates, flag outdated decisions |
| `memory_freshness` | Show stale nodes ordered by age |
| `get_save_status` | List pending saves |
| `get_pending_saves` | Counts and timestamps of unresolved saves |

### Service Registry
| Tool | When to use |
|------|-------------|
| `register_service` | Add a new service to the workspace |
| `list_services` | List all services in workspace |

---

## MCP Resources

- `graphbase://schema` — live Pydantic schema for all tools and result types
- `graphbase://services` — list of registered services in the current workspace
- `graphbase://session/{session_id}` — retrieve a saved session

## MCP Prompts

- `memory_review` — guided review of a project's current memory state
- `impact_before_edit` — analyze blast-radius before modifying a key entity
- `federated_sync` — synchronize shared patterns across workspace services
