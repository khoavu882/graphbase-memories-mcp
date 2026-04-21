# MCP Tools Overview

`graphbase` exposes **20 async tools** across 8 functional groups. All tools use MCP JSON-RPC 2.0 over stdio.

In addition to the tool surface, the server also registers:

- **4 prompts**: `analysis_routing`, `memory_review`, `impact_before_edit`, `federated_sync`
- **2 resources**: `graphbase://schema`, `graphbase://services`
- **2 resource templates**: `graphbase://health/{workspace_id}`, `graphbase://session/{session_id}`

---

## Tool groups

=== "By group"

    | Group | Tools | Purpose |
    |---|---|---|
    | [Retrieval](retrieval.md) | `retrieve_context`, `memory_surface` | Load memory before reasoning |
    | [Session](session.md) | `store_session_with_learnings` | Persist session summaries |
    | [Artifacts](artifacts.md) | `save_decision`, `save_pattern`, `save_context` | Save structured knowledge |
    | [Entity](entity.md) | `upsert_entity_with_deps` | Named entity graph nodes |
    | [Governance](governance.md) | `request_global_write_approval` | Issue one-time governance tokens |
    | [Hygiene](hygiene.md) | `run_hygiene` | Memory maintenance, health, and staleness tracking |
    | [Federation](federation.md) | `register_federated_service`, `list_active_services`, `search_cross_service`, `link_cross_service`, `propagate_impact`, `graph_health` | Multi-service workspace coordination |
    | [Topology](topology.md) | `register_service`, `link_topology_nodes`, `batch_upsert_shared_infrastructure`, `get_service_dependencies`, `get_feature_workflow` | Service dependency and infrastructure graph |

=== "Recommended call sequence"

    ```mermaid
    sequenceDiagram
        participant A as Agent
        participant M as MCP Server

        A->>M: retrieve_context(project_id, scope="project")
        M-->>A: ContextBundle { items, retrieval_status }

        Note over A: ... reason, work, decide ...

        A->>M: store_session_with_learnings(session, decisions, patterns)
        M-->>A: BatchSaveResult { session, decisions, patterns }
    ```

---

## Scope requirement

Most memory tools require a resolved `project_id`.

- If `project_id` is missing, scope is `unresolved`
- If `project_id` is unknown, scope is usually `uncertain`
- Writes require `scope_state="resolved"`

Federation and topology tools use `workspace_id`, service IDs, or topology node IDs instead of project scope resolution.

!!! info "First time with a new project"
    Call `retrieve_context(project_id="your-project", scope="project")` first. If the project
    does not exist yet, `retrieval_status` will be `empty` and `scope_state` will be `uncertain`.
    In service-oriented setups, `register_federated_service(service_id=project_id, ...)` is the
    simplest way to create that scope anchor.

---

## Return types

All tools return structured Pydantic models serialized to JSON:

| Model | Returned by |
|---|---|
| `ContextBundle` | `retrieve_context` |
| `SurfaceResult` | `memory_surface` |
| `SaveResult` | `save_decision`, `save_pattern`, `save_context`, `upsert_entity_with_deps`, `link_cross_service` |
| `BatchSaveResult` | `store_session_with_learnings` |
| `GovernanceTokenResult` | `request_global_write_approval` |
| `HygieneReport` | `run_hygiene` |
| `ServiceRegistrationResult` / `ServiceInfo` | `register_federated_service` |
| `ServiceListResult` | `list_active_services` |
| `CrossServiceBundle` | `search_cross_service` |
| `ImpactReport` | `propagate_impact` |
| `WorkspaceHealthReport` | `graph_health` |
| `ServiceResult` | `register_service` |
| `TopologyLinkResult` | `link_topology_nodes` |
| `BatchInfraResult` | `batch_upsert_shared_infrastructure` |
| `ServiceDependencyResult` | `get_service_dependencies` |
| `FeatureWorkflowResult` | `get_feature_workflow` |

---

## Error contract

Tools never throw raw exceptions to the caller. Error states are encoded as return values whenever possible:

- `SaveResult.status` — `saved` / `failed` / `blocked_scope` / `pending_retry` / `duplicate_skip`
- `ContextBundle.retrieval_status` — `succeeded` / `empty` / `timed_out` / `failed` / `conflicted`
- `MCPError` — used by selected tool flows that need a structured error envelope, such as blocked entity writes and missing impact-analysis entities
- Governance failures surface as structured failure results rather than crashing the caller

This means the agent always receives a parseable response and can decide what to do next.
