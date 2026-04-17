# Federation Tools

Eight tools for multi-service workspace coordination — registering services, searching across
them, creating typed cross-service links, and propagating breaking-change impact.

---

## Service registration

### `register_service`

Register (or re-activate) a service in a workspace. Creates the `Workspace` node if it does not
exist. Idempotent — safe to call on every server startup.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `service_id` | `string` | Yes | Unique service identifier (used as graph key) |
| `workspace_id` | `string` | Yes | Workspace to join; normalized to lowercase |
| `display_name` | `string \| null` | No | Human-readable name |
| `description` | `string \| null` | No | Short description |
| `tags` | `list[string] \| null` | No | Searchable labels (e.g. `["java", "kafka"]`) |

#### Returns: `ServiceRegistrationResult`

```json
{
  "service_info": {
    "service_id": "user-auth",
    "display_name": "User Auth Service",
    "workspace_id": "timo-platform",
    "status": "active",
    "last_seen": "2026-04-17T10:00:00Z",
    "tags": ["java", "spring-boot"]
  },
  "workspace_created": false,
  "status": "saved"
}
```

---

### `deregister_service`

Mark a service as idle. Does **not** delete any memory nodes — only updates the service status.
Use when a service is temporarily out of scope or has been retired.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `service_id` | `string` | Yes | Service to deregister |

#### Returns: `ServiceInfo`

```json
{
  "service_id": "user-auth",
  "display_name": "User Auth Service",
  "workspace_id": "timo-platform",
  "status": "idle",
  "last_seen": "2026-04-17T10:00:00Z",
  "tags": ["java", "spring-boot"]
}
```

---

### `list_active_services`

List all services in a workspace that have been seen within the idle window.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | `string` | Yes | Workspace to query |
| `max_idle_minutes` | `integer` | No | Exclude services last seen longer ago than this (default: `60`) |

#### Returns: `ServiceListResult`

```json
{
  "services": [
    {
      "service_id": "user-auth",
      "display_name": "User Auth Service",
      "workspace_id": "timo-platform",
      "status": "active",
      "last_seen": "2026-04-17T10:00:00Z",
      "tags": ["java"]
    }
  ],
  "workspace_id": "timo-platform",
  "retrieval_status": "succeeded"
}
```

---

## Cross-service knowledge

### `search_cross_service`

Full-text search across all services in a workspace. Searches `EntityFact` and `Decision` nodes
by default.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | `string` | Yes | Search keyword or phrase |
| `workspace_id` | `string` | Yes | Workspace to search |
| `target_project_ids` | `list[string] \| null` | No | Narrow search to specific services |
| `node_types` | `list[string] \| null` | No | Filter by label: `"EntityFact"`, `"Decision"` (default: both) |
| `limit` | `integer` | No | Max results (default: `50`) |

#### Returns: `CrossServiceBundle`

```json
{
  "items": [
    {
      "node_id": "uuid",
      "node_type": "EntityFact",
      "source_project": "user-auth",
      "score": 3.12,
      "summary": "JWT — RS256 tokens with 15-minute expiry"
    }
  ],
  "total_count": 1,
  "queried_projects": ["user-auth", "txn-management"],
  "retrieval_status": "succeeded"
}
```

---

### `link_cross_service`

Create a typed semantic link between entities in **different** services. Same-project links are
rejected. Duplicate links are silently skipped.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `source_entity_id` | `string` | Yes | UUID of the source entity node |
| `target_entity_id` | `string` | Yes | UUID of the target entity node |
| `relationship_type` | `string` | Yes | One of: `DEPENDS_ON`, `SHARES_CONCEPT`, `CONTRADICTS`, `SUPERSEDES`, `EXTENDS` |
| `rationale` | `string` | Yes | Why this link exists |
| `confidence` | `float` | No | Link confidence score 0.0–1.0 (default: `1.0`) |
| `created_by` | `string \| null` | No | Agent or user that created the link |

#### Returns: `SaveResult`

```json
{
  "status": "saved",
  "artifact_id": "uuid-of-link",
  "dedup_outcome": "new",
  "message": null
}
```

!!! warning "Cross-project only"
    `link_cross_service` validates that `source_entity_id` and `target_entity_id` belong to
    different projects. Linking within the same project returns `status: "failed"`.

---

## Impact analysis

### `propagate_impact`

Run a BFS traversal from an entity across all `CROSS_SERVICE_LINK` edges to find every service
affected by a breaking change. Writes an `ImpactEvent` audit node.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entity_id` | `string` | Yes | UUID of the changed entity; must exist in the graph |
| `change_description` | `string` | Yes | Human-readable description of the change |
| `impact_type` | `string` | No | Change category (default: `"breaking"`) |
| `max_depth` | `integer` | No | Max BFS hops (default: `3`, capped by `GRAPHBASE_IMPACT_MAX_DEPTH`) |

#### Returns: `ImpactReport` or `MCPError`

```json
{
  "source_entity_id": "uuid",
  "change_description": "JWT signing algorithm changed from RS256 to ES256",
  "impact_type": "breaking",
  "overall_risk": "HIGH",
  "affected_services": [
    { "project_id": "txn-management", "depth": 1, "risk_level": "HIGH", "entity_count": 3 },
    { "project_id": "notification-svc", "depth": 2, "risk_level": "MEDIUM", "entity_count": 1 }
  ],
  "impact_event_id": "uuid",
  "created_at": "2026-04-17T10:00:00Z",
  "next_step": null
}
```

| Depth | Risk level | Note |
|---|---|---|
| 1 | `HIGH` | Direct dependency |
| 2 | `MEDIUM` | One hop removed |
| 3 | `LOW` | Two hops removed |
| any | `CRITICAL` | Link type is `CONTRADICTS` |

Returns `MCPError` with `code: ENTITY_NOT_FOUND` if `entity_id` does not exist — call
`upsert_entity_with_deps` to create the entity first.

---

### `graph_health`

Return health metrics for all services in a workspace.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | `string` | Yes | Workspace to inspect |

#### Returns: `WorkspaceHealthReport`

```json
{
  "workspace_id": "timo-platform",
  "service_count": 3,
  "services": [
    {
      "service_id": "user-auth",
      "entity_count": 12,
      "decision_count": 5,
      "pattern_count": 2,
      "conflict_count": 0,
      "staleness_days": 8.3,
      "hygiene_status": "clean"
    }
  ],
  "total_conflicts": 0,
  "checked_at": "2026-04-17T10:00:00Z",
  "next_step": null
}
```

| `hygiene_status` | Meaning |
|---|---|
| `clean` | No stale or conflicted nodes |
| `needs_hygiene` | Some nodes approaching staleness |
| `critical` | Conflicts detected or many stale nodes |

---

### `detect_conflicts`

Return all `CONTRADICTS` cross-service links between services in the workspace.

#### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `workspace_id` | `string` | Yes | Workspace to inspect |
| `limit` | `integer` | No | Max conflicts to return (default: `100`) |

#### Returns: `list[ConflictRecord]`

```json
[
  {
    "source_id": "uuid-a",
    "source_project": "user-auth",
    "source_summary": "JWT must use RS256",
    "target_id": "uuid-b",
    "target_project": "api-gateway",
    "target_summary": "JWT algorithm is ES256",
    "link_rationale": "Different algorithm assumptions in each service",
    "link_confidence": 0.95
  }
]
```

Returns an empty list when no conflicts exist — this is not an error.

!!! tip "Conflict resolution workflow"
    1. Call `detect_conflicts` to list all contradictions.
    2. Investigate each pair and update the relevant `EntityFact` or `Decision` with `save_decision`.
    3. Call `link_cross_service` with `relationship_type="SUPERSEDES"` to document the resolution.
    4. Run `graph_health` to verify `total_conflicts` drops to zero.
