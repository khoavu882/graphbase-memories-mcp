# MCP Tools Overview

`graphbase` exposes **22 async tools** across 9 functional groups. All tools use MCP JSON-RPC 2.0 over stdio.

---

## Tool groups

=== "By group"

    | Group | Tools | Purpose |
    |---|---|---|
    | [Retrieval](retrieval.md) | `retrieve_context`, `get_scope_state`, `memory_surface` | Load memory before reasoning |
    | [Session](session.md) | `save_session`, `store_session_with_learnings` | Persist session summaries |
    | [Artifacts](artifacts.md) | `save_decision`, `save_pattern`, `save_context` | Save structured knowledge |
    | [Entity](entity.md) | `upsert_entity_with_deps` | Named entity graph nodes |
    | [Governance](governance.md) | `request_global_write_approval` | Gate global-scope writes |
    | [Analysis](analysis.md) | `route_analysis` | Route tasks to reasoning mode |
    | [Hygiene](hygiene.md) | `run_hygiene`, `get_save_status`, `memory_freshness` | Memory maintenance, health, and freshness tracking |
    | [Federation](federation.md) | `register_service`, `deregister_service`, `list_active_services`, `search_cross_service`, `link_cross_service`, `propagate_impact`, `graph_health`, `detect_conflicts` | Multi-service workspace coordination |

=== "Recommended call sequence"

    ```mermaid
    sequenceDiagram
        participant A as Agent
        participant M as MCP Server

        A->>M: get_scope_state(project_id)
        M-->>A: { scope_state: "resolved" }

        A->>M: retrieve_context(project_id, scope="project")
        M-->>A: ContextBundle { items, retrieval_status }

        Note over A: ... reason, work, decide ...

        A->>M: store_session_with_learnings(session, decisions, patterns)
        M-->>A: BatchSaveResult { session, decisions, patterns }
    ```

---

## Scope requirement

Every tool that reads or writes memory requires a `project_id`. Without it, scope remains `unresolved` and most tools return early with an empty or blocked result.

!!! info "First time with a new project"
    Call `get_scope_state(project_id="your-project")` first. It returns `uncertain` if the project
    doesn't exist yet in the graph. A first `save_session` call creates the Project node automatically.

---

## Return types

All tools return structured Pydantic models serialized to JSON:

| Model | Returned by |
|---|---|
| `ContextBundle` | `retrieve_context` |
| `SaveResult` | `save_session`, `save_decision`, `save_pattern`, `save_context`, `upsert_entity_with_deps` |
| `BatchSaveResult` | `store_session_with_learnings` |
| `HygieneReport` | `run_hygiene` |
| `FreshnessReport` | `memory_freshness` |
| `SaveStatusSummary` | `get_save_status` |
| `AnalysisResult` | `route_analysis` |

---

## Error contract

Tools never throw exceptions to the caller. All error states are encoded as fields in the return value:

- `SaveResult.status` — `saved` / `failed` / `blocked_scope` / `pending_retry`
- `ContextBundle.retrieval_status` — `succeeded` / `empty` / `timed_out` / `failed`
- `MCPError` — returned by `route_analysis`, `upsert_entity_with_deps`, and governance tools when a structured error applies (use `error: true` as discriminant)
- Governance errors — returned as `{ "blocked": true, "reason": "..." }`

This means your agent always receives a structured response and can decide how to proceed.
