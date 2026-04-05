# CLI Reference

All subcommands are available via the `graphbase-memories` script (installed by pip) or `python -m graphbase_memories`.

## server

Run the MCP server.

```bash
graphbase-memories server [--transport stdio|sse] [--host HOST] [--port PORT] [--devtools] [--devtools-project SLUG] [--devtools-host HOST] [--devtools-port PORT] [--open-browser]
```

| Option | Default | Description |
|---|---|---|
| `--transport` | `stdio` | Transport protocol: `stdio` or `sse` |
| `--host` | `127.0.0.1` | Bind host (SSE only) |
| `--port` | `8765` | Port (SSE only) |
| `--devtools` | `False` | Start the DevTools sidecar alongside the MCP server |
| `--devtools-project` | `None` | Explicit project slug for the DevTools sidecar |
| `--devtools-host` | `127.0.0.1` | DevTools bind host |
| `--devtools-port` | `3001` | DevTools port |
| `--open-browser` | `False` | Open the DevTools UI in a browser when DevTools is enabled |

**stdio** is the default and works with Claude Code out of the box.

When `--devtools` is enabled in `stdio` mode, the DevTools sidecar logs to `stderr` so MCP `stdout` remains clean.

**SSE** starts a persistent HTTP server — useful for multi-client setups or when you want to keep the server running across sessions:
```bash
graphbase-memories server --transport sse --port 8765
```

Optional sidecar examples:

```bash
graphbase-memories server --devtools --devtools-project my-project
graphbase-memories server --transport sse --devtools --devtools-project my-project --open-browser
```

## inject

Output a token-budgeted YAML context block to stdout. Used by the hook script.

```bash
graphbase-memories inject --project SLUG [--entity NAME] [--max-tokens N]
```

| Option | Default | Description |
|---|---|---|
| `--project` | _(required)_ | Project slug |
| `--entity` | `None` | Focus on memories referencing this entity |
| `--max-tokens` | `500` | Token budget for the YAML output |

Never raises — exits 0 with empty output if the project has no memories yet.

## inspect

List memories for a project (developer inspection).

```bash
graphbase-memories inspect --project SLUG [--limit N]
```

| Option | Default | Description |
|---|---|---|
| `--project` | _(required)_ | Project slug |
| `--limit` | `20` | Max memories to show |

Output format: `[type        ] title  (id_prefix…)  [EXPIRED]  tags=[...]`

## doctor

Health check: Python version, fastmcp, data directory, WAL mode, schema version, FTS5, hook script.

```bash
graphbase-memories doctor [--project SLUG]
```

| Option | Default | Description |
|---|---|---|
| `--project` | `None` | If set, adds per-project checks (WAL, schema, FTS5, counts) |

Exit code 0 if all checks pass, 1 if any check fails.

Without `--project`, lists memory counts for all discovered projects.

## export

Export memories, entities, and edges to JSON. Full fidelity — soft-deleted memories are included.

```bash
graphbase-memories export --project SLUG [--output FILE]
```

| Option | Default | Description |
|---|---|---|
| `--project` | _(required)_ | Project slug |
| `--output` | `-` (stdout) | Output file path (`-` = stdout) |

Output schema (`format_version: "1.0"`):
```json
{
  "format_version": "1.0",
  "exported_at": "2026-04-06T00:00:00",
  "generator": "graphbase-memories-mcp 1.0.0",
  "projects": {
    "my-project": {
      "memories": [...],
      "entities": [...],
      "edges": [...]
    }
  }
}
```

## import

Import a JSON export file.

```bash
graphbase-memories import --file PATH [--merge | --replace]
```

| Option | Default | Description |
|---|---|---|
| `--file` | _(required)_ | Path to export JSON file |
| `--merge` | _(default)_ | Skip records whose IDs already exist (idempotent) |
| `--replace` | — | Wipe all project data first, then import (prompts for confirmation) |

`--replace` requires typing the project name to confirm — it cannot be scripted without user interaction by design.

## devtools

Launch a standalone HTTP server with a browser-based UI for inspecting memories. Useful for debugging graph state without writing MCP tool calls.

```bash
graphbase-memories devtools --project SLUG [--host HOST] [--port PORT] [--data-dir PATH] [--open-browser]
```

| Option | Default | Description |
|---|---|---|
| `--project` | _(required)_ | Project slug to inspect |
| `--host` | `127.0.0.1` | HTTP bind host |
| `--port` | `3001` | HTTP port to listen on |
| `--data-dir` | `~/.graphbase` | Override `GRAPHBASE_DATA_DIR` |
| `--open-browser` | `False` | Open the UI in a browser after the server starts |

The UI is served from the bundled `src/graphbase_memories/devtools/static/` directory. By default it prints the local URL and keeps serving. Pass `--open-browser` to open the page automatically after the socket is bound.

## setup

Patch `.mcp.json` and write the Claude Code hook script.

```bash
graphbase-memories setup [--project-dir DIR] [--hook-dir DIR] [--python PATH] [--dry-run]
```

| Option | Default | Description |
|---|---|---|
| `--project-dir` | `.` | Directory where `.mcp.json` lives |
| `--hook-dir` | `~/.claude/hooks/` | Directory for the hook script |
| `--python` | auto-detected | Python executable to use in the hook |
| `--dry-run` | `False` | Print actions without making changes |

Always run `--dry-run` first to preview changes.
