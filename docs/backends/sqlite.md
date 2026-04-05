# SQLite Backend

The default backend. Zero external dependencies — works immediately after install.

## Storage

```
~/.graphbase/{project-slug}/memories.db
```

SQLite with:
- **FTS5** full-text search (BM25 ranking)
- **WAL mode** for safe concurrent access from MCP server + CLI
- **JSON columns** for tags, metadata, and edge properties
- **Schema migrations** via `PRAGMA user_version`

## Configuration

| Variable | Default | Description |
|---|---|---|
| `GRAPHBASE_DATA_DIR` | `~/.graphbase` | Root directory for all project databases |

No other configuration needed. Each project automatically gets its own subdirectory and database file.

## Schema version

The current schema version is `2`. Migrations run automatically on connection open.

To inspect:
```bash
sqlite3 ~/.graphbase/my-project/memories.db "PRAGMA user_version"
```

## Performance notes

- FTS5 `MATCH` queries are O(log n) against the inverted index
- `graph_view` uses a temp table (`_gd_ids`) to avoid `SQLITE_MAX_VARIABLE_NUMBER` limits when fetching edges for many memory IDs
- Entity→entity edges (`DEPENDS_ON`, `IMPLEMENTS`) have a unique index on `(from_id, to_id, type)` to enforce idempotency
- WAL checkpoint runs automatically — no manual maintenance needed

## Backup

```bash
sqlite3 ~/.graphbase/my-project/memories.db ".backup backup.db"
```

Or use `graphbase-memories export` for a JSON backup that's portable across backends.
