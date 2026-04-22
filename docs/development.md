# Development Guide

---

## Prerequisites

- Python 3.11+
- Docker (for Neo4j)
- `git`

---

## Setup

```bash
# 1. Clone
git clone https://github.com/khoavu882/graphbase-memories-mcp.git
cd graphbase-memories-mcp

# 2. Install dependencies (uv respects the lockfile)
uv sync --group dev

# Or with pip in a manual virtual environment
# python3 -m venv .venv && source .venv/bin/activate && pip install -e .
# pip install ruff pytest pytest-asyncio

# 3. Start Neo4j
docker compose -f docker-compose.neo4j.yml up -d

# 4. Verify Neo4j is healthy
docker compose -f docker-compose.neo4j.yml ps
# Expected: State = Up (healthy)
```

---

## Running tests

Tests are **integration tests** — they require a live Neo4j instance.

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_engines.py

# Run a specific test
uv run pytest tests/test_topology.py::test_upsert_service_creates_dual_label_node
```

!!! warning "Neo4j must be running"
    Tests connect to `bolt://localhost:7687` with credentials `neo4j` / `graphbase`.
    They will fail with a connection error if Neo4j is not running.

Pytest configuration lives in `pyproject.toml`. Async tests use `pytest-asyncio`.

---

## Linting and formatting

```bash
# Check for linting issues
ruff check src/ tests/

# Auto-fix fixable issues
ruff check --fix src/ tests/

# Format code
ruff format src/ tests/

# Check format without modifying
ruff format --check src/ tests/
```

Ruff is configured in `pyproject.toml`. Key rules enabled: `E`, `W`, `F`, `I` (isort), `N` (pep8-naming), `UP` (pyupgrade), `ASYNC`, `B` (bugbear), `SIM`, `RUF`.

---

## Project structure

```
src/graphbase_memories/
├── main.py               CLI (typer): serve | devtools | hygiene | surface
├── config.py             pydantic-settings: GRAPHBASE_* env vars
├── mcp/
│   ├── server.py         FastMCP app + tool/prompt/resource registration
│   ├── tools/            Tool handlers (one file per group)
│   ├── prompts.py        MCP prompt templates
│   └── resources.py      MCP resource handlers
├── engines/              Business logic engines
├── graph/
│   ├── driver.py         AsyncGraphDatabase setup + lifespan context manager
│   ├── models.py         Node dataclasses
│   ├── queries/          .cypher files (schema, retrieval, write, dedup, hygiene, topology, federation, impact, surface)
│   └── repositories/     One repo class per node type
└── devtools/             FastAPI HTTP inspection server + Alpine.js UI
    ├── server.py         FastAPI app, lifespan, router mounting (pool=2)
    ├── routes/           Route modules for graph, projects, tools, hygiene, memory, events, and health
    │   ├── events.py     SSE heartbeat stream
    │   ├── memory.py     Memory node list/get/search/relationships
    │   ├── projects.py   Project registry with staleness + node counts
    │   ├── tools.py      MCP tool registry + engine-direct invocation
    │   ├── health.py     Graph stats, workspace health, conflicts
    │   └── hygiene.py    Hygiene status + run control
    └── ui/               Alpine.js single-page dashboard
        ├── index.html    Sidebar-driven dashboard shell
        ├── graph.html    Standalone graph overview canvas
        └── static/       CSS, Alpine helpers, stores, graph renderer, inspector
```

---

## Key patterns

### FastMCP lifespan

The Neo4j `AsyncDriver` is created in a FastMCP lifespan context manager and injected into tool
handlers via `ctx.lifespan_context["driver"]`:

```python
@asynccontextmanager
async def neo4j_lifespan(server):
    driver = AsyncGraphDatabase.driver(...)
    await driver.verify_connectivity()
    async with driver.session() as s:
        await s.run(SCHEMA_DDL)
    yield {"driver": driver}
    await driver.close()

mcp = FastMCP("graphbase-memories", lifespan=neo4j_lifespan)
```

### Tool handler signature

All tool handlers receive `ctx: Context` as the **first parameter** (FastMCP requirement):

```python
@mcp.tool()
async def retrieve_context(
    ctx: Context,
    project_id: str,
    scope: MemoryScope,
    ...
) -> ContextBundle:
    driver = ctx.lifespan_context["driver"]
    ...
```

### Cypher file loading

All `.cypher` files are loaded at import time via `graph/driver.py`. If a file is missing, the
server fails fast before accepting any connections:

```python
SCHEMA_DDL = _load_cypher("schema")   # raises FileNotFoundError if missing
```

---

## Devtools server

The devtools server provides a human-readable HTTP interface for inspecting graph state without an agent. Start it with:

```bash
graphbase devtools --port 8765
# Console prints: DevTools write token: <token>
# Open http://localhost:8765 — redirects to /ui (Alpine.js dashboard)
```

Current UI layout:

- `/ui` loads the main dashboard with sidebar navigation for Projects, Memory, Tools, and Operations.
- `/ui/graph.html` loads the standalone graph canvas for workspace and project topology inspection.
- The header `Write Token` field stores the startup token in browser `localStorage` under `gb-devtools-token`.
- The Memory view supports infinite scroll, date/title sorting, project and label filters, keyboard navigation, and a live Inspector Drawer.
- The Inspector Drawer supports inline edit, delete, JSON copy/download, and deep-links into the graph canvas for graph-rendered node types.
- The Operations view consolidates health, hygiene, conflict, and orphan-repair workflows that were previously split across separate tabs.

Architecture notes:

- Connection pool capped at 2 for devtools. The MCP server default pool is 10, for a combined default ceiling of 12 Bolt connections.
- All route handlers call engine functions directly with the devtools driver — no FastMCP Context needed.
- The server generates a random write token at startup and prints it to stdout once connectivity succeeds.
- Devtools write routes require the `X-Devtools-Token` header to match the startup token, including memory CRUD, bulk delete, hygiene runs, orphan repair, and write-capable tool invocation.
- Write tools (`propagate_impact`, `link_cross_service`, `register_federated_service`) also require `confirm: true` in the invoke body; without it, the response is `{"status": "preview", ...}`.
- The SSE `/events` endpoint emits a `heartbeat` event every 5 seconds with Neo4j connectivity status.

---

## Adding a new tool

1. Add the handler to the appropriate file in `mcp/tools/`
2. Add input/output schemas to `mcp/schemas/` if needed
3. Register any new Cypher queries in `graph/queries/`
4. Add a repository method if the tool needs a new graph operation
5. Write an integration test in `tests/`

---

## Building the documentation locally

```bash
uv sync --group docs
uv run mkdocs serve
# Open http://127.0.0.1:8000
```

Changes to `docs/` are hot-reloaded. Edit `mkdocs.yml` to adjust navigation or theme settings.
