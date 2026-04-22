---
name: graphbase-federation
description: Use for workspace service registration, active-service discovery, cross-service search/linking, impact propagation, and workspace health checks.
---

# Graphbase Federation

## Register or Deactivate

```text
register_federated_service(service_id="<service>", workspace_id="<workspace>", active=true)
register_federated_service(service_id="<service>", workspace_id="<workspace>", active=false)
```

`workspace_id` is normalized to lowercase. `active=false` marks a service idle and does not delete memory.

## Search and Link

```text
search_cross_service(query="<concept>", workspace_id="<workspace>")
link_cross_service(source_entity_id="<id-a>", target_entity_id="<id-b>", relationship_type="SHARES_CONCEPT", rationale="<why>")
```

Cross-service link types:

- `DEPENDS_ON`
- `SHARES_CONCEPT`
- `CONTRADICTS`
- `SUPERSEDES`
- `EXTENDS`

Same-project links are rejected.

## Health

```text
graph_health(workspace_id="<workspace>", include_conflicts=true)
```

Use `conflict_records` to resolve `CONTRADICTS` links before hygiene or broad refactors.
