# Entity Tool

One tool for managing named entities and their relationships in the graph.

---

## `upsert_entity_with_deps`

Upsert a named entity fact and optionally link it to related entities. Uses MERGE semantics — calling this multiple times with the same `entity_name` updates the existing node rather than creating duplicates.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `entity` | `EntityFactSchema` | Yes | The primary entity to upsert |
| `related_entities` | `list[EntityFactSchema]` | No | Related entities to upsert and link |
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

When `related_entities` are provided, each is upserted and linked to the primary entity. The relationship type is inferred from context or defaults to `[:CONFLICTS_WITH]` for conflicting entities and `[:PRODUCED]` for produced artifacts.

```python
upsert_entity_with_deps(
    entity={
        "entity_name": "WriteEngine",
        "fact": "Orchestrates governance gate, dedup check, and retry logic for all write operations.",
        "scope": "project"
    },
    related_entities=[
        {
            "entity_name": "DedupEngine",
            "fact": "Called by WriteEngine before every Decision/Pattern write.",
            "scope": "project"
        },
        {
            "entity_name": "GovernanceToken",
            "fact": "Required by WriteEngine for global-scope writes.",
            "scope": "project"
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
