# graphbase-memories

Graph-backed episodic memory for coding agents — an MCP server (stdio) that stores sessions, decisions, and patterns as a knowledge graph and injects relevant context at session start.

## Problem

Serena stores project-level and symbol-level notes well, but loses episodic memory: *why* a design was chosen, *which* patterns were adopted, *what* was tried and failed. After a context compaction, all of that is gone.

**graphbase-memories** stores episodic memory as a graph, survives compactions, and injects a token-budgeted YAML summary into every session via a hook.

## Architecture in one line

```
SQLite + FTS5 (v1) → GraphEngine ABC → 10 MCP tools → FastMCP stdio server
                                     → inject CLI    → session-start.sh hook
```

---

## Quick Install

**Option A — uvx (recommended, no pip install needed):**

```bash
# UV manages an isolated env automatically on first run
uvx --from ~/Workspace/my-templates/graphbase-memories-mcp graphbase-memories-mcp

# verify CLI tools still work (uses system python3)
cd ~/Workspace/my-templates/graphbase-memories-mcp
pip install -e .
graphbase-memories inspect --project test-project   # empty is fine
graphbase-memories inject  --project test-project   # empty YAML is fine
```

**Option B — pip install (if uvx is unavailable):**

```bash
cd ~/Workspace/my-templates/graphbase-memories-mcp
pip install -e .             # or: pip install -e ".[dev]" for tests
python3 -m graphbase_memories server   # verify server starts
```

**Python requirement**: Python 3.11+.

---

## Claude Code Registration

**Preferred — uvx** (add to `.mcp.json` or `~/.claude/.mcp.json`):

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from", "/home/<you>/Workspace/my-templates/graphbase-memories-mcp",
        "graphbase-memories-mcp"
      ],
      "env": {
        "GRAPHBASE_DATA_DIR":  "~/.graphbase-memories",
        "GRAPHBASE_BACKEND":   "sqlite",
        "GRAPHBASE_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

**Alternative — pip-installed:**

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "graphbase_memories", "server"],
      "env": {
        "GRAPHBASE_DATA_DIR": "~/.graphbase-memories",
        "GRAPHBASE_BACKEND": "sqlite",
        "GRAPHBASE_LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

See `.mcp.json.example` for the copy-paste template.

---

## Tools Reference

| Tool | Phase | Description |
|---|---|---|
| `store_memory` | Write | Store a memory (session / decision / pattern / context / entity_fact) with entity links |
| `relate_memories` | Write | Create a directed edge between two memories (SUPERSEDES / RELATES_TO / LEARNED_DURING) |
| `get_memory` | Read | Retrieve a memory by ID with linked entities and outgoing edges |
| `list_memories` | Read | List memories in a project, newest first (with type filter and pagination) |
| `search_memories` | Read | FTS5 BM25 full-text search across titles, content, and tags |
| `delete_memory` | Read | Soft-delete a memory (reversible; permanent only via `purge_expired_memories`) |
| `get_blast_radius` | Analysis | Find all memories and co-occurring entities affected by a named entity |
| `get_stale_memories` | Analysis | List memories not updated in N days and flag them `is_expired=1` |
| `purge_expired_memories` | Analysis | **IRREVERSIBLE** — permanently DELETE expired memories older than N days |
| `get_context` | Context | Return a token-budgeted YAML context block (for hook injection or agent use) |

### Memory types

| Type | Use for |
|---|---|
| `session` | Coding sessions — what was worked on, outcomes |
| `decision` | Architectural or design decisions with rationale |
| `pattern` | Reusable patterns adopted by the project |
| `context` | Project-level context that doesn't fit elsewhere |
| `entity_fact` | Facts about a specific service, table, or file |

### Edge types and direction rules

| Edge type | Allowed via `relate_memories` | Allowed direction |
|---|---|---|
| `SUPERSEDES` | ✓ | newer → older (any memory type) |
| `RELATES_TO` | ✓ | any → any |
| `LEARNED_DURING` | ✓ | `{decision, pattern, context, entity_fact}` → `{session}` |
| `DEPENDS_ON` | engine only | entity → entity (e.g., service dependency graphs) |
| `IMPLEMENTS` | engine only | entity → entity (e.g., service implements interface) |

`DEPENDS_ON` and `IMPLEMENTS` are valid in the storage engine for entity-level graph edges but are not exposed via the `relate_memories` tool (which validates against the three memory-to-memory relationship rules above).

---

## Update-via-Supersession Pattern [R2]

There is no `update_memory` tool. The graph is append-only. To revise a memory:

```python
# 1. Store the updated version
new_mem = store_memory(project="my-proj", title="Auth v2", content="New approach...", type="decision")

# 2. Mark the old one as superseded
relate_memories(project="my-proj", from_id=new_mem["id"], to_id=old_id, relationship="SUPERSEDES")
```

`get_context` automatically excludes superseded memories when traversing the graph.
The old memory remains retrievable via `get_memory(memory_id, include_deleted=False)` — it is never deleted by supersession.

---

## Serena Boundary [Q1 — Parallel Operation]

graphbase-memories and Serena run **in parallel** — they own different memory types:

| Layer | Owner | What it stores |
|---|---|---|
| Symbol memory | **Serena** | Code symbols, file content, project structure |
| Project notes | **Serena** | Architecture docs, session summaries (`project/context`) |
| Episodic memory | **graphbase-memories** | Sessions, decisions, patterns, entity facts |
| Graph edges | **graphbase-memories** | SUPERSEDES / RELATES_TO / LEARNED_DURING relationships |

**Rule**: If you're storing *why* a decision was made, *what* was tried, or *what pattern* was adopted → use graphbase-memories. If you're storing notes about code structure or symbols → use Serena.

Do **not** migrate Serena memories to graphbase-memories automatically in v1 — see [Post-MVP Roadmap](#post-mvp-roadmap).

---

## Hook Integration [R4 — Timeout Protection]

Add to your `session-start.sh` (or use the pre-configured one in `claude-code-agent-workflow`):

```bash
# Inject episodic memory context at session start
# timeout 3s prevents SQLite busy_timeout (5s) from blocking session start [R4]
GRAPHBASE_PYTHON="${GRAPHBASE_PYTHON:-python3}"
MEMORIES_CONTEXT=""
if command -v "$GRAPHBASE_PYTHON" >/dev/null 2>&1; then
  MEMORIES_CONTEXT=$(
    timeout 3 "$GRAPHBASE_PYTHON" -m graphbase_memories inject \
      --project "${GCX_STATE_PROJECT_NAME:-$(basename "$PWD")}" \
      ${GCX_STATE_SERVICE:+--entity "$GCX_STATE_SERVICE"} \
      --max-tokens 400 \
      2>/dev/null
  ) || MEMORIES_CONTEXT=""
fi
```

The inject call outputs a priority-ordered YAML block (decisions → patterns → stale warnings → entities) and exits 0 silently if no memories exist yet.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `GRAPHBASE_BACKEND` | `sqlite` | Storage backend (`sqlite` only in v1) |
| `GRAPHBASE_DATA_DIR` | `~/.graphbase-memories` | Root directory for all project DBs |
| `GRAPHBASE_LOG_LEVEL` | `WARNING` | Log level for `graphbase.log` |
| `GRAPHBASE_PYTHON` | `python3` | Python binary used by hook |

---

## Data Layout

```
~/.graphbase-memories/
└── {project-slug}/
    ├── memories.db      # SQLite + FTS5 (WAL mode)
    └── graphbase.log    # Structured JSON log (RotatingFileHandler, 1MB × 3)
```

Schema: `memories`, `entities`, `relationships`, `memory_entities`, `memories_fts` (FTS5 content table).
Migration: `PRAGMA user_version` tracks schema version; `_run_migrations()` runs on every open (idempotent).

---

## CLI Commands

```bash
# MCP stdio server (default mode — used by Claude Code)
graphbase-memories server
python3 -m graphbase_memories         # same

# Inject context YAML to stdout (used by session-start.sh hook)
graphbase-memories inject --project <slug> [--entity <name>] [--max-tokens 400]

# List memories (developer inspection)
graphbase-memories inspect --project <slug> [--limit 20]
```

---

## Neo4j Backend (V2)

**Status**: Implemented. Activate with `GRAPHBASE_BACKEND=neo4j`.

Neo4jEngine uses:
- Lucene full-text index (`memory_fts`) for BM25 search — same quality as SQLite FTS5
- Cypher variable-length path queries for N-hop `get_blast_radius`
- `MERGE ... ON CREATE SET` for idempotent upserts

### Quick start with local Docker

```bash
# Start Neo4j (waits until healthy — ~20s first run)
make neo4j-up

# Run the server against Neo4j
GRAPHBASE_BACKEND=neo4j \
GRAPHBASE_NEO4J_PASSWORD=graphbase \
graphbase-memories server

# Run the Neo4j contract tests
make neo4j-test

# Stop
make neo4j-down
```

### Register Neo4j backend in `.mcp.json`

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "/path/to/graphbase-memories-mcp", "graphbase-memories-mcp"],
      "env": {
        "GRAPHBASE_BACKEND":        "neo4j",
        "GRAPHBASE_NEO4J_URI":      "bolt://localhost:7687",
        "GRAPHBASE_NEO4J_USER":     "neo4j",
        "GRAPHBASE_NEO4J_PASSWORD": "graphbase",
        "GRAPHBASE_LOG_LEVEL":      "WARNING"
      }
    }
  }
}
```

### Neo4j environment variables

| Variable | Default | Description |
|---|---|---|
| `GRAPHBASE_NEO4J_URI` | `bolt://localhost:7687` | Bolt connection URI |
| `GRAPHBASE_NEO4J_USER` | `neo4j` | Username |
| `GRAPHBASE_NEO4J_PASSWORD` | _(required)_ | Password set in `NEO4J_AUTH` |

---

## Backend Comparison

| | SQLite v1 | Neo4j v2 |
|---|---|---|
| **Search** | FTS5 BM25 | Lucene BM25 (same quality) |
| **N-hop traversal** | Recursive CTE | Cypher variable-length path |
| **Setup** | Zero deps | Docker + `pip install '.[neo4j]'` |
| **Max scale** | ~50K memories | Millions of nodes |
| **Switch trigger** | — | `search_miss_rate > 20%` in log |

---

## Post-MVP Roadmap

- **`import_from_serena`**: Migration tool to bulk-import Serena markdown memories. Deferred — type mapping is fragile, no rollback path. [R6]
- **Sentence-transformers**: `all-MiniLM-L6-v2` (22MB, CPU-only) alongside BM25 for semantic vector search.
- **HTTP/SSE transport**: FastMCP supports this natively — needed only for multi-session concurrent access.
- **PyPI publish**: Package is ready; publish to PyPI to enable `uvx graphbase-memories-mcp`.

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"
# or with Neo4j driver
pip install -e ".[dev,neo4j]"

# Run SQLite tests (no Docker needed)
make test                        # or: uv run pytest tests/ --ignore=tests/neo4j -v

# Run with coverage
make test-cov

# Run Neo4j contract tests (starts/stops Docker automatically)
make neo4j-test

# Run ALL tests (SQLite + Neo4j)
make neo4j-test-full

# Debug logging
GRAPHBASE_LOG_LEVEL=DEBUG graphbase-memories inject --project my-project
```

Tests (as of Phase 3): 91 SQLite tests passing (added 5 search contract tests), 30 Neo4j contract tests (run with `make neo4j-test`).
