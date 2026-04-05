# graphbase-memories

**Graph-backed episodic memory for coding agents — delivered as an MCP server.**

graphbase-memories stores your coding sessions, architectural decisions, and reusable patterns as a knowledge graph. At the start of each Claude Code session, a token-budgeted YAML summary is injected automatically via a hook, giving your agent continuous project context without manual copy-paste.

## Why a graph?

Flat lists of notes age out and lose context. A graph lets you:

- **Link decisions to the memories that motivated them** (SUPERSEDES, RELATES_TO)
- **Track which entities are most referenced** — identify hot-spots across sessions
- **Query blast radius** before refactoring a service or database table

## Key features

| Feature | Detail |
|---|---|
| MCP stdio server | Works with Claude Code, Cursor, and any MCP-compatible agent |
| FTS5 full-text search | BM25-ranked search across titles, content, and tags |
| Append-only graph | No `update_memory` — revisions use SUPERSEDES edges |
| Zero-dependency default | SQLite backend ships with no extra installs |
| Plugin backends | Drop in Neo4j or write your own via `GraphEngine` ABC |
| Token-budgeted injection | YAML context trimmed to fit your session budget |
| SSE transport | Optional HTTP SSE mode for multi-client setups |

## Quick install

```bash
pip install graphbase-memories-mcp
graphbase-memories setup
```

See [Quick Start](quickstart.md) for the full setup walkthrough.
