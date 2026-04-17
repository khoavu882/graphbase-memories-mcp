---
name: graphbase-topology
description: Upsert service topology into the graph — register services, shared infrastructure, features, and all relationships between them. Use when onboarding a new service, after a dependency refactor, or before running blast-radius analysis.
version: 2.0.0
tools:
  - retrieve_context
  - register_service
  - batch_upsert_shared_infrastructure
  - link_topology_nodes
  - get_service_dependencies
  - get_feature_workflow
  - request_global_write_approval
---

# graphbase-topology — Service Topology Upsert Skill

Use this skill to populate the graph with service dependency topology:
service nodes, shared infrastructure (databases, queues, features, bounded contexts),
and the relationships that connect them. All operations are idempotent — safe to re-run
after code changes to update the graph to current state.

---

## Quick Reference

| Goal | Start here |
|---|---|
| Register one service and its dependencies | Phase 0 → 2 → 3 for that service only |
| Onboard a full workspace (many services) | Full Phase 0 → 1 → 2 → 3 → 4 |
| Update existing dependencies after refactor | Phase 3 only (nodes already exist) |
| Verify current graph state | Phase 4 only |

---

## Discovery Modes

Choose one before starting. Different modes require different user input.

### `explicit` mode
The user provides the relationship list directly. Highest confidence.
Use when the user says: "login-service calls user-auth over REST with high criticality."

### `config` mode
Scan service configuration files to infer topology:
- `application.yml` / `env.conf` / `.env` → service URLs → `CALLS_DOWNSTREAM`
- DB connection strings → `READS_FROM` / `WRITES_TO` (DataSource)
- Kafka/RabbitMQ topic configs → `PUBLISHES_TO` / `SUBSCRIBES_TO` (MessageQueue)
- Gradle `*-agent` module dependencies → `CALLS_DOWNSTREAM` (via API contract)

**Always confirm inferences with the user before writing.**

### `source` mode
Read Java/Python source code to infer topology:
- `RestTemplate`, `WebClient`, `FeignClient` calls → `CALLS_DOWNSTREAM`
- `@KafkaListener(topics=...)` → `SUBSCRIBES_TO`
- `kafkaTemplate.send(topic, ...)` → `PUBLISHES_TO`
- `RedisTemplate` / `jedis` usage → `READS_WRITES` on a Redis DataSource
- `@RabbitListener(queues=...)` → `SUBSCRIBES_TO`

**Always confirm inferences with the user before writing.**

---

## What You Cannot Infer — Ask the User

| Data point | Why it needs user input |
|---|---|
| `workspace_id` | Must match an existing `:Workspace` node |
| `criticality` on dependency edges | Business risk judgment |
| `step_order` in feature workflows | Process ordering from documentation |
| Feature membership | Which services belong to which feature |
| `bounded_context` groupings | DDD boundaries, not deterministic from code |
| `owner_team` | Organisational knowledge |

---

## Execution Phases

Execute in strict order. Each phase is a prerequisite for the next.

---

### Phase 0 — Prerequisites

```
retrieve_context(project_id=<workspace_id>, scope="project")
→ ContextBundle.scope_state:
    "resolved"   — workspace exists, context loaded → proceed
    "uncertain"  — workspace exists but has few memories → proceed with caution
    "unresolved" — workspace not found → ask user for correct workspace_id
```

**Governance token (only when batch-upserting >1 infra node):**

```
request_global_write_approval(
  rationale="Batch-registering shared infra nodes for <workspace_id> topology upsert",
  ttl_seconds=600
)
→ save token.id — consumed once in Phase 1 Option B
```

Single-node `batch_upsert_shared_infrastructure` calls (N=1) do **not** require a token.

---

### Phase 1 — Register Shared Infrastructure

Register all infrastructure nodes before any services. All operations use MERGE — idempotent.

**Option A — Single node (no governance token required):**

```
batch_upsert_shared_infrastructure(inp={
  workspace_id: <workspace_id>,
  nodes: [
    { node_type: "datasource", source_id: "redis-session", source_type: "redis",
      host: "redis.internal", owner_team: "platform" }
  ]
})
→ check: upserted == 1 AND failed == 0

batch_upsert_shared_infrastructure(inp={
  workspace_id: <workspace_id>,
  nodes: [
    { node_type: "messagequeue", queue_id: "login-events", queue_type: "kafka",
      topic_or_exchange: "login.events.v1" }
  ]
})

batch_upsert_shared_infrastructure(inp={
  workspace_id: <workspace_id>,
  nodes: [
    { node_type: "feature", feature_id: "user-login-flow",
      name: "User Login Flow", workflow_order: 1 }
  ]
})

batch_upsert_shared_infrastructure(inp={
  workspace_id: <workspace_id>,
  nodes: [
    { node_type: "boundedcontext", context_id: "identity",
      name: "Identity", domain: "Platform" }
  ]
})
```

**Option B — Batch (governance token required, for >1 infra node in one call):**

```
batch_upsert_shared_infrastructure(inp={
  workspace_id: <workspace_id>,
  governance_token: <token.id from Phase 0>,
  nodes: [
    { node_type: "datasource",    source_id: "redis-session", source_type: "redis", ... },
    { node_type: "messagequeue",  queue_id: "login-events",   queue_type: "kafka",  ... },
    { node_type: "feature",       feature_id: "user-login-flow", name: "...",        ... },
    { node_type: "boundedcontext",context_id: "identity",     name: "...",           ... }
  ]
})
→ check: upserted > 0 AND failed == 0
→ if failed > 0: surface errors list, stop — do not proceed to Phase 2
```

**Note:** Services cannot be batched — use `register_service()` per service (Phase 2).

---

### Phase 2 — Register Service Nodes

Services use MERGE on `:Project:Service` dual-label. Order does not matter between services.

```
register_service(inp={
  service_id: "api-gateway",
  name: "api-gateway",
  workspace_id: <workspace_id>,
  service_type: "gateway",
  bounded_context: "infrastructure",
  health_status: "healthy",
  owner_team: "platform",
  version: "2.1.0"
})

register_service(inp={
  service_id: "login-service",
  name: "login-service",
  workspace_id: <workspace_id>,
  service_type: "api",
  bounded_context: "identity",
  health_status: "healthy",
  owner_team: "identity-team"
})
```

**Hard gate:** All services must succeed before Phase 3. A failed `register_service` means the endpoint node does not exist — linking to it will fail.

---

### Phase 3 — Register Relationships

All relationship writes use `link_topology_nodes`. The server validates `rel_type` against
the labels of `from_id` and `to_id` — use the IDs you assigned in Phases 1 and 2.

**Always run the dry-run pass first.** This validates that both endpoint nodes exist before
committing any writes. Fix missing nodes before proceeding to the write pass.

**Dry-run pass:**

```
link_topology_nodes(inp={
  from_id: "api-gateway",
  to_id:   "login-service",
  rel_type: "CALLS_DOWNSTREAM",
  workspace_id: <workspace_id>,
  dry_run: true
})
→ {status: "dry_run_ok"}          — both nodes found, safe to write
→ {status: "dry_run_node_missing"} — stop, fix missing node first
```

**Write pass** (after all dry-runs return `dry_run_ok`):

**3a — Service-to-service dependencies:**

```
link_topology_nodes(inp={
  from_id:     "api-gateway",
  to_id:       "login-service",
  rel_type:    "CALLS_DOWNSTREAM",
  workspace_id: <workspace_id>,
  protocol:    "REST",
  timeout_ms:  5000,
  criticality: "high",
  dry_run:     false
})
```

Valid `rel_type` values for service→service: `CALLS_DOWNSTREAM`, `CALLS_UPSTREAM`

**3b — Service-to-datasource links:**

```
link_topology_nodes(inp={
  from_id:       "login-service",
  to_id:         "redis-session",
  rel_type:      "READS_WRITES",
  workspace_id:  <workspace_id>,
  access_pattern: "cache-aside",
  dry_run:       false
})
```

Valid `rel_type` values for service→datasource: `READS_FROM`, `WRITES_TO`, `READS_WRITES`

**3c — Service-to-message-queue links:**

```
link_topology_nodes(inp={
  from_id:     "login-service",
  to_id:       "login-events",
  rel_type:    "PUBLISHES_TO",
  workspace_id: <workspace_id>,
  event_type:  "LoginSucceededEvent",
  dry_run:     false
})
```

Valid `rel_type` values for service→messagequeue: `PUBLISHES_TO`, `SUBSCRIBES_TO`

**3d — Feature-to-service links:**

```
link_topology_nodes(inp={
  from_id:     "user-login-flow",
  to_id:       "api-gateway",
  rel_type:    "INVOLVES",
  workspace_id: <workspace_id>,
  step_order:  1,
  role:        "entry",
  dry_run:     false
})

link_topology_nodes(inp={
  from_id:     "user-login-flow",
  to_id:       "login-service",
  rel_type:    "INVOLVES",
  workspace_id: <workspace_id>,
  step_order:  2,
  role:        "authenticator",
  dry_run:     false
})
```

`INVOLVES` is the fixed `rel_type` for feature→service edges.

**3e — Service-to-bounded-context links:**

```
link_topology_nodes(inp={
  from_id:     "login-service",
  to_id:       "identity",
  rel_type:    "MEMBER_OF_CONTEXT",
  workspace_id: <workspace_id>,
  ownership:   "owner",
  dry_run:     false
})
```

`MEMBER_OF_CONTEXT` is the fixed `rel_type` for service→bounded-context edges.

> **Note:** The graph uses `MEMBER_OF_CONTEXT` for service→bounded-context edges to avoid
> collision with artifact→Project ownership edges. Do not use `BELONGS_TO`.

---

### Phase 4 — Verify

```
get_service_dependencies(inp={
  service_id: "api-gateway",
  direction:  "downstream",
  depth:      2
})
→ verify login-service appears in dependencies list at depth 1

get_feature_workflow(inp={
  feature_id: "user-login-flow"
})
→ verify steps ordered correctly: api-gateway (step 1), login-service (step 2)
```

Report to user: counts of nodes registered, edges created, verification results.

---

## Relationship Type Reference

| `from` node type | `to` node type | `rel_type` values | Key edge properties |
|---|---|---|---|
| Service | Service | `CALLS_DOWNSTREAM`, `CALLS_UPSTREAM` | `protocol`, `timeout_ms`, `criticality` |
| Service | DataSource | `READS_FROM`, `WRITES_TO`, `READS_WRITES` | `access_pattern` |
| Service | MessageQueue | `PUBLISHES_TO`, `SUBSCRIBES_TO` | `event_type` |
| Feature | Service | `INVOLVES` (fixed) | `step_order`, `role` |
| Service | BoundedContext | `MEMBER_OF_CONTEXT` (fixed) | `ownership` |

All edge properties are optional. Omitting them on a re-link preserves existing values.

---

## Error Recovery

| Error | Recovery |
|---|---|
| `scope_state: "unresolved"` | Verify `workspace_id` with user; first `register_service` will create the Workspace node |
| `dry_run_node_missing` | Re-run Phase 1 or 2 for the missing node, then retry Phase 3 |
| `batch_upsert` returns `failed > 0` | Check `errors` list, fix individual nodes, re-run batch or use single-node calls |
| Governance token expired (TTL 600s) | Request a new token and retry `batch_upsert` only — all prior writes are idempotent |
