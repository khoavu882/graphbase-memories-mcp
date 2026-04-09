# Entity Tool

One tool for managing named entities and their relationships in the graph.

---

## `upsert_entity_with_deps`

Upsert a named entity fact and optionally link it to related entities. Uses MERGE semantics — calling this multiple times with the same `entity_name` updates the existing node rather than creating duplicates.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entity` | `EntityFactSchema` | Yes | The primary entity to upsert |
| `related_entities` | `list[EntityRelation]` | No | Typed relationships to existing entity nodes |
| `project_id` | `string` | Yes | Project identifier |
| `focus` | `string \| null` | No | Focus area |

### `EntityFactSchema`

```json
{
  "entity_name": "DedupEngine",
  "fact": "Implements two-step deduplication: SHA-256 exact hash check followed by Jaccard similarity on full-text candidates.",
  "scope": "project"
}
```

| Field | Description |
|---|---|
| `entity_name` | Canonical name of the entity (used as MERGE key) |
| `fact` | A single fact statement about the entity |
| `scope` | Memory scope |

### Related entity linking

`related_entities` takes a list of `EntityRelation` objects — typed edges from the primary entity to **existing** entity nodes (identified by their UUID). The `relationship_type` field is required and must be one of:

| Type | Meaning |
|---|---|
| `BELONGS_TO` | This entity belongs to a scope node |
| `CONFLICTS_WITH` | This entity conflicts with another entity |
| `PRODUCED` | This entity was produced by another entity |
| `MERGES_INTO` | This entity should be merged into a canonical node (hygiene) |

```python
# First upsert the entities you want to link
dedup_result = upsert_entity_with_deps(
    entity={
        "entity_name": "DedupEngine",
        "fact": "SHA-256 exact hash + Jaccard similarity dedup for decisions.",
        "scope": "project"
    },
    project_id="graphbase-memories"
)

# Then link them using the returned artifact_id
upsert_entity_with_deps(
    entity={
        "entity_name": "WriteEngine",
        "fact": "Orchestrates governance gate, dedup check, and retry logic for all write operations.",
        "scope": "project"
    },
    related_entities=[
        {
            "entity_id": dedup_result["artifact_id"],
            "relationship_type": "PRODUCED",
            "properties": {}
        }
    ],
    project_id="graphbase-memories"
)
```

### Returns: `SaveResult`

```json
{
  "status": "saved",
  "artifact_id": "uuid-of-primary-entity",
  "dedup_outcome": null,
  "message": "Upserted 1 entity + 2 related entities"
}
```

---

## Entity normalization

The hygiene engine detects `EntityFact` nodes with the same `entity_name` across the graph and proposes `[:MERGES_INTO]` edges to normalize them. This prevents entity drift where the same concept is stored under slightly different names over multiple sessions.

See [Hygiene tools](hygiene.md) and [Memory Model](../concepts/memory-model.md) for details.
