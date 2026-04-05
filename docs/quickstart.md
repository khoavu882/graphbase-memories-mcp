# Quick Start

## 1. Install

```bash
pip install graphbase-memories-mcp
```

Or for development (editable install):

```bash
git clone https://github.com/your-org/graphbase-memories-mcp
cd graphbase-memories-mcp
pip install -e ".[dev]"
```

## 2. Run setup

```bash
graphbase-memories setup --project-dir . --dry-run  # preview first
graphbase-memories setup --project-dir .             # apply
```

This:
- Patches `.mcp.json` in your project directory with the MCP server registration
- Writes a hook script to `~/.claude/hooks/graphbase-memories-hook.sh`
- Creates `~/.graphbase/` data directory

## 3. Set your project slug

In Claude Code `settings.json`, add an `env` block:

```json
{
  "env": {
    "GRAPHBASE_PROJECT": "my-project"
  }
}
```

The project slug is used as a namespace — all memories for a project share the same SQLite database.

## 4. Register the hook

In Claude Code `settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/graphbase-memories-hook.sh"
          }
        ]
      }
    ]
  }
}
```

## 5. Verify

Run the health check:

```bash
graphbase-memories doctor --project my-project
```

Expected output:
```
graphbase-memories doctor
────────────────────────────────────────────
  [OK  ] Python >= 3.11  (3.11.x)
  [OK  ] fastmcp installed  (2.x.x)
  [OK  ] data dir writable  (~/.graphbase)
  [OK  ] SQLite WAL mode  (wal)
  [OK  ] Schema version  (2)
  [OK  ] FTS5 present
  [OK  ] Hook script found
────────────────────────────────────────────
  All checks passed.
```

## 6. Store your first memory

In Claude Code, once the MCP server is connected, ask Claude to store a memory:

```
Remember that this project uses the "SUPERSEDES pattern" for revising decisions —
store a new memory and relate it to the old one rather than editing in-place.
```

Claude will call `store_memory` with type `pattern` and tag it appropriately.

## Next steps

- Optional DevTools UI:
  Start the standalone inspector with `graphbase-memories devtools --project my-project`
  Add `--open-browser` to open the page automatically after bind
  Or run it alongside the MCP server with `graphbase-memories server --devtools --devtools-project my-project`
- [How It Works](how-it-works.md) — understand the graph model
- [Session Workflows](guides/workflows.md) — real-world usage patterns
- [CLI Reference](cli.md) — all subcommands
