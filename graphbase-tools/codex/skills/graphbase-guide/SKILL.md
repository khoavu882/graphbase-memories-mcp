---
name: graphbase-guide
description: Use when you need a quick map of Graphbase Memories tools, prompts, resources, and recommended Codex workflows.
---

# Graphbase Guide

Use Graphbase Memories as Codex's persistent graph-backed project memory.

## Server Surface

Graphbase exposes:

- 20 MCP tools
- 4 prompts: `analysis_routing`, `memory_review`, `impact_before_edit`, `federated_sync`
- 2 resources: `graphbase://schema`, `graphbase://services`
- 2 resource templates: `graphbase://health/{workspace_id}`, `graphbase://session/{session_id}`

## Tool Groups

| Group | Tools |
|---|---|
| Retrieval | `retrieve_context`, `memory_surface` |
| Session | `store_session_with_learnings` |
| Artifacts | `save_decision`, `save_pattern`, `save_context` |
| Entity | `upsert_entity_with_deps` |
| Governance | `request_global_write_approval` |
| Hygiene | `run_hygiene` |
| Federation | `register_federated_service`, `list_active_services`, `search_cross_service`, `link_cross_service`, `propagate_impact`, `graph_health` |
| Topology | `register_service`, `link_topology_nodes`, `batch_upsert_shared_infrastructure`, `get_service_dependencies`, `get_feature_workflow` |

## Default Codex Workflow

1. Start with `retrieve_context(project_id="<project>", scope="project")`.
2. Use `memory_surface(query="<topic>", project_id="<project>")` for focused lookup.
3. Before cross-service or shared entity changes, run `propagate_impact`.
4. At session end, call `store_session_with_learnings`.
5. When memory looks stale or pending writes exist, call `run_hygiene`.

If `scope_state` is `uncertain`, register the project/service first with `register_federated_service` or `register_service`; memory writes require resolved scope.
