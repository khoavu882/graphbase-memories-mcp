---
name: graphbase-entity
description: Create, update, and retrieve entity facts with linked decisions and patterns. Use when tracking a symbol, API, service component, or concept in the knowledge graph.
version: 2.1.0
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
  entity={
    "entity_name": "HygieneEngine",
    "fact": "Runs dedup, staleness, drift, and pending-save checks.",
    "scope": "project"
  },
  project_id="<project>",
  related_entities=[],
  focus=None
)
```

The `upsert_entity_with_deps` tool:
- Creates the entity if it does not exist (MERGE on `entity_name` + `scope`)
- Updates the `fact` if it does exist
- Optionally links to existing `EntityFact` nodes by ID using typed relationships:
  `BELONGS_TO`, `CONFLICTS_WITH`, `PRODUCED`, `MERGES_INTO`, `PRODUCES`, `CONSUMES`,
  `READS`, `WRITES`, or `INVOLVES`

## Finding Cross-Service Entities

```
search_cross_service(
  query="circuit breaker",
  workspace_id="<workspace>",
  limit=10
)
```

Returns `CrossServiceBundle` — entities or decisions from other services in the
workspace that match the query. Useful before introducing a pattern that may already exist
elsewhere.

## Scoping Rules

| Scope | project_id required? | Who can write? |
|-------|---------------------|---------------|
| `project` | Yes | Anyone with project scope |
| `global` | Yes | Governance token required for global artifact writes; entity writes still require resolved project scope |

## Freshness

Freshness is derived from graph timestamps. If `freshness == "stale"` in a surface or hygiene
result, call `upsert_entity_with_deps` with the latest fact to refresh the stored content.
