# Graphbase Memories MCP

Graph-backed persistent memory for AI coding agents, exposed as an MCP server (stdio transport).

Agents call structured tools to read and write scoped memory into a **Neo4j** graph database. Memory is organized into three scopes — `global`, `project`, and `focus` — and four artifact types: sessions, decisions, patterns, and context snippets.

---

## Requirements

- Python 3.11+
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
# Development (editable)
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Or install from source without dev extras
pip install .
```

### 3. Run the MCP server

```bash
graphbase-memories-mcp serve
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
      "command": "/path/to/.venv/bin/graphbase-memories-mcp",
      "args": ["serve"],
      "env": {
        "GRAPHBASE_NEO4J_URI": "bolt://localhost:7687",
        "GRAPHBASE_NEO4J_USER": "neo4j",
        "GRAPHBASE_NEO4J_PASSWORD": "graphbase"
      }
    }
  }
}
```

After saving, restart Claude Code. The 12 memory tools will appear in the tool list.

---

## MCP Tools Reference

| Tool | Group | Description |
|---|---|---|
| `retrieve_context` | Retrieval | Load memory with priority merge: focus > project > global |
| `get_scope_state` | Retrieval | Resolve project/focus scope state before reads or writes |
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

---

## CLI Commands

```bash
# Start the stdio MCP server (primary agent mode)
graphbase-memories-mcp serve

# Start the HTTP devtools inspection server (human browsing)
graphbase-memories-mcp devtools --port 8765

# Run the memory hygiene cycle and print the report as JSON
graphbase-memories-mcp hygiene --project-id <uuid>
graphbase-memories-mcp hygiene --scope global
```

---

## Devtools Server

The devtools server (`graphbase-memories-mcp devtools`) exposes a read-only HTTP API for inspecting graph memory without an agent:

```
GET /health                     — liveness check
GET /memory?project_id=<id>     — list all memory nodes for a project
GET /memory/<node-id>           — fetch a single node
```

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
pytest

# Lint
ruff check src/

# Format
ruff format src/
```

Tests are integration tests and require a live Neo4j instance at `bolt://localhost:7687` with credentials `neo4j` / `graphbase`.

---

## License

This repository is licensed under the MIT License. See `LICENSE` for the full text.
