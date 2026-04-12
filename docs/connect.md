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

Restart Claude Code. The 12 `graphbase-memories` tools will appear in the tool panel.

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

After connecting, call `get_scope_state` with no arguments to confirm the server is reachable:

```
get_scope_state()
```

Expected response:
```json
{
  "scope_state": "unresolved",
  "project_exists": false
}
```

`unresolved` means no `project_id` was provided — that is correct and expected on the first call.
See [Scope Resolution](concepts/scope-resolution.md) for how to move from `unresolved` to `resolved`.

---

## Devtools server

For human inspection of memory (not agent use), start the HTTP server:

```bash
graphbase devtools --port 8765
```

Endpoints:

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /memory?project_id=<id>` | List all memory nodes for a project |
| `GET /memory/<node-id>` | Fetch a single node by ID |
