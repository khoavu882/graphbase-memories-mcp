# graphbase-memories — Architecture

**Status**: Phase 3 | 2026-04-05
**Source**: `~/Workspace/my-templates/graphbase-memories-mcp`
**MCP name**: `graphbase-memories`
**Transport**: stdio (local process)
**Tests**: 91 SQLite passing + 30 Neo4j contract (Docker) | Coverage: ~88%

---

## 1. Problem Statement

The current coding agent memory system (Serena MCP) stores memories as flat markdown files with a
namespace convention (`project/context`, `session/history/<ts>`, etc.). This works for simple
key-value retrieval but fails at:

| Pain Point | Concrete Symptom |
|---|---|
| No relational queries | Can't ask "which sessions worked on PaymentService?" |
| No entity disambiguation | "PaymentService" appears in 5 memories with no linking |
| No staleness model | Old decisions linger with no decay signal |
| No blast-radius | Changing a design decision: which memories reference it? |
| No semantic search | Must know exact key to retrieve a memory |
| Cross-session drift | Agent re-discovers the same patterns each session |

`graphbase-memories` solves this by replacing flat file storage with a **graph-backed memory
engine** exposed as an MCP server (stdio) with 10 focused tools.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        Claude Code Session                         │
│                                                                    │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    Hook Layer (existing)                      │  │
│  │  session-start.sh  user-prompt-submit.sh  post-edit-index.sh │  │
│  │    └── timeout 3 python3 -m graphbase_memories inject ──┘   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                              │ stdout → additionalContext          │
│  ┌───────────┐   stdio RPC   ▼                                    │
│  │  Claude   │◄────────────► graphbase-memories MCP Server        │
│  │  Agent    │               (FastMCP 3.x, Python 3.11+)          │
│  └───────────┘               │                                    │
│                              │                                    │
└──────────────────────────────┼────────────────────────────────────┘
                               │
               ┌───────────────▼──────────────┐
               │    _provider.get_engine()     │
               │  (lazy singleton per project, │
               │   double-checked lock [M1])   │
               └───────────────┬──────────────┘
                               │
               ┌───────────────▼──────────────┐
               │         GraphEngine ABC       │
               │  (interface contract — swap   │
               │   backend without API change) │
               └───────┬──────────────┬────────┘
                       │              │
            ┌──────────▼──┐    ┌──────▼──────────┐
            │  SQLiteEngine│    │  Neo4jEngine     │
            │  (v1, live)  │    │  (v2, live)      │
            │  FTS5 search │    │  Lucene FTS      │
            │  WAL mode    │    │  Cypher N-hop    │
            └─────────────┘    └──────────────────┘
                    │
         ~/.graphbase-memories/
         └── <project>/
             ├── memories.db     (SQLite + FTS5, WAL mode, ACID)
             └── graphbase.log   (JSON, RotatingFileHandler 1MB×3)
```

**Key architectural principle**: The 10 MCP tools never touch storage directly — they go through
the `GraphEngine` interface. This means the V2 Neo4j migration is a one-file swap with zero
API changes.

---

## 3. Layer Map

| Layer | Module | Responsibility |
|---|---|---|
| **CLI / Entry** | `__main__.py` | Dispatch: `server` (MCP), `inject` (hook), `inspect` (dev) |
| **MCP Server** | `server.py` | FastMCP singleton; registers all 10 tools |
| **Tools** | `tools/{write,read,analysis,context}_tools.py` | MCP wire protocol; call `_provider.get_engine()` only |
| **Provider** | `_provider.py` | Lazy engine lifecycle; backend selection; test injection |
| **Config** | `config.py` | Env-aware dataclass (backend, data_dir, log_level) |
| **Formatter** | `formatters/yaml_context.py` | **Pure function** — token-capped YAML rendering, no I/O |
| **Engine ABC** | `graph/engine.py` | Dataclasses + abstract interface contract |
| **SQLite Backend** | `graph/sqlite_engine.py` | Full v1 implementation |
| **Neo4j Backend** | `graph/neo4j_engine.py` | V2 implementation — Lucene FTS, Cypher traversal |

**Dependency graph: acyclic.** `_provider.py` uses lazy imports to avoid import-time
instantiation. The tool layer never imports any concrete engine.

---

## 4. Graph Data Model

### 4.1 Node Types

```
MemoryNode ─── fundamental unit
  id          : UUID (TEXT)
  project     : project slug (e.g. "claude-code-agent-workflow")
  type        : 'session' | 'decision' | 'pattern' | 'context' | 'entity_fact'
  title       : short label (≤ 100 chars)
  content     : markdown body
  tags        : list[str]  (stored as JSON in DB)
  created_at  : ISO-8601
  updated_at  : ISO-8601
  valid_until : ISO-8601 | None  (None = perpetual)
  is_deleted  : bool  (soft-delete — never hard-deleted by default)
  is_expired  : bool  (flag-only decay [Q4] — flagged by get_stale_memories)

EntityNode ─── named real-world object a memory references
  id          : UUID
  name        : canonical name (e.g. "PaymentService")
  type        : 'service' | 'file' | 'feature' | 'concept' | 'table' | 'topic'
  project     : project slug
  metadata    : dict  (arbitrary JSON properties)
  created_at  : ISO-8601
  UNIQUE (name, type, project)

Edge ─── directed relationship between two nodes
  id          : UUID
  from_id     : source node UUID
  from_type   : 'memory' | 'entity'  (discriminator, no FK [B1])
  to_id       : target node UUID
  to_type     : 'memory' | 'entity'  (discriminator, no FK [B1])
  type        : edge type string (see §4.2)
  properties  : dict  (arbitrary JSON)
  created_at  : ISO-8601
```

### 4.2 Edge Types

| Edge type | `relate_memories` tool | Allowed direction |
|---|---|---|
| `SUPERSEDES` | ✓ | newer → older (any memory type) |
| `RELATES_TO` | ✓ | any memory → any memory |
| `LEARNED_DURING` | ✓ | `{decision,pattern,context,entity_fact}` → `{session}` |
| `DEPENDS_ON` | engine only | entity → entity |
| `IMPLEMENTS` | engine only | entity → entity |

`DEPENDS_ON` and `IMPLEMENTS` are valid in the storage engine for entity-level graph edges
(e.g., service dependency maps) but are not exposed via the `relate_memories` tool.

### 4.3 SQLite Schema (v1)

```sql
CREATE TABLE memories (
    id          TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    type        TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]',   -- JSON array
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    valid_until TEXT,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    is_expired  INTEGER NOT NULL DEFAULT 0    -- [Q4] flag-only decay
);

CREATE TABLE entities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    project     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    UNIQUE (name, type, project)
);

-- [B1] No FK constraints. from_type/to_type discriminators allow
-- Memory→Memory, Entity→Entity, and cross-type edges in one table.
CREATE TABLE relationships (
    id          TEXT PRIMARY KEY,
    from_id     TEXT NOT NULL,
    from_type   TEXT NOT NULL,   -- 'memory' | 'entity'
    to_id       TEXT NOT NULL,
    to_type     TEXT NOT NULL,   -- 'memory' | 'entity'
    type        TEXT NOT NULL,
    properties  TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);

CREATE TABLE memory_entities (
    memory_id   TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    PRIMARY KEY (memory_id, entity_id)
);

-- FTS5: title + content + tags, sync'd via triggers
CREATE VIRTUAL TABLE memories_fts USING fts5(
    id UNINDEXED, title, content, tags,
    content='memories', content_rowid='rowid'
);

-- Sync triggers (INSERT / DELETE / UPDATE)
CREATE TRIGGER memories_ai AFTER INSERT ON memories ...
CREATE TRIGGER memories_ad AFTER DELETE ON memories ...
CREATE TRIGGER memories_au AFTER UPDATE ON memories ...

-- Indexes
CREATE INDEX idx_memories_project ON memories(project, type, is_deleted);
CREATE INDEX idx_memories_updated  ON memories(updated_at);
CREATE INDEX idx_entities_project  ON entities(project, type);
CREATE INDEX idx_rel_from          ON relationships(from_id, from_type);
CREATE INDEX idx_rel_to            ON relationships(to_id, to_type);
```

**Schema migration**: `PRAGMA user_version` tracks schema version.
`_init_db()` runs on every connection open:
- `current > SCHEMA_VERSION` → `RuntimeError` (downgrade guard) [M2]
- `current < SCHEMA_VERSION` → runs migrations `v{N} → v{N+1}` in order
- `current == SCHEMA_VERSION` → no-op

---

## 5. MCP Tool API (10 tools — as implemented)

### 5.1 Write Tools

```python
store_memory(
    project:     str,
    title:       str,
    content:     str,
    type:        str = "context",      # 'session'|'decision'|'pattern'|'context'|'entity_fact'
    entities:    list[str] = [],       # entity names — auto-created if missing [R8]
    tags:        list[str] = [],
    valid_until: str | None = None,    # ISO-8601 expiry
) -> dict   # {id, title, type, created_at}

relate_memories(
    project:      str,
    from_id:      str,                 # memory UUID
    to_id:        str,                 # memory UUID
    relationship: str,                 # SUPERSEDES | RELATES_TO | LEARNED_DURING
) -> dict   # {id, from_id, to_id, type, created_at}
```

### 5.2 Read Tools

```python
get_memory(
    project:         str,
    memory_id:       str,
    include_deleted: bool = False,     # [R3] soft-deleted excluded by default
) -> dict | None   # full node + {entities: [...], edges: [...]}

list_memories(
    project:         str,
    type:            str | None = None,
    limit:           int = 20,         # max 100
    offset:          int = 0,
    include_deleted: bool = False,     # [R3]
) -> list[dict]   # [{id, title, type, updated_at, tags, is_expired}]

search_memories(
    query:   str,                      # FTS5 BM25; supports phrases, prefix*, OR
    project: str | None = None,        # None = search all loaded engines
    type:    str | None = None,
    limit:   int = 10,                 # max 50
) -> list[dict]   # [{id, title, type, project, score, snippet, updated_at}]

delete_memory(
    project:   str,
    memory_id: str,
) -> dict   # {memory_id, deleted: bool, permanent: False}
            # Soft-delete only. Permanent removal: purge_expired_memories().
```

### 5.3 Analysis Tools

```python
get_blast_radius(
    entity_name: str,
    project:     str,
    depth:       int = 2,
) -> dict   # {entity_name, project, depth, total_references,
            #  memories: [{id,title,type,updated_at,tags,is_expired}],
            #  related_entities: [{id,name,type}]}
            # [R1] typed BlastRadiusResult dataclass converted to dict

get_stale_memories(
    project:  str,
    age_days: int = 30,
) -> list[dict]   # [{id,title,type,updated_at,tags,is_expired:True}]
                  # Side effect: flags each stale memory is_expired=1 [Q4]

purge_expired_memories(
    project:        str,
    older_than_days: int = 90,
) -> dict   # {project, purged_count, older_than_days}
            # IRREVERSIBLE — permanently DELETE is_expired=1 memories [Q4]
```

### 5.4 Context Tool

```python
get_context(
    project:    str,
    entity:     str | None = None,   # focus on a specific entity
    max_tokens: int = 500,           # hard token cap [Q3]
) -> str   # compact YAML block (see §6 for format)
```

### 5.5 Tool Name Mapping (as seen in Claude Code)

| Implemented Tool | Claude Code name |
|---|---|
| `store_memory` | `mcp__graphbase-memories__store_memory` |
| `relate_memories` | `mcp__graphbase-memories__relate_memories` |
| `get_memory` | `mcp__graphbase-memories__get_memory` |
| `list_memories` | `mcp__graphbase-memories__list_memories` |
| `search_memories` | `mcp__graphbase-memories__search_memories` |
| `delete_memory` | `mcp__graphbase-memories__delete_memory` |
| `get_blast_radius` | `mcp__graphbase-memories__get_blast_radius` |
| `get_stale_memories` | `mcp__graphbase-memories__get_stale_memories` |
| `purge_expired_memories` | `mcp__graphbase-memories__purge_expired_memories` |
| `get_context` | `mcp__graphbase-memories__get_context` |

**Not implemented**: `import_from_serena` was deferred to post-MVP (see §11).

---

## 6. Context Injection Format

`get_context` / `inject` CLI output. Priority-ordered, token-capped YAML:

```yaml
decisions:
  - title: "Tier A always loaded, Tier B gated at 72h"
    content: "Load project/context unconditionally; session/history…"
  - title: "_GCX_MEM_* constants = single source of truth"
    content: "Constants defined in graph-context.sh _init block…"

patterns:
  - title: "Serena-only mode when no _index/ found"
    content: "Do not abort on missing _index/; degrade to serena-only…"

stale_warnings:
  - 'project/architecture — not yet written'  # expired

related_entities:
  - name: 'do:save'
    type: 'feature'
  - name: 'graph-context.sh'
    type: 'file'

recent_sessions:
  - 'Session 2026-04-04: implemented Phase 4-5'
```

Priority order (P1 → P5) with per-section budget gates:
- P1 `decisions` — always included if they fit
- P2 `patterns` — if budget > 80 tokens
- P3 `stale_warnings` — if budget > 60 tokens
- P4 `related_entities` — if budget > 40 tokens (entity filter only)
- P5 `recent_sessions` — filler if budget > 40 tokens

Token counting: `len(text) // 4` (GPT-3.5 heuristic, ±15%).

---

## 7. Project File Structure

```
graphbase-memories-mcp/
├── src/
│   └── graphbase_memories/
│       ├── __init__.py
│       ├── __main__.py            # CLI entry: server | inject | inspect
│       ├── server.py              # FastMCP singleton + 4 register_*_tools() calls
│       ├── config.py              # Config dataclass (backend, data_dir, log_level)
│       ├── _provider.py           # Lazy engine per project; double-checked lock [M1]
│       ├── graph/
│       │   ├── __init__.py
│       │   ├── engine.py          # GraphEngine ABC + dataclasses
│       │   ├── sqlite_engine.py   # v1: SQLite + FTS5 + WAL + JSON logging
│       │   └── neo4j_engine.py    # v2 — Lucene FTS, Cypher N-hop, MERGE upserts
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── write_tools.py     # store_memory, relate_memories
│       │   ├── read_tools.py      # get_memory, list_memories, search_memories, delete_memory
│       │   ├── analysis_tools.py  # get_blast_radius, get_stale_memories, purge_expired_memories
│       │   └── context_tools.py   # get_context
│       └── formatters/
│           ├── __init__.py
│           └── yaml_context.py    # Pure function: render_context() token-budgeted YAML
├── tests/
│   ├── conftest.py                # engine + mcp fixtures; parse() helper
│   ├── test_write_tools.py        # store_memory, relate_memories (11 tests)
│   ├── test_read_tools.py         # get_memory, list_memories, search, delete (16 tests)
│   ├── test_analysis_tools.py     # blast radius, stale, purge (9 tests)
│   ├── test_context_tools.py      # get_context (9 tests)
│   ├── test_cli.py                # inject + inspect subcommands (6 tests)
│   └── test_engine_schema.py      # WAL, schema version, migrations, FTS5, edges (10 tests)
├── claudedocs/
│   ├── graphbase_memories_agent_mcp_research.md
│   └── workflow_graphbase_memories.md
├── ARCHITECTURE.md                (this file)
├── README.md
├── pyproject.toml                 # requires-python ≥3.11; fastmcp≥2.0; pytest-asyncio
└── .mcp.json.example
```

---

## 8. GraphEngine ABC (actual interface)

```python
# graph/engine.py

VALID_MEMORY_TYPES = frozenset({"session","decision","pattern","context","entity_fact"})
VALID_ENTITY_TYPES = frozenset({"service","file","feature","concept","table","topic"})
VALID_EDGE_TYPES   = frozenset({"SUPERSEDES","RELATES_TO","LEARNED_DURING","DEPENDS_ON","IMPLEMENTS"})

class GraphEngine(ABC):
    # Write
    @abstractmethod
    def store_memory_with_entities(self, memory: MemoryNode, entity_names: list[str]) -> MemoryNode: ...
    @abstractmethod
    def store_edge(self, edge: Edge) -> Edge: ...
    @abstractmethod
    def soft_delete(self, memory_id: str) -> bool: ...
    @abstractmethod
    def flag_expired(self, memory_id: str) -> None: ...
    @abstractmethod
    def purge_expired(self, project: str, older_than_days: int) -> int: ...

    # Read
    @abstractmethod
    def get_memory(self, memory_id: str, include_deleted: bool = False) -> MemoryNode | None: ...
    @abstractmethod
    def list_memories(self, project: str, type: str | None, limit: int, offset: int,
                      include_deleted: bool = False) -> list[MemoryNode]: ...
    @abstractmethod
    def search_memories(self, query: str, project: str | None, type: str | None,
                        limit: int) -> list[tuple[MemoryNode, float]]: ...
    @abstractmethod
    def get_memories_for_entity(self, entity_name: str, project: str) -> list[MemoryNode]: ...
    @abstractmethod
    def get_entities_for_memory(self, memory_id: str) -> list[EntityNode]: ...
    @abstractmethod
    def get_edges_for_memory(self, memory_id: str) -> list[Edge]: ...
    @abstractmethod
    def get_related_entities(self, project: str, entity_name: str | None = None) -> list[EntityNode]: ...

    # Analysis
    @abstractmethod
    def get_blast_radius(self, entity_name: str, project: str, depth: int) -> BlastRadiusResult: ...
    @abstractmethod
    def get_stale_memories(self, project: str, age_days: int) -> list[MemoryNode]: ...

    # Introspection
    @abstractmethod
    def schema_version(self) -> int: ...
    @abstractmethod
    def journal_mode(self) -> str: ...

    # Test helper (non-abstract, no-op base)
    def _backdate(self, memory_id: str, days: int) -> None: ...
```

**Adding a new backend** (e.g., DuckDB): implement the 20 abstract methods above in a new
`graph/duckdb_engine.py` file, then add 3 lines to `_provider.get_engine()`. Zero tool changes.

---

## 9. Claude Code Integration

### 9.1 MCP Registration (`.mcp.json`)

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

### 9.2 Hook Integration (session-start.sh)

```bash
# Inject episodic context at session start [R4: timeout 3s]
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

The `inject` subcommand instantiates SQLiteEngine directly (bypasses `_provider.get_engine()`)
to avoid importing the full MCP server stack. Always uses SQLite regardless of
`GRAPHBASE_BACKEND`.

### 9.3 Settings.json env block

```json
{
  "env": {
    "GRAPHBASE_BACKEND":   "sqlite",
    "GRAPHBASE_DATA_DIR":  "~/.graphbase-memories",
    "GRAPHBASE_LOG_LEVEL": "WARNING",
    "GRAPHBASE_PYTHON":    "python3"
  }
}
```

---

## 10. Key Design Decisions (Resolved)

| # | Decision | Resolution |
|---|---|---|
| Q1 | Serena memories: replace or parallel? | **Parallel** — graphbase-memories owns episodic memory (sessions, decisions, patterns); Serena owns symbol and project notes |
| Q2 | `import_from_serena` in v1 or post-MVP? | **Post-MVP** — type mapping is fragile; manual `store_memory()` is the v1 path [R6] |
| Q3 | Token budget: hard-cap or best-effort? | **Hard cap** (`len(text) // 4`; ±15%) — hook injection must not overrun context window |
| Q4 | `valid_until` decay: auto-delete or flag-only? | **Flag-only** (`is_expired=1`) — `get_stale_memories` flags, `purge_expired_memories` deletes. Two-step prevents silent data loss |
| M1 | Thread safety on `get_engine()` | **Double-checked locking** (`threading.Lock`) — serialises lazy init; fast path skips lock after first access |
| M2 | Schema downgrade handling | **RuntimeError** when `current > SCHEMA_VERSION` — clear error instead of silent mis-match |
| B1 | Polymorphic edges (memory↔entity) | **No FK constraints** — `from_type`/`to_type` discriminators; all edges in one `relationships` table |
| B2 | CLI hook safety | **Direct SQLiteEngine** in `inject`/`inspect` — avoids MCP server import overhead; always exits 0 |
| R1 | `get_blast_radius` return type | **Typed `BlastRadiusResult` dataclass** — converted to dict at the tool layer only |
| R4 | Hook timeout | **`timeout 3`** in shell wraps inject call; SQLite `busy_timeout=5000ms` would otherwise block session start |
| A-6 | Neo4j search strategy | **Lucene FTS index** (`memory_fts` on title+content+tags_json) — BM25 scoring, same quality as SQLite FTS5. Falls back to CONTAINS on malformed Lucene syntax |
| C-1 | Neo4j constraints init | **Each DDL in its own `execute_write` call** — lambda capture issue in tuple form caused only first stmt to run |

---

## 11. Backend Migration Path (SQLite → Neo4j)

```
v1: GRAPHBASE_BACKEND=sqlite   → SQLiteEngine   (MVP, stdlib only, FTS5)
v2: GRAPHBASE_BACKEND=neo4j    → Neo4jEngine    (local Docker, Cypher traversal)
```

**V2 trigger**: `search_miss_rate > 20%` in `graphbase.log` OR graph exceeds 50K memory nodes.

Neo4j V2 requirements:
- `neo4j:community` Docker image
- Python `neo4j` driver
- Same `GraphEngine` ABC — the tool layer is unchanged
- Cypher replaces SQLite recursive CTEs for N-hop traversal

---

## 12. Performance Targets

| Operation | SQLite v1 | Neo4j v2 |
|---|---|---|
| `store_memory` | < 10ms | < 20ms |
| `get_memory` | < 5ms | < 10ms |
| `search_memories` (FTS5) | < 50ms | < 100ms (vector) |
| `get_blast_radius` (depth 2) | < 100ms | < 50ms (Cypher) |
| `get_context` (500 tokens) | < 80ms | < 60ms |
| `list_memories` (20 items) | < 10ms | < 15ms |

*All targets measured on graphs < 50K memory nodes.*

---

## 13. Non-Goals (v1)

- **No vector/semantic embeddings** — FTS5 BM25 is sufficient for local-first.
- **No multi-user / auth** — local process, single user.
- **No REST/HTTP transport** — stdio only. FastMCP supports SSE natively for v2.
- **No UI/dashboard** — CLI inspection via `python3 -m graphbase_memories inspect`.
- **No auto-indexing of codebase** — `Entity` is for manually linked concepts only.
- **No `import_from_serena`** — manual migration via `store_memory()` is the v1 path.

---

## 14. Post-MVP Roadmap

- **`import_from_serena` [R6]**: Bulk-import Serena markdown memories. Deferred due to fragile
  type-mapping (`project/context` → which `MemoryNode.type`?) and no rollback path.
- **Neo4jEngine**: V2 backend. Implemented at `graph/neo4j_engine.py`. Activate via
  `GRAPHBASE_BACKEND=neo4j`. Requires Docker — see `make neo4j-up`.
- **Sentence-transformers**: `all-MiniLM-L6-v2` (22MB, CPU) for semantic search alongside FTS5.
- **HTTP/SSE transport**: FastMCP supports this natively — only needed for multi-session
  concurrent access (e.g., shared team memory server).
