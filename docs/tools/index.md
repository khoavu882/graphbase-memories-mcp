# MCP Tools Overview

`graphbase` exposes **21 async tools** across 9 functional groups. All tools use MCP JSON-RPC 2.0 over stdio.

---

## Tool groups

=== "By group"

    | Group | Tools | Purpose |
    |---|---|---|
    | [Retrieval](retrieval.md) | `retrieve_context`, `memory_surface` | Load memory before reasoning |
    | [Session](session.md) | `store_session_with_learnings` | Persist session summaries |
    | [Artifacts](artifacts.md) | `save_decision`, `save_pattern`, `save_context` | Save structured knowledge |
    | [Entity](entity.md) | `upsert_entity_with_deps` | Named entity graph nodes |
    | [Governance](governance.md) | `request_global_write_approval` | Gate global-scope writes |
    | [Analysis](analysis.md) | `route_analysis` *(deprecated — use `analysis_routing` prompt)* | Route tasks to reasoning mode |
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

Every tool that reads or writes memory requires a `project_id`. Without it, scope remains
`unresolved` and most tools return early with an empty or blocked result.

!!! info "First time with a new project"
    Call `retrieve_context(project_id="your-project", scope="project")` first. If the project
    doesn't exist yet, `retrieval_status` will be `empty` and `scope_state` will be `uncertain`.
    Memory writes, including `store_session_with_learnings`, require a resolved project. In
    service-oriented setups, `register_federated_service(service_id=project_id, ...)` is the
    simplest way to create that scope anchor.

---

## Return types

All tools return structured Pydantic models serialized to JSON:

| Model | Returned by |
|---|---|
| `ContextBundle` | `retrieve_context` |
| `SaveResult` | `save_decision`, `save_pattern`, `save_context`, `upsert_entity_with_deps`, `link_cross_service` |
| `BatchSaveResult` | `store_session_with_learnings` |
| `HygieneReport` | `run_hygiene` |
| `AnalysisResult` | `route_analysis` |
| `ServiceResult` | `register_service` |
| `TopologyLinkResult` | `link_topology_nodes` |
| `BatchInfraResult` | `batch_upsert_shared_infrastructure` |
| `ServiceDependencyResult` | `get_service_dependencies` |
| `FeatureWorkflowResult` | `get_feature_workflow` |
| `ServiceRegistrationResult` | `register_federated_service` (active=true) |
| `ServiceListResult` | `list_active_services` |
| `CrossServiceBundle` | `search_cross_service` |
| `ImpactReport` | `propagate_impact` |
| `WorkspaceHealthReport` | `graph_health` |

---

## Error contract

Tools never throw exceptions to the caller. All error states are encoded as fields in the return value:

- `SaveResult.status` — `saved` / `failed` / `blocked_scope` / `pending_retry`
- `ContextBundle.retrieval_status` — `succeeded` / `empty` / `timed_out` / `failed`
- `MCPError` — returned by `route_analysis`, `upsert_entity_with_deps`, and governance tools when a structured error applies (use `error: true` as discriminant)
- Governance errors — returned as `{ "blocked": true, "reason": "..." }`

This means your agent always receives a structured response and can decide how to proceed.
