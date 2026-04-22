---
name: graphbase-entity
description: Use when Codex needs to record, update, retrieve, or link facts about symbols, APIs, services, schemas, or domain concepts.
---

# Graphbase Entity

An `EntityFact` stores one durable fact about a named entity.

## Upsert

```json
{
  "entity": {
    "entity_name": "AuthTokenValidator",
    "fact": "Validates JWT expiry, issuer, and audience before request routing.",
    "scope": "project"
  },
  "project_id": "<project>",
  "related_entities": []
}
```

`upsert_entity_with_deps` merges by `entity_name` and `scope`, updates `fact`, and optionally links to existing `EntityFact` nodes.

Allowed relationship types:

- `BELONGS_TO`
- `CONFLICTS_WITH`
- `PRODUCED`
- `MERGES_INTO`
- `PRODUCES`
- `CONSUMES`
- `READS`
- `WRITES`
- `INVOLVES`

## Search

Use `memory_surface` for local focused lookup and `search_cross_service` for workspace-wide entity/decision search.
