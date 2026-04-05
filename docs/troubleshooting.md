# Troubleshooting

Run `graphbase-memories doctor --project <slug>` first — it checks the most common issues automatically.

---

## Hook not injecting context

**Symptom**: No YAML context block appears at session start.

**Check**:
```bash
# Test hook manually
GRAPHBASE_PROJECT=your-slug ~/.claude/hooks/graphbase-memories-hook.sh
```

**Causes and fixes**:

| Cause | Fix |
|---|---|
| `GRAPHBASE_PROJECT` not set | Add it to Claude Code `settings.json` `env` block |
| Hook not registered | Add hook path to `settings.json` `hooks.UserPromptSubmit` |
| Hook not executable | `chmod +x ~/.claude/hooks/graphbase-memories-hook.sh` |
| No memories stored yet | Store a memory first — empty projects produce no output |
| Hook script path wrong | Use absolute path; `~` may not expand in all shells |

---

## MCP server not connecting

**Symptom**: Claude Code shows the tool as unavailable or times out.

**Check**:
```bash
python -m graphbase_memories server  # should block, waiting for JSON-RPC input
```

**Causes and fixes**:

| Cause | Fix |
|---|---|
| Wrong Python path in `.mcp.json` | Use `which python3` and set absolute path |
| Package not installed | `pip install graphbase-memories-mcp` |
| `.mcp.json` syntax error | Validate with `python3 -m json.tool .mcp.json` |
| Port conflict (SSE mode) | Change `--port` to an unused port |

---

## DevTools sidecar not starting

**Symptom**: `server --devtools` starts MCP correctly, but no DevTools UI becomes available.

**Check**:
```bash
graphbase-memories server --devtools --devtools-project your-project-slug
```

Watch `stderr` for sidecar status messages.

**Causes and fixes**:

| Cause | Fix |
|---|---|
| `--devtools-project` not set and `GRAPHBASE_PROJECT` missing | Pass `--devtools-project <slug>` or set `GRAPHBASE_PROJECT` |
| DevTools port already in use | Change `--devtools-port` to an unused port |
| Static assets missing | Reinstall the package or pass `--static-dir` explicitly |
| Browser did not open | Use `--open-browser` only when desired; otherwise open the printed URL manually |

In `stdio` mode, DevTools sidecar logs go to `stderr` by design so MCP `stdout` stays valid.

---

## `RuntimeError: schema version X > SCHEMA_VERSION Y`

**Symptom**: The server or CLI crashes with this error on startup.

**Cause**: You're running an older version of graphbase-memories against a database created by a newer version.

**Fix**: Upgrade the package:
```bash
pip install --upgrade graphbase-memories-mcp
```

If you need to downgrade the DB (not recommended), back up first:
```bash
cp ~/.graphbase/my-project/memories.db memories.db.bak
```

---

## FTS5 search returns no results

**Symptom**: `search_memories` returns empty results for terms that should match.

**Diagnose**:
```bash
graphbase-memories doctor --project my-project  # checks FTS5 present
```

**Causes and fixes**:

| Cause | Fix |
|---|---|
| FTS index out of sync | Run: `sqlite3 ~/.graphbase/my-project/memories.db "INSERT INTO memories_fts(memories_fts) VALUES('rebuild')"` |
| Query uses FTS5 syntax incorrectly | Avoid special chars; use plain terms or `"exact phrase"` |
| SQLite compiled without FTS5 | Rebuild SQLite with FTS5 (`--enable-fts5`), or use a different Python distribution |

---

## Cross-project search misses projects

**Symptom**: `search_memories` without a project doesn't find memories from some projects.

**Cause**: The data directory has projects whose databases exist but weren't discovered.

**Fix**: Ensure `GRAPHBASE_DATA_DIR` points to the correct root:
```bash
ls ~/.graphbase/  # should show project subdirectories
```

Each subdirectory must contain `memories.db` to be discovered. If you moved databases manually, ensure the subdirectory name matches the project slug you used when storing memories.

---

## `export` produces empty entities/edges

**Symptom**: Export JSON has memories but empty `entities` and `edges` arrays.

**Cause**: Memories stored with `store_memory` (not `store_memory_with_entities`) have no entity links. Edges are only stored when `relate_memories` or `link_entities` is called.

**Not a bug** — this is expected for bare memories. Use `store_memory_with_entities` when you want automatic entity extraction.

---

## Neo4j connection refused

**Symptom**: `GRAPHBASE_BACKEND=neo4j` fails with connection error.

**Check**:
```bash
graphbase-memories doctor --project my-project
# Look for Neo4j reachable check
```

**Fix**:
```bash
# Start Neo4j via Docker
make neo4j-up     # from project root, if Makefile is available

# Or manually
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/graphbase \
  neo4j:5-community
```

Verify environment variables are set:
```bash
export GRAPHBASE_BACKEND=neo4j
export GRAPHBASE_NEO4J_URI=bolt://localhost:7687
export GRAPHBASE_NEO4J_USER=neo4j
export GRAPHBASE_NEO4J_PASSWORD=graphbase
```

---

## Import fails: `Unsupported format_version`

**Symptom**: `graphbase-memories import` exits with format version error.

**Cause**: The file was not produced by `graphbase-memories export`, or was hand-edited incorrectly.

**Fix**: Ensure the top-level `format_version` field is `"1.0"`:
```bash
python3 -m json.tool export.json | grep format_version
```
