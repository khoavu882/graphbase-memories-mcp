---
name: graphbase-impact
description: Use when analyzing the blast radius of a code change, before editing a shared entity, or when evaluating cross-service risk. Surfaces affected services and risk levels.
version: 2.1.0
tools:
  - propagate_impact
  - graph_health
  - memory_surface
---

# graphbase-impact — Blast-Radius Analysis Skill

## When to use this skill

- Before modifying a shared entity, API contract, or schema
- When a decision affects multiple services in the workspace
- When you want to find contradictory memories before making a change

## Impact Analysis Workflow

```
1. memory_surface(query="<entity being changed>", project_id="<project>")
   → identify which EntityFact / Decision nodes are relevant
   → note the node_id of the entity you are changing

2. propagate_impact(
     entity_id="<entity id from step 1>",
     change_description="<what is changing>",
     impact_type="breaking"   # or "deprecation", "behavior_change"
   )
   → ImpactReport {
       affected_services: [{ project_id, depth, risk_level, entity_count }],
       overall_risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
       impact_event_id,
       next_step
     }

3. If overall_risk is "HIGH" or "CRITICAL":
   → review affected_services list
   → notify those teams before merging
```

## Workspace Health & Conflict Detection

Conflicts between decisions are surfaced passively inside `graph_health` — no separate
conflict-detection call is needed:

```
graph_health(workspace_id="<workspace>")
→ WorkspaceHealthReport {
    services: [{ service_id, entity_count, conflict_count, staleness_days, hygiene_status }],
    total_conflicts,
    conflict_records: [
      {
        source_id, source_project, source_summary,
        target_id, target_project, target_summary,
        link_rationale, link_confidence
      }
    ],
    next_step
  }
```

Run periodically (or after large refactors) to keep the workspace graph healthy.
When `conflict_records` is non-empty, review and resolve before running `run_hygiene` to
avoid false merges.

## Risk Levels

| Level | Meaning | Action |
|-------|---------|--------|
| `LOW` | Low-depth or contained impact | Proceed with awareness |
| `MEDIUM` | Depth-2 impact | Notify affected teams |
| `HIGH` | Direct dependency impact | Coordinate before merging |
| `CRITICAL` | Contradicting cross-service link involved | Resolve conflict before merging |
