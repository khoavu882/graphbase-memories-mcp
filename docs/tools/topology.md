# Topology Tools

Five tools for mapping service dependencies, shared infrastructure, and feature workflows in the
topology graph.

---

## Node registration

### `register_service`

Register or update a service node in the topology graph. Creates a dual-label `:Project:Service`
node so the service is also queryable as a memory scope anchor (`retrieve_context` resolves
`:Project` by `service_id`).

Idempotent — safe to call on every startup. The `workspace_id` must match an existing `:Workspace`
node; create it first with `register_federated_service`.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `service_id` | `string` | Yes | Stable unique identifier (used as graph key) |
| `name` | `string` | Yes | Canonical short name (slug) |
| `workspace_id` | `string` | Yes | Workspace this service belongs to |
| `display_name` | `string \| null` | No | Human-readable label |
| `service_type` | `ServiceType \| null` | No | Classification (e.g. `api`, `worker`, `gateway`) |
| `bounded_context` | `string \| null` | No | DDD bounded context name |
| `owner_team` | `string \| null` | No | Team responsible for this service |
| `health_status` | `ServiceHealthStatus` | No | Default: `unknown` |
| `env` | `string \| null` | No | Deployment environment (e.g. `prod`, `staging`) |
| `version` | `string \| null` | No | Current deployed version |
| `sla` | `string \| null` | No | SLA tier or target (e.g. `99.9%`) |
| `docs_url` | `string \| null` | No | Link to service documentation |
| `tags` | `list[string]` | No | Searchable labels |

#### Returns: `ServiceResult`

```json
{
  "service_id": "user-auth",
  "name": "user-auth",
  "workspace_id": "timo-platform",
  "display_name": "User Auth Service",
  "service_type": "api",
  "bounded_context": "Identity",
  "health_status": "healthy",
  "status": "saved",
  "tags": ["java", "spring-boot"]
}
```

!!! note "Topology vs federation"
    `register_service` (topology) creates the full service topology node with SLA, team, and
    health metadata. `register_federated_service` (federation) registers liveness into a workspace
    for cross-service search and impact analysis. Both can co-exist for the same logical service.

---

## Link operations

### `link_topology_nodes`

Create a typed relationship between any two topology nodes. The engine validates that `rel_type`
is compatible with the node label pair. Missing nodes and invalid rel types return structured
status values — no exception is raised.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `from_id` | `string` | Yes | ID of the source topology node |
| `to_id` | `string` | Yes | ID of the target topology node |
| `rel_type` | `TopologyLinkType` | Yes | Relationship type (see compatibility matrix below) |
| `workspace_id` | `string` | Yes | Workspace both nodes belong to |
| `step_order` | `integer \| null` | No | Step position for `INVOLVES` edges (1-based) |
| `role` | `string \| null` | No | Service role for `INVOLVES` edges (e.g. `orchestrator`) |
| `ownership` | `ServiceOwnership \| null` | No | Ownership type for `MEMBER_OF_CONTEXT` edges |
| `protocol` | `string \| null` | No | Transport protocol (REST, gRPC, kafka, etc.) |
| `timeout_ms` | `integer \| null` | No | Call timeout in milliseconds |
| `criticality` | `"high" \| "medium" \| "low" \| null` | No | Business criticality of the dependency |
| `access_pattern` | `string \| null` | No | DataSource access pattern (e.g. `cache-aside`) |
| `event_type` | `string \| null` | No | Event/message type for queue edges |
| `metadata` | `dict[string, string] \| null` | No | Arbitrary string key/value pairs |
| `dry_run` | `boolean` | No | Validate nodes exist without writing (default: `false`) |

#### Relationship compatibility matrix

| From → To | Valid `rel_type` values |
|---|---|
| `Service → Service` | `CALLS_DOWNSTREAM`, `CALLS_UPSTREAM` |
| `Service → DataSource` | `READS_FROM`, `WRITES_TO`, `READS_WRITES` |
| `Service → MessageQueue` | `PUBLISHES_TO`, `SUBSCRIBES_TO` |
| `Feature → Service` | `INVOLVES` (requires `step_order` + `role`) |
| `Service → BoundedContext` | `MEMBER_OF_CONTEXT` (use `ownership`) |

#### Returns: `TopologyLinkResult`

```json
{
  "from_id": "user-auth",
  "to_id": "postgres-main",
  "rel_type": "READS_WRITES",
  "status": "linked",
  "dry_run": false,
  "error": null
}
```

| `status` | Meaning |
|---|---|
| `linked` | Relationship created (or merged if duplicate) |
| `dry_run_ok` | Dry run succeeded — both nodes found, no write |
| `dry_run_node_missing` | Dry run found a missing node — check `error` field |
| `node_not_found` | One or both nodes do not exist in the graph |
| `invalid_rel_type` | `rel_type` is not valid for this node pair; `error` lists allowed values |

---

## Batch ingestion

### `batch_upsert_shared_infrastructure`

Upsert multiple shared infrastructure nodes (`DataSource`, `MessageQueue`, `Feature`,
`BoundedContext`) in a single call.

**Service nodes are not supported in batch** — use `register_service` per service to ensure
proper `:Project` dual-label creation for scope resolution.

Single-node registration requires no governance token. Multi-node (N>1) requires a governance
token obtained via `request_global_write_approval`.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | `string` | Yes | Workspace all nodes belong to |
| `governance_token` | `string \| null` | No* | Required when N>1; optional for single node |
| `nodes` | `list[SharedInfraNodeSchema]` | Yes | Heterogeneous list of nodes to upsert (min 1) |

#### Node item schemas (discriminated union on `node_type`)

**DataSource item** (`node_type: "datasource"`):
```json
{
  "node_type": "datasource",
  "source_id": "postgres-main",
  "source_type": "postgres",
  "host": "db.internal",
  "owner_team": "platform",
  "health_status": "healthy",
  "version": "15",
  "tags": ["primary-db"]
}
```

**MessageQueue item** (`node_type: "messagequeue"`):
```json
{
  "node_type": "messagequeue",
  "queue_id": "payment-events",
  "queue_type": "kafka",
  "topic_or_exchange": "payments.completed",
  "owner_team": "payments",
  "schema_version": "v2"
}
```

**Feature item** (`node_type: "feature"`):
```json
{
  "node_type": "feature",
  "feature_id": "checkout-flow",
  "name": "Checkout Flow",
  "workflow_order": 1,
  "owner_team": "commerce"
}
```

**BoundedContext item** (`node_type: "boundedcontext"`):
```json
{
  "node_type": "boundedcontext",
  "context_id": "identity",
  "name": "Identity",
  "domain": "Platform"
}
```

#### Returns: `BatchInfraResult`

```json
{
  "workspace_id": "timo-platform",
  "upserted": 3,
  "failed": 1,
  "errors": ["queue_id='broken-queue': source_type is required for datasource nodes"]
}
```

!!! warning "Governance token required for N>1"
    Submitting more than 1 node without a `governance_token` raises a Pydantic `ValidationError`
    before the request reaches the graph. Obtain a token with `request_global_write_approval`.

---

## Read / traversal

### `get_service_dependencies`

Traverse the service dependency graph from a starting service node and return all reachable
services up to a specified hop depth.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `service_id` | `string` | Yes | Starting service node identifier |
| `direction` | `"downstream" \| "upstream" \| "both"` | No | Default: `downstream` |
| `depth` | `integer` | No | Max traversal hops, 1–6 (default: `2`) |
| `limit` | `integer` | No | Max nodes returned, 1–200 (default: `50`) |

#### Returns: `ServiceDependencyResult`

```json
{
  "service_id": "user-auth",
  "direction": "downstream",
  "dependencies": [
    {
      "service_id": "postgres-main",
      "name": "postgres-main",
      "service_type": "datastore",
      "health_status": "healthy",
      "bounded_context": "Identity",
      "depth": 1
    },
    {
      "service_id": "notification-svc",
      "name": "notification-svc",
      "service_type": "worker",
      "health_status": "unknown",
      "bounded_context": null,
      "depth": 2
    }
  ]
}
```

| `direction` | Traverses |
|---|---|
| `downstream` | `CALLS_DOWNSTREAM` edges — services this service calls |
| `upstream` | `CALLS_UPSTREAM` edges — services that call this service |
| `both` | Both edge types — undirected traversal |

---

### `get_feature_workflow`

Return all services involved in a feature node, ordered by their workflow step. Each step is
created by `link_topology_nodes` with `rel_type=INVOLVES`, `step_order`, and `role`.

Read-only — no governance gate.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `feature_id` | `string` | Yes | Feature node identifier |

#### Returns: `FeatureWorkflowResult`

```json
{
  "feature_id": "checkout-flow",
  "steps": [
    {
      "service_id": "cart-svc",
      "name": "cart-svc",
      "service_type": "api",
      "health_status": "healthy",
      "bounded_context": "Commerce",
      "step_order": 1,
      "role": "orchestrator"
    },
    {
      "service_id": "payment-svc",
      "name": "payment-svc",
      "service_type": "api",
      "health_status": "healthy",
      "bounded_context": "Payments",
      "step_order": 2,
      "role": "processor"
    }
  ]
}
```
