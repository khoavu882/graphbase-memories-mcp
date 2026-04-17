# Graphbase Memories MCP

Graph-backed persistent memory for AI coding agents, exposed as an MCP server (stdio transport).

Agents call structured tools to read and write scoped memory into a **Neo4j** graph database. Memory is organized into three scopes — `global`, `project`, and `focus` — and five artifact types: sessions, decisions, patterns, context snippets, and entity facts.

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
| `GRAPHBASE_RETRIEVAL_FOCUS_LIMIT` | `10` | Max focus-scope results per retrieval |
| `GRAPHBASE_RETRIEVAL_PROJECT_LIMIT` | `20` | Max project-scope results per retrieval |
| `GRAPHBASE_RETRIEVAL_GLOBAL_LIMIT` | `5` | Max global-scope results per retrieval |
| `GRAPHBASE_WRITE_MAX_RETRIES` | `1` | Max retries on `ServiceUnavailable` |
| `GRAPHBASE_GOVERNANCE_TOKEN_TTL_S` | `60` | GovernanceToken expiry (seconds) |
| `GRAPHBASE_FEDERATION_ACTIVE_WINDOW_MINUTES` | `60` | Service liveness window for federation |
| `GRAPHBASE_FEDERATION_MAX_RESULTS` | `100` | Max cross-service search results |
| `GRAPHBASE_IMPACT_MAX_DEPTH` | `3` | Max BFS depth for impact propagation |
| `GRAPHBASE_WORKSPACE_ENFORCE_ISOLATION` | `true` | Enforce workspace isolation boundaries |
| `GRAPHBASE_FTS_ENABLED` | `true` | Enable BM25 full-text search indexes |
| `GRAPHBASE_FTS_LIMIT` | `20` | BM25 candidates per full-text index |
| `GRAPHBASE_RRF_K` | `60` | RRF damping constant for hybrid search |
| `GRAPHBASE_FRESHNESS_RECENT_DAYS` | `7` | Days threshold for "recent" freshness label |
| `GRAPHBASE_FRESHNESS_STALE_DAYS` | `30` | Days threshold for "stale" freshness label |

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
      "args": ["--python", "3.11", "--from", "git+https://github.com/khoavu882/graphbase@v1.5.0", "graphbase", "serve"],
      "env": {
        "GRAPHBASE_NEO4J_URI": "bolt://localhost:7687",
        "GRAPHBASE_NEO4J_USER": "neo4j",
        "GRAPHBASE_NEO4J_PASSWORD": "graphbase"
      }
    }
  }
}
```

After saving, restart Claude Code. The 21 MCP tools will appear in the tool list.

> **Tip**: Use `@v1.5.0` (or the latest tag) to pin to a stable release. `@main` tracks the development branch and may include unreleased changes.

---

## MCP Tools Reference

| Tool | Group | Description |
|---|---|---|
| `retrieve_context` | Retrieval | Load memory with priority merge: focus > project > global; supports BM25 keyword fusion via RRF |
| `memory_surface` | Retrieval | BM25 keyword surface: fast focused lookup without full context retrieval |
| `store_session_with_learnings` | Session | Batch save: session + related decisions + patterns in one call; pass `decisions=[]` for session-only |
| `save_decision` | Artifact | Save an architectural or technical decision with dedup + supersession; requires governance token for `scope=global` |
| `save_pattern` | Artifact | Save a repeatable workflow pattern with hash-based dedup |
| `save_context` | Artifact | Save a free-form context snippet with relevance score |
| `upsert_entity_with_deps` | Entity | Upsert a named entity fact and link related entities with typed relationships |
| `request_global_write_approval` | Governance | Obtain a one-time token required for global-scope writes |
| `route_analysis` | Analysis | Route a task description to sequential / debate / socratic mode |
| `run_hygiene` | Hygiene | Detect duplicates, stale decisions, obsolete patterns, entity drift; pass `check_pending_only=True` to list pending/failed saves |
| `register_federated_service` | Federation | Register (or deactivate via `active=False`) a service in a named workspace |
| `list_active_services` | Federation | List services active within a time window |
| `search_cross_service` | Federation | Federated memory search across services in a workspace |
| `link_cross_service` | Federation | Create a typed cross-service link between entities in different services |
| `propagate_impact` | Federation | BFS impact propagation across CROSS_SERVICE_LINK edges with risk scoring |
| `graph_health` | Federation | Workspace health metrics; `include_conflicts=True` adds CONTRADICTS conflict detection |
| `register_service` | Topology | Register or update a `:Project:Service` node in the topology graph |
| `link_topology_nodes` | Topology | Create a typed relationship between any two topology nodes (Service, DataSource, MessageQueue, Feature, BoundedContext) |
| `batch_upsert_shared_infrastructure` | Topology | Upsert multiple shared infrastructure nodes in one operation; requires governance token for N>1 |
| `get_service_dependencies` | Topology | Traverse the service dependency graph upstream, downstream, or both directions |
| `get_feature_workflow` | Topology | Return all services involved in a feature, ordered by workflow step |

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

Write tools (`propagate_impact`, `link_cross_service`, `register_federated_service`) require `"confirm": true` in the POST body when invoked via `/tools/{name}/invoke`; without it the response is `{"status": "preview", ...}`.

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

Topology:  Service         — a deployed service (:Project:Service dual-label)
           DataSource      — database, cache, or storage node
           MessageQueue    — event bus or queue node
           Feature         — cross-service feature workflow anchor
           BoundedContext  — domain boundary grouping services

Graph edges (memory):
  [:BELONGS_TO]    artifact → Project | GlobalScope
  [:HAS_FOCUS]     artifact → FocusArea
  [:SUPERSEDES]    Decision → older Decision  (append-only lineage)
  [:CONFLICTS_WITH] Decision ↔ Decision
  [:PRODUCED]      Session → artifact  (traceability)
  [:MERGES_INTO]   EntityFact → EntityFact  (hygiene normalization)

Graph edges (topology):
  [:CALLS_DOWNSTREAM] / [:CALLS_UPSTREAM]   Service → Service
  [:READS_FROM] / [:WRITES_TO] / [:READS_WRITES]  Service → DataSource
  [:PUBLISHES_TO] / [:SUBSCRIBES_TO]        Service → MessageQueue
  [:INVOLVES]                                Feature → Service  (step_order + role)
  [:MEMBER_OF_CONTEXT]                       Service → BoundedContext
  [:CROSS_SERVICE_LINK]                      entity → entity  (cross-workspace)
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