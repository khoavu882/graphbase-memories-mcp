---
name: graphbase-impact
description: Use when analyzing the blast radius of a code change, before editing a shared entity, or when evaluating cross-service risk. Surfaces affected services and risk levels.
version: 1.0.0
tools:
  - propagate_impact
  - detect_conflicts
  - graph_health
---

# graphbase-impact — Blast-Radius Analysis Skill

## When to use this skill

- Before modifying a shared entity, API contract, or schema
- When a decision affects multiple services in the workspace
- When you want to find contradictory memories before making a change

## Impact Analysis Workflow

```
1. memory_surface(query="<entity being changed>")
   → identify which EntityFact / Decision nodes are relevant

2. propagate_impact(
     source_entity_id="<entity id from step 1>",
     change_description="<what is changing>",
     impact_type="breaking_change"   # or "deprecation", "behavior_change"
   )
   → ImpactReport with affected_services, risk levels, depth

3. If overall_risk == "high":
   → review affected_services list
   → notify those teams before merging
```

## Conflict Detection

```
detect_conflicts(
  project_id="<project>",
  scope="project"
)
```

Returns `ConflictRecord` list — pairs of nodes with contradictory content. Resolve conflicts
before running hygiene to avoid false merges.

## Workspace Health

```
graph_health(workspace_id="<workspace>")
```

Returns `WorkspaceHealthReport` — per-service entity counts, staleness days, conflict counts.
Run periodically (or after large refactors) to keep the workspace graph healthy.

## Risk Levels

| Level | Meaning | Action |
|-------|---------|--------|
| `low` | Only this service affected | Proceed with awareness |
| `medium` | 2–4 services affected | Notify affected teams |
| `high` | 5+ services or deep graph | Coordinate before merging |
