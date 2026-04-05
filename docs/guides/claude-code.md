# Claude Code Setup

## .mcp.json registration

Add graphbase-memories to your project's `.mcp.json` (created by `setup`, or manually):

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "type": "stdio",
      "command": "python3",
      "args": ["-m", "graphbase_memories", "server"]
    }
  }
}
```

If you prefer the installed script:

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "type": "stdio",
      "command": "graphbase-memories",
      "args": ["server"]
    }
  }
}
```

## Hook for automatic context injection

The hook calls `inject` at session start and prepends a YAML context block to each prompt. Register it in Claude Code `settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/home/you/.claude/hooks/graphbase-memories-hook.sh"
          }
        ]
      }
    ]
  },
  "env": {
    "GRAPHBASE_PROJECT": "your-project-slug"
  }
}
```

The hook script wraps the call in `timeout 3` so it never blocks session startup.

## SSE transport (multi-client)

If you want to run the server as a persistent HTTP process:

```bash
graphbase-memories server --transport sse --port 8765
```

Then register in `.mcp.json`:

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "type": "sse",
      "url": "http://127.0.0.1:8765/sse"
    }
  }
}
```

## Optional DevTools sidecar

If you want the browser-based inspector to run alongside the MCP server, start the server with `--devtools` and provide a project explicitly or through `GRAPHBASE_PROJECT`:

```bash
graphbase-memories server --devtools --devtools-project your-project-slug
graphbase-memories server --transport sse --devtools --devtools-project your-project-slug --open-browser
```

Notes:
- In `stdio` mode, DevTools logs are written to `stderr` so MCP `stdout` remains valid.
- The DevTools sidecar binds to `127.0.0.1` by default.
- `--open-browser` is valid only when `--devtools` is enabled.

## Recommended `settings.json` env block

```json
{
  "env": {
    "GRAPHBASE_PROJECT": "your-project-slug",
    "GRAPHBASE_DATA_DIR": "~/.graphbase",
    "GRAPHBASE_LOG_LEVEL": "WARNING"
  }
}
```

`GRAPHBASE_PROJECT` is the only required variable. The rest have sensible defaults.
