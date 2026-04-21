---
name: graphbase-guide
description: Quick reference for all 20 graphbase MCP tools, 4 prompts, 2 resources, and 2 resource templates. Use when you need to know which tool to call, what parameters it accepts, or what the server exposes.
version: 2.1.0
tools:
  - retrieve_context
  - memory_surface
  - upsert_entity_with_deps
  - save_decision
  - save_pattern
  - save_context
  - store_session_with_learnings
  - run_hygiene
  - propagate_impact
  - graph_health
  - register_service
  - link_topology_nodes
  - batch_upsert_shared_infrastructure
  - get_service_dependencies
  - get_feature_workflow
  - request_global_write_approval
  - register_federated_service
  - list_active_services
  - search_cross_service
  - link_cross_service
---

# graphbase — Quick Reference (20 Tools)

## Memory Lifecycle

### Before starting work
1. `retrieve_context(project_id, scope="project")` — load full context; check `ContextBundle.scope_state`
2. Or `memory_surface(query="<topic>")` — lightweight targeted BM25 lookup

### While working
- `memory_surface(query)` — surface relevant memories for a symbol or topic
- `upsert_entity_with_deps(entity={...}, project_id="<project>")` — update an entity fact

### On save / session end
- `store_session_with_learnings(session={...}, project_id, decisions=[], patterns=[])` — checkpoint

---

## Tool Reference

### Retrieval (2)
| Tool | When to use |
|------|-------------|
| `retrieve_context` | Full scope-aware context bundle (focus > project > global); returns `scope_state` inline |
| `memory_surface` | Targeted BM25 lookup by keyword, symbol, or topic |

### Write (4)
| Tool | When to use |
|------|-------------|
| `upsert_entity_with_deps` | Create/update EntityFact + optional typed links to existing EntityFact nodes |
| `save_decision` | Persist an architectural decision |
| `save_pattern` | Persist a recurring implementation pattern |
| `save_context` | Persist a context note (topic + content) |

### Session (1)
| Tool | When to use |
|------|-------------|
| `store_session_with_learnings` | Save session summary with decisions and patterns; replaces start_session / end_session |

### Hygiene (1)
| Tool | When to use |
|------|-------------|
| `run_hygiene` | Full scan: duplicates, outdated decisions, drift, freshness, pending saves; use `check_pending_only=True` for fast pending check |

### Analysis and Impact (2 tools + prompts)
| Tool | When to use |
|------|-------------|
| `propagate_impact` | Blast-radius from a changed entity |
| `graph_health` | Workspace-level health; returns `conflict_records` inline (replaces detect_conflicts) |

### Topology (5)
| Tool | When to use |
|------|-------------|
| `register_service` | Add/update a service node in the workspace |
| `link_topology_nodes` | Create any service topology relationship (replaces all link_service_* / link_feature_* tools) |
| `batch_upsert_shared_infrastructure` | Register datasource, messagequeue, feature, or boundedcontext nodes; N=1 requires no token |
| `get_service_dependencies` | Read upstream/downstream dependencies for a service |
| `get_feature_workflow` | Read ordered service steps for a feature |

### Federation (2)
| Tool | When to use |
|------|-------------|
| `register_federated_service` | Register an external / cross-workspace service |
| `list_active_services` | List all active services in the workspace (replaces list_services) |

### Cross-Service (2)
| Tool | When to use |
|------|-------------|
| `search_cross_service` | Find entity facts and decisions across workspace services |
| `link_cross_service` | Create a cross-service relationship (federated link) |

### Governance (1)
| Tool | When to use |
|------|-------------|
| `request_global_write_approval` | Get governance token for global decisions or guarded batch topology writes |

---

## MCP Prompts (4)

| Prompt | Purpose |
|--------|---------|
| `analysis_routing` | Decide whether to retrieve, write, or run hygiene for the current context |
| `memory_review` | Guided review of a project's current memory state |
| `impact_before_edit` | Analyze blast-radius before modifying a key entity |
| `federated_sync` | Synchronize shared patterns across workspace services |

---

## MCP Resources

- `graphbase://schema` — live Pydantic schema for all tools and result types
- `graphbase://services` — list of registered services in the current workspace

## MCP Resource Templates

- `graphbase://health/{workspace_id}` — workspace health snapshot
- `graphbase://session/{session_id}` — retrieve a saved session

---

## Key Behavioral Changes (from v1.x)

| Old tool | Replacement |
|----------|-------------|
| `start_session` / `end_session` / `save_session` | `store_session_with_learnings` |
| `get_scope_state` | `ContextBundle.scope_state` returned inline by `retrieve_context` |
| `memory_freshness` | `HygieneReport.stale_items` returned inline by `run_hygiene` |
| `get_save_status` / `get_pending_saves` | `run_hygiene(check_pending_only=True)` |
| `detect_conflicts` | `WorkspaceHealthReport.conflict_records` returned inline by `graph_health` |
| `link_service_dependency` / `link_service_datasource` / `link_service_mq` / `link_feature_service` / `link_service_context` | `link_topology_nodes` |
| `register_datasource` / `register_message_queue` / `register_feature` / `register_bounded_context` | `batch_upsert_shared_infrastructure` |
| `check_governance_policy` | Removed — call `request_global_write_approval` directly |
| `list_services` | `list_active_services` |
| `analyze_memory_needs` / `route_analysis` | `analysis_routing` prompt |
