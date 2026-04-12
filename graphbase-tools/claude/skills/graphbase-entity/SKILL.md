---
name: graphbase-entity
description: Create, update, and retrieve entity facts with linked decisions and patterns. Use when tracking a symbol, API, service component, or concept in the knowledge graph.
version: 1.0.0
tools:
  - upsert_entity_with_deps
  - retrieve_context
  - search_cross_service
  - memory_surface
---

# graphbase-entity — Entity CRUD Skill

## What is an Entity?

An `EntityFact` node stores a discrete fact about a named entity (a class, function, API, service,
or concept). It can link to:
- `Decision` nodes — why the entity was designed this way
- `Pattern` nodes — how it is used in practice

## Creating / Updating an Entity

```
upsert_entity_with_deps(
  entity_name="HygieneEngine",
  fact="Runs four-phase dedup/staleness cycle. Batch size controlled by max_candidates setting.",
  project_id="<project>",
  decision_titles=["Use batch deletion for hygiene performance"],
  pattern_triggers=["run hygiene before retrieval in long sessions"]
)
```

The `upsert_entity_with_deps` tool:
- Creates the entity if it does not exist (MERGE on entity_name + scope)
- Updates the `fact` if it does exist (sets `updated_at`)
- Links the listed decisions and patterns (creates them if absent)

## Finding Cross-Service Entities

```
search_cross_service(
  query="circuit breaker",
  workspace_id="<workspace>",
  limit=10
)
```

Returns `CrossServiceBundle` — entities, decisions, or patterns from other services in the
workspace that match the query. Useful before introducing a pattern that may already exist
elsewhere.

## Scoping Rules

| Scope | project_id required? | Who can write? |
|-------|---------------------|---------------|
| `project` | Yes | Anyone with project scope |
| `global` | No | Governance token required |

## Freshness

Entity facts have `updated_at` set on every MERGE. If `_freshness == "stale"` in a retrieval
result, call `upsert_entity_with_deps` with the latest fact to refresh it.
