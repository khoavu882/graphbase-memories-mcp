# Graphbase Memories MCP

Graph-backed persistent memory for AI coding agents, exposed as an MCP server (stdio transport).

Agents call structured tools to read and write scoped memory into a **Neo4j** graph database. Memory is organized into three scopes — `global`, `project`, and `focus` — and four artifact types: sessions, decisions, patterns, and context snippets.

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — Python package manager (replaces pip/venv)
- Neo4j 5 Community (or Enterprise) — running locally or remotely

---

## Quick Start

### 1. Start Neo4j

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Default credentials: `neo4j` / `graphbase` on `bolt://localhost:7687`.

### 2. Install

```bash
# Install uv if you don't have it yet
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (creates .venv automatically)
uv sync --group dev

# Or without dev extras
uv sync
```

### 3. Run the MCP server

```bash
graphbase serve
```

The server speaks **MCP JSON-RPC 2.0 over stdio** — connect it via your agent's `.mcp.json` (see [Connecting to Claude Code](#connecting-to-claude-code)).

---

## Configuration

All settings are read from environment variables with the `GRAPHBASE_` prefix.

| Variable | Default | Description |
|---|---|---|
| `GRAPHBASE_NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `GRAPHBASE_NEO4J_USER` | `neo4j` | Neo4j username |
| `GRAPHBASE_NEO4J_PASSWORD` | `graphbase` | Neo4j password |
| `GRAPHBASE_NEO4J_DATABASE` | `neo4j` | Neo4j database name |
| `GRAPHBASE_NEO4J_MAX_POOL_SIZE` | `10` | Connection pool size |
| `GRAPHBASE_RETRIEVAL_TIMEOUT_S` | `5.0` | Per-attempt retrieval timeout (seconds) |
| `GRAPHBASE_RETRIEVAL_MAX_RETRIES` | `1` | Max retries on timeout/transient error |
| `GRAPHBASE_WRITE_MAX_RETRIES` | `1` | Max retries on `ServiceUnavailable` |
| `GRAPHBASE_GOVERNANCE_TOKEN_TTL_S` | `60` | GovernanceToken expiry (seconds) |

Set them in your shell or in a `.env` file. Example:

```bash
export GRAPHBASE_NEO4J_URI=bolt://my-neo4j-host:7687
export GRAPHBASE_NEO4J_PASSWORD=my-secret-password
```

---

## Connecting to Claude Code

Copy `.mcp.json.example` to `.mcp.json` in your project root and adjust paths/env vars:

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "command": "uvx",
      "args": ["--python", "3.11", "--from", "git+https://github.com/khoavu882/graphbase@v1.0.0", "graphbase", "serve"],
      "env": {
        "GRAPHBASE_NEO4J_URI": "bolt://localhost:7687",
        "GRAPHBASE_NEO4J_USER": "neo4j",
        "GRAPHBASE_NEO4J_PASSWORD": "graphbase"
      }
    }
  }
}
```

After saving, restart Claude Code. The 22 MCP tools will appear in the tool list.

> **Tip**: Use `@v1.0.0` (or the latest tag) to pin to a stable release. `@main` tracks the development branch and may include unreleased changes.

---

## MCP Tools Reference

| Tool | Group | Description |
|---|---|---|
| `retrieve_context` | Retrieval | Load memory with priority merge: focus > project > global |
| `get_scope_state` | Retrieval | Resolve project/focus scope state before reads or writes |
| `memory_surface` | Retrieval | BM25 keyword surface: fast focused lookup without full context retrieval |
| `save_session` | Session | Persist a session summary (objective, actions, decisions, next steps) |
| `store_session_with_learnings` | Session | Batch save: session + related decisions + patterns in one call |
| `save_decision` | Artifact | Save an architectural or technical decision with dedup + supersession |
| `save_pattern` | Artifact | Save a repeatable workflow pattern with hash-based dedup |
| `save_context` | Artifact | Save a free-form context snippet with relevance score |
| `upsert_entity_with_deps` | Entity | Upsert a named entity fact and link related entities |
| `request_global_write_approval` | Governance | Obtain a one-time token required for global-scope writes |
| `route_analysis` | Analysis | Route a task description to sequential / debate / socratic mode |
| `run_hygiene` | Hygiene | Detect duplicates, stale decisions, obsolete patterns, entity drift |
| `get_save_status` | Hygiene | List pending or failed saves for a project |
| `memory_freshness` | Hygiene | List nodes not updated within the freshness threshold, oldest-first |
| `register_service` | Federation | Register a service into a named workspace |
| `deregister_service` | Federation | Remove a service from the registry |
| `list_active_services` | Federation | List services active within a time window |
| `search_cross_service` | Federation | Federated memory search across services |
| `link_cross_service` | Federation | Create a typed cross-service link (write) |
| `propagate_impact` | Federation | Propagate a breaking change across the graph (write) |
| `graph_health` | Federation | Get workspace health and cross-service metrics |
| `detect_conflicts` | Federation | Find contradicting cross-service links |

---

## CLI Commands

```bash
# Start the stdio MCP server (primary agent mode)
graphbase serve

# Start the HTTP devtools inspection server (human browsing)
graphbase devtools --port 8765

# Run the memory hygiene cycle and print the report as JSON
graphbase hygiene --project-id <uuid>
graphbase hygiene --scope global
```

---

## Devtools Server

The devtools server (`graphbase devtools`) exposes an HTTP API and a browser dashboard for inspecting graph memory without an agent. Open `http://localhost:8765` after starting — it redirects to the Alpine.js single-page dashboard (`/ui`) with 5 tabs: Projects, Tools, Health, Memory, and Hygiene, plus a standalone Graph canvas page (`/ui/graph.html`) showing the Workspace→Project topology.

```
GET  /events                          SSE heartbeat (real-time connectivity status)
GET  /memory                          List nodes
GET  /memory/{id}/relationships       Relationship inspector
GET  /memory/{id}                     Node detail
POST /memory/search                   CONTAINS full-text search
GET  /projects                        Projects with node counts + staleness
GET  /projects/{id}                   Single project detail
GET  /tools                           MCP tool registry (live)
GET  /tools/{name}                    Tool schema + metadata
POST /tools/{name}/invoke             Engine-direct invoke with write-confirmation gate
GET  /graph/overview                  Force-directed graph: Workspace→Project topology with staleness + federation edges
GET  /graph/stats                     Per-label node + relationship counts
GET  /graph/stats/workspace/{id}      Workspace health
GET  /graph/conflicts/{id}            CONTRADICTS conflict detection
GET  /hygiene/status                  All-project hygiene summary
POST /hygiene/run                     Run hygiene engine
MOUNT /ui                             Alpine.js dashboard (StaticFiles)
GET  /                                → redirect to /ui
```

Write tools (`propagate_impact`, `link_cross_service`, `register_service`, `deregister_service`) require `"confirm": true` in the POST body when invoked via `/tools/{name}/invoke`; without it the response is `{"status": "preview", ...}`.

---

## Memory Model

```
Scopes:   global  ← cross-project reusable knowledge
          project ← initiative or codebase specific
          focus   ← narrow runtime context within a project

Artifacts: Session     — what happened in a coding session
           Decision    — architectural / technical decisions (with supersession chain)
           Pattern     — repeatable workflows (trigger + steps)
           Context     — free-form snippets with relevance score
           EntityFact  — named entity with a fact statement

Graph edges:
  [:BELONGS_TO]    artifact → Project | GlobalScope
  [:HAS_FOCUS]     artifact → FocusArea
  [:SUPERSEDES]    Decision → older Decision  (append-only lineage)
  [:CONFLICTS_WITH] Decision ↔ Decision
  [:PRODUCED]      Session → artifact  (traceability)
  [:MERGES_INTO]   EntityFact → EntityFact  (hygiene normalization)
```

---

## Development

```bash
# Run tests (requires Neo4j running)
uv run pytest

# Lint
uv run ruff check src tests

# Format
uv run ruff format src tests
```

Tests are integration tests and require a live Neo4j instance at `bolt://localhost:7687` with credentials `neo4j` / `graphbase`.

---

## License

This repository is licensed under the MIT License. See `LICENSE` for the full text.
