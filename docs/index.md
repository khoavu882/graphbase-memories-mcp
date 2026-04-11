# Graphbase Memories MCP

**Graph-backed persistent memory for AI coding agents, exposed as an MCP server.**

Agents (Claude, Codex, Gemini, and others) call 20 structured tools to read and write scoped memory into a **Neo4j** graph database. Memory survives across sessions, accumulates decisions and patterns over time, and surfaces the most relevant context when you need it.

---

## Why graph memory?

Most agent memory is flat — a list of notes, a vector store of embeddings, or session summaries that drift away. `graphbase-memories-mcp` organizes memory as a **property graph**:

- **Scopes** (`global` / `project` / `focus`) keep cross-project knowledge separate from initiative-specific context.
- **Artifact types** (sessions, decisions, patterns, context snippets, entity facts) give structure to what agents remember.
- **Graph edges** (`[:SUPERSEDES]`, `[:CONFLICTS_WITH]`, `[:PRODUCED]`) make the lineage and relationships between memories explicit and queryable.

```mermaid
graph TD
    A["AI Agent<br/>(Claude / Codex / Gemini)"]
    B["MCP Server — FastMCP<br/>20 async tools · stdio JSON-RPC 2.0"]
    C["Business Logic Layer<br/>engines/"]
    I[("Neo4j 5<br/>Graph Store")]

    A -->|"stdio"| B
    B --> C
    C -->|"Bolt :7687"| I
```

---

## What agents can do

| Action | Tool |
|---|---|
| Load context before reasoning | `retrieve_context` |
| Check scope before reading/writing | `get_scope_state` |
| Save a session summary | `save_session` |
| Save session + decisions + patterns in one call | `store_session_with_learnings` |
| Save an architectural decision (with dedup) | `save_decision` |
| Save a repeatable workflow pattern | `save_pattern` |
| Save a free-form context snippet | `save_context` |
| Upsert a named entity and its relationships | `upsert_entity_with_deps` |
| Obtain a global-scope write token | `request_global_write_approval` |
| Route a task to the right reasoning mode | `route_analysis` |
| Run memory hygiene (detect duplicates, stale items) | `run_hygiene` |
| Check for pending or failed saves | `get_save_status` |
| Register a service into a workspace | `register_service` |
| List services active in a workspace | `list_active_services` |
| Search memory across services | `search_cross_service` |
| Create a cross-service knowledge link | `link_cross_service` |
| Propagate a breaking change across services | `propagate_impact` |
| Get workspace health metrics | `graph_health` |
| Find contradicting cross-service links | `detect_conflicts` |

---

## Requirements

- Python 3.11+
- Neo4j 5 Community (or Enterprise) — local or remote
- An MCP-compatible agent host (Claude Code, Cursor, Cline, etc.)

---

## Quick links

- [Quick Start](quickstart.md) — up and running in 3 steps
- [MCP Tools Overview](tools/index.md) — all 20 tools with call sequence
- [Memory Model](concepts/memory-model.md) — scopes, artifacts, graph edges
- [Configuration](configuration.md) — all `GRAPHBASE_*` environment variables
