---
name: graphbase-topology
description: Use to register service topology, shared infrastructure, feature workflows, bounded contexts, and dependency edges.
---

# Graphbase Topology

## Register Services

```json
{
  "inp": {
    "service_id": "api-gateway",
    "name": "api-gateway",
    "workspace_id": "platform",
    "service_type": "gateway",
    "health_status": "healthy",
    "tags": ["edge", "http"]
  }
}
```

`register_service` creates or updates a dual-label `:Project:Service` node, so it also resolves project memory scope.

## Register Infrastructure

Use `batch_upsert_shared_infrastructure` for:

- `datasource`
- `messagequeue`
- `feature`
- `boundedcontext`

Single-node batches do not need governance. Multi-node batches require `governance_token`.

## Link Nodes

Always dry-run before writing:

```json
{
  "inp": {
    "from_id": "api-gateway",
    "to_id": "auth-service",
    "rel_type": "CALLS_DOWNSTREAM",
    "workspace_id": "platform",
    "dry_run": true
  }
}
```

Then repeat with `"dry_run": false` if the result is `dry_run_ok`.

Read topology with `get_service_dependencies` and `get_feature_workflow`.
