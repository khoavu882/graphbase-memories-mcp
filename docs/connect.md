# Connect to Your Agent

`graphbase` uses the **MCP stdio transport** — the server reads JSON-RPC 2.0 from stdin and writes responses to stdout. Any MCP-compatible agent host can connect to it.

---

## Claude Code

Copy `.mcp.json.example` to `.mcp.json` in your project root:

```bash
cp .mcp.json.example .mcp.json
```

Edit the file with the absolute path to your installed binary:

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "command": "/absolute/path/to/.venv/bin/graphbase",
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

Restart Claude Code. The 21 `graphbase-memories` tools will appear in the tool panel.

!!! tip "Find your binary path"
    ```bash
    which graphbase
    # or, if using a project-local venv:
    echo "$(pwd)/.venv/bin/graphbase"
    ```

---

## Other MCP hosts (Cursor, Cline, Continue, etc.)

Any host that supports MCP stdio servers accepts the same configuration shape. Use the `command` + `args` + `env` pattern from the Claude Code example above, adjusted for your host's config format.

---

## Global install (all projects)

To make the server available across all projects, install it globally and configure it in your user-level MCP config (`~/.claude/mcp.json` for Claude Code):

```bash
pip install graphbase-memories
```

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "command": "graphbase",
      "args": ["serve"],
      "env": {
        "GRAPHBASE_NEO4J_PASSWORD": "graphbase"
      }
    }
  }
}
```

---

## Verify connection

After connecting, call `retrieve_context` with a test project ID to confirm the server is reachable:

```
retrieve_context(project_id="test", scope="project")
```

Expected response:
```json
{
  "items": [],
  "retrieval_status": "empty",
  "scope_state": "uncertain",
  "conflicts_found": false,
  "hygiene_due": false
}
```

`empty` with `scope_state: "uncertain"` means the server is reachable and no project node exists yet — that is correct and expected on the first call.
See [Scope Resolution](concepts/scope-resolution.md) for how to create a project and move to `resolved`.

---

## Devtools server

For human inspection of memory (not agent use), start the HTTP server:

```bash
graphbase devtools --port 8765
```

Endpoints:

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check and Neo4j connectivity status |
| `GET /projects` | List all registered projects with staleness and node counts |
| `GET /memory?project_id=<id>` | List all memory nodes for a project |
| `GET /memory/<node-id>` | Fetch a single node by ID |
| `GET /memory/<node-id>/relationships` | Fetch all graph edges for a node |
| `GET /memory/search?q=<query>&project_id=<id>` | Full-text keyword search across memory nodes |
| `GET /tools` | List all registered MCP tools |
| `POST /tools/<name>/invoke` | Invoke a tool directly (add `confirm: true` for write tools) |
| `GET /workspace/health?workspace_id=<id>` | Workspace health metrics across all services |
| `GET /workspace/conflicts?workspace_id=<id>` | List cross-service CONTRADICTS links |
| `GET /hygiene/status?project_id=<id>` | Current hygiene status for a project |
| `POST /hygiene/run` | Trigger a hygiene scan and return the `HygieneReport` |
| `GET /events` | SSE stream — emits `heartbeat` every 5 s with Neo4j connectivity |

!!! note "Write tool confirmation"
    Tools that mutate graph state (`propagate_impact`, `link_cross_service`,
    `register_federated_service`) require `{ "confirm": true }` in the POST body. Without it, the
    response is `{ "status": "preview", ... }` — a dry-run showing what would change.

See [Development Guide](development.md) for full architecture notes on the devtools server.
