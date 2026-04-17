---
name: graphbase-federation
description: Manage cross-workspace service federation — register external services, search across service boundaries, link shared concepts, and assess cross-service blast radius. Use when onboarding a federated service, surfacing shared patterns, or analyzing multi-workspace impact.
version: 1.0.0
tools:
  - register_federated_service
  - list_active_services
  - search_cross_service
  - link_cross_service
  - propagate_impact
  - graph_health
---

# graphbase-federation — Federation Management Skill

## When to use this skill

- When registering a service that spans multiple workspaces or is consumed externally
- When searching for shared concepts, decisions, or patterns across service boundaries
- When linking an entity in one service to a related entity in another (e.g. DEPENDS_ON, SHARES_CONCEPT)
- Before impact analysis that may cross workspace boundaries

---

## Service Lifecycle

### Register a federated service

```
register_federated_service(
  service_id="payment-gateway",
  workspace_id="platform",
  display_name="Payment Gateway",
  description="External payment processing service",
  tags=["payments", "external"],
  active=True
)
→ ServiceRegistrationResult { service_id, workspace_id, status }
```

Use `active=False` to mark a service as idle (soft deregistration — no data is deleted).

### List active services

```
list_active_services(
  workspace_id="platform",
  max_idle_minutes=60   # exclude services not seen in last 60 minutes
)
→ ServiceListResult { services: [ServiceInfo { service_id, display_name, last_seen, tags }] }
```

---

## Cross-Service Search

Find decisions, entities, or patterns that appear across multiple services in the workspace:

```
search_cross_service(
  query="authentication token validation",
  workspace_id="platform",
  target_project_ids=["auth-service", "api-gateway"],  # optional: narrow to specific services
  node_types=["EntityFact", "Decision"],               # optional: default is both
  limit=50
)
→ CrossServiceBundle {
    results: [{ node_id, project_id, label, summary, score }],
    total
  }
```

Use `search_cross_service` before `link_cross_service` to discover candidate nodes to link.

---

## Cross-Service Linking

Create a typed relationship between entities in different services. Same-project links are rejected.

```
link_cross_service(
  source_entity_id="<node_id from service A>",
  target_entity_id="<node_id from service B>",
  relationship_type="SHARES_CONCEPT",
  rationale="Both services enforce the same JWT validation logic independently",
  confidence=0.9,
  created_by="agent"
)
→ SaveResult { status, node_id }
```

**Relationship types:**

| `relationship_type` | Meaning |
|---------------------|---------|
| `DEPENDS_ON` | Source service depends on target concept |
| `SHARES_CONCEPT` | Both services independently implement the same concept |
| `CONTRADICTS` | Source and target express conflicting decisions |
| `SUPERSEDES` | Source replaces or overrides target |
| `EXTENDS` | Source extends or specializes target concept |

**Note:** Duplicate links are silently skipped (`duplicate_skip` status).

---

## Cross-Service Impact Analysis

After linking entities, assess blast radius before making a breaking change:

```
propagate_impact(
  source_entity_id="<entity id>",
  change_description="<what is changing>",
  impact_type="breaking_change"   # or "deprecation", "behavior_change"
)
→ ImpactReport {
    affected_services: [{ project_id, depth, risk_level, entity_count }],
    overall_risk: "low" | "medium" | "high",
    impact_event_id,
    next_step
  }
```

If `overall_risk == "high"`, review `affected_services` and notify those teams before merging.

---

## Workspace Health (Cross-Service Conflicts)

```
graph_health(workspace_id="platform")
→ WorkspaceHealthReport {
    services: [...],
    total_conflicts,
    conflict_records: [{ source_id, source_project, target_id, target_project, link_rationale }]
  }
```

`conflict_records` highlights entities with `CONTRADICTS` cross-service links.
Review and resolve before running hygiene to avoid false merges.

---

## Risk Levels

| Level | Meaning | Action |
|-------|---------|--------|
| `low` | Only this service affected | Proceed with awareness |
| `medium` | 2–4 services affected | Notify affected teams |
| `high` | 5+ services or deep graph | Coordinate before merging |
