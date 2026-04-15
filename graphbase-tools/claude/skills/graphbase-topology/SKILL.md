---
name: graphbase-topology
description: Upsert service topology into the graph — register services, shared infrastructure, features, and all relationships between them. Use when onboarding a new service, after a dependency refactor, or before running blast-radius analysis.
version: 1.0.0
tools:
  - register_service
  - register_datasource
  - register_message_queue
  - register_feature
  - register_bounded_context
  - link_service_dependency
  - link_service_datasource
  - link_service_mq
  - link_feature_service
  - link_service_context
  - batch_upsert_shared_infrastructure
  - get_service_dependencies
  - get_feature_workflow
  - request_global_write_approval
  - check_governance_policy
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
1. get_scope_state(project_id=<workspace_id>)
   → must return scope_state: "resolved"
   → if "unresolved": ask user for correct workspace_id

2. (Only if using batch_upsert_shared_infrastructure)
   check_governance_policy(
     proposed_decision="batch infrastructure upsert for workspace <workspace_id>",
     project_id=<workspace_id>
   )
   → if policy allows:
   request_global_write_approval(
     rationale="Batch-registering shared infra nodes for <workspace_id> topology upsert",
     ttl_seconds=600
   )
   → save token.id — consumed once in Phase 1
```

---

### Phase 1 — Register Shared Infrastructure

Register all infrastructure nodes before any services. All operations use MERGE — idempotent.

**Option A — Individual (no governance token required):**

```
register_datasource(inp={
  source_id: "redis-session",
  source_type: "redis",
  workspace_id: <workspace_id>,
  host: "redis.internal",
  owner_team: "platform"
})

register_message_queue(inp={
  queue_id: "login-events",
  queue_type: "kafka",
  topic_or_exchange: "login.events.v1",
  workspace_id: <workspace_id>
})

register_feature(inp={
  feature_id: "user-login-flow",
  name: "User Login Flow",
  workspace_id: <workspace_id>,
  workflow_order: 1
})

register_bounded_context(inp={
  context_id: "identity",
  name: "Identity",
  domain: "Platform",
  workspace_id: <workspace_id>
})
```

**Option B — Batch (governance token required, for >5 infra nodes):**

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

**Always run the dry-run pass first.** This validates that both endpoint nodes exist before
committing any writes. Fix missing nodes before proceeding to the write pass.

**Dry-run pass:**

```
link_service_dependency(
  inp={from_service_id:"api-gateway", to_service_id:"login-service",
       rel_type:"CALLS_DOWNSTREAM", dry_run:true},
  workspace_id:<workspace_id>
)
→ {status: "dry_run_ok"}  — both nodes found, safe to write
→ {status: "dry_run_node_missing"}  — stop, fix missing node first
```

**Write pass** (after all dry-runs return `dry_run_ok`):

**3a — Service-to-service dependencies:**

```
link_service_dependency(
  inp={
    from_service_id: "api-gateway",
    to_service_id:   "login-service",
    rel_type:        "CALLS_DOWNSTREAM",
    protocol:        "REST",
    timeout_ms:      5000,
    criticality:     "high",
    dry_run:         false
  },
  workspace_id: <workspace_id>
)
```

**3b — Service-to-datasource links:**

```
link_service_datasource(
  inp={
    service_id:     "login-service",
    source_id:      "redis-session",
    rel_type:       "READS_WRITES",
    access_pattern: "cache-aside",
    dry_run:        false
  },
  workspace_id: <workspace_id>
)
```

Relationship type options: `READS_FROM`, `WRITES_TO`, `READS_WRITES`

**3c — Service-to-message-queue links:**

```
link_service_mq(
  inp={
    service_id: "login-service",
    queue_id:   "login-events",
    rel_type:   "PUBLISHES_TO",
    event_type: "LoginSucceededEvent",
    dry_run:    false
  },
  workspace_id: <workspace_id>
)
```

**3d — Feature-to-service links:**

```
link_feature_service(
  inp={
    feature_id: "user-login-flow",
    service_id: "api-gateway",
    step_order: 1,
    role:       "entry",
    dry_run:    false
  },
  workspace_id: <workspace_id>
)

link_feature_service(
  inp={
    feature_id: "user-login-flow",
    service_id: "login-service",
    step_order: 2,
    role:       "authenticator",
    dry_run:    false
  },
  workspace_id: <workspace_id>
)
```

**3e — Service-to-context links:**

```
link_service_context(
  inp={
    service_id: "login-service",
    context_id: "identity",
    ownership:  "owner",
    dry_run:    false
  },
  workspace_id: <workspace_id>
)
```

> **Note on relationship naming:** The graph uses `MEMBER_OF_CONTEXT` for the
> service→bounded-context edge (not `BELONGS_TO` as in the PDR).
> This avoids collision with artifact→Project ownership edges. Use `link_service_context()` exclusively.

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

| Link tool | rel_type values | Key edge properties |
|---|---|---|
| `link_service_dependency` | `CALLS_DOWNSTREAM`, `CALLS_UPSTREAM` | `protocol`, `timeout_ms`, `criticality` |
| `link_service_datasource` | `READS_FROM`, `WRITES_TO`, `READS_WRITES` | `access_pattern` |
| `link_service_mq` | `PUBLISHES_TO`, `SUBSCRIBES_TO` | `event_type` |
| `link_feature_service` | `INVOLVES` (fixed) | `step_order`, `role` |
| `link_service_context` | `MEMBER_OF_CONTEXT` (fixed) | `ownership` |

All edge properties are optional. Omitting them on a re-link preserves existing values.

---

## Error Recovery

| Error | Recovery |
|---|---|
| `dry_run_node_missing` for a service | Re-run Phase 2 for the missing service, then retry Phase 3 |
| `batch_upsert` returns `failed > 0` | Check `errors` list, fix individual nodes, re-run batch or use individual `register_*` calls |
| Governance token expired (TTL 600s) | Request a new token (`request_global_write_approval`) and retry the `batch_upsert` call only — all prior calls are idempotent |
| Workspace not found | Use `register_service(workspace_id=...)` — it creates the Workspace node if absent |
