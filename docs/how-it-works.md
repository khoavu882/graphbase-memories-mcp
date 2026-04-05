# How It Works

## The graph model

graphbase-memories stores three kinds of nodes:

### MemoryNode

The primary unit — a single episodic record. Five types:

| Type | When to use |
|---|---|
| `session` | What happened in a coding session |
| `decision` | An architectural or design choice and its rationale |
| `pattern` | A reusable technique or convention |
| `context` | Background facts about the project |
| `entity_fact` | A fact about a specific entity (service, table, etc.) |

### EntityNode

Named things in your project. Six types: `service`, `file`, `feature`, `concept`, `table`, `topic`.

Entities are upserted by `(name, type, project)` — calling `upsert_entity` twice with the same key replaces the metadata rather than creating a duplicate.

### Edge

A directed relationship between any two nodes. Five types:

| Type | Meaning | Used between |
|---|---|---|
| `SUPERSEDES` | New memory replaces old | memory → memory |
| `RELATES_TO` | General association | memory → memory |
| `LEARNED_DURING` | Session that produced a memory | decision/pattern → session |
| `DEPENDS_ON` | Service/component dependency | entity → entity |
| `IMPLEMENTS` | Entity implements a concept | entity → entity |

## Append-only design

There is no `update_memory` tool. The graph is append-only by design:

```
store_memory(type="decision", title="Use Redis for session cache", ...)
  → memory A

# Later, decision changes:
store_memory(type="decision", title="Use PostgreSQL for session cache", ...)
  → memory B

relate_memories(from_id=B, to_id=A, relationship="SUPERSEDES")
  → edge B → A
```

`get_context` automatically excludes superseded memories from the YAML summary. The original decision (A) remains readable via `get_memory(include_deleted=False)` — the history is preserved.

## Token-budgeted injection

The hook calls:

```bash
python -m graphbase_memories inject --project <slug> --max-tokens 500
```

`formatters/yaml_context.py` renders memories, entities, and stale flags into a compact YAML block, then trims to fit within the token budget. The most recently updated memories are prioritised.

## Storage layout

```
~/.graphbase/
└── {project-slug}/
    ├── memories.db     # SQLite + FTS5, WAL mode
    └── graphbase.log   # JSON lines, 1MB × 3 rotation
```

Each project gets its own database file. The SQLite WAL mode ensures safe concurrent access from both the MCP server and CLI tools.

## Schema migrations

`_init_db()` runs on every connection open. The schema version is tracked via `PRAGMA user_version`:

- `current > SCHEMA_VERSION` → `RuntimeError` (downgrade guard — never silently corrupt)
- `current < SCHEMA_VERSION` → ordered migrations run in sequence

## Backend abstraction

All storage access goes through the `GraphEngine` ABC. Swap backends by setting:

```bash
GRAPHBASE_BACKEND=neo4j
```

The tool layer never imports `SQLiteEngine` or `Neo4jEngine` directly. See [Custom Backend](backends/custom.md) for implementing your own.
