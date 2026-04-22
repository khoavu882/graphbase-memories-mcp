# Graphbase Memories for Codex

This package provides Codex-native Graphbase integration:

- a Codex plugin manifest at `.codex-plugin/plugin.json`
- reusable Codex skills under `skills/`
- Graphbase MCP server config in `.mcp.json`
- repo-local Codex hook examples in `.codex/`
- a Codex hook dispatcher in `hooks/`

The layout follows OpenAI Codex docs for skills, plugins, MCP config, and hooks.

## Official Docs Basis

This package is built around the current Codex documentation:

- Skills are directories with `SKILL.md` files and optional scripts/references/assets.
- Codex scans repository skills from `.agents/skills`, while plugins are the distribution unit for reusable skills.
- Plugins require `.codex-plugin/plugin.json` and may bundle `skills`, `hooks`, and `mcpServers`.
- MCP servers for Codex are configured in `config.toml` with `[mcp_servers.<name>]`.
- Hooks are discovered from `.codex/hooks.json`; command hooks receive JSON on stdin.
- Current Codex hook support allows additional context from `SessionStart`, `UserPromptSubmit`, and `PostToolUse`.

## Install as a local repo integration

1. Install the Python package and make sure `graphbase` is on `PATH`.
2. Copy or merge `.codex/config.toml.example` into `<repo>/.codex/config.toml`.
3. Copy or merge `.codex/hooks.json.example` into `<repo>/.codex/hooks.json`.
4. Start Neo4j and restart Codex.

Codex MCP config lives in `config.toml`; the JSON `.mcp.json` is included for plugin packaging because Codex plugin manifests can bundle MCP server config.

## Install as a plugin

The plugin root is this directory. For local plugin testing, add a marketplace entry that points at this folder from a marketplace root, then restart Codex.

Minimal marketplace entry:

```json
{
  "name": "graphbase-memories",
  "source": {
    "source": "local",
    "path": "./graphbase-tools/codex"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

## Hook behavior

The hook dispatcher reads the Codex hook JSON payload from stdin and always exits `0`.

- `SessionStart`: adds a short reminder to load project memory.
- `UserPromptSubmit`: extracts task keywords, calls `graphbase surface`, and injects relevant memory.
- `PostToolUse`: after successful git history mutations, checks changed file names for stale memory.

The hook intentionally avoids memory injection in `PreToolUse`: current Codex hook support only intercepts Bash there, plain stdout is ignored, and additional-context output is not supported for that event.

## Validation

```bash
node --test graphbase-tools/codex/hooks/graphbase-codex-hook.test.js
```
