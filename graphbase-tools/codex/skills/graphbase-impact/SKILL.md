---
name: graphbase-impact
description: Use before changing shared entities, API contracts, schemas, topology, or decisions that may affect multiple services.
---

# Graphbase Impact

1. Locate the entity:

```text
memory_surface(query="<entity or API>", project_id="<project>")
```

2. Propagate impact:

```text
propagate_impact(entity_id="<entity-id>", change_description="<what changes>", impact_type="breaking")
```

Risk levels are uppercase:

- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

If risk is `HIGH` or `CRITICAL`, inspect affected services and workspace conflicts before editing.

3. Check health:

```text
graph_health(workspace_id="<workspace>", include_conflicts=true)
```
