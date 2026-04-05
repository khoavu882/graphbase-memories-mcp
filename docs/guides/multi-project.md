# Multi-Project Setup

graphbase-memories namespaces all data by project slug. Each project gets its own SQLite database at `~/.graphbase/{project-slug}/memories.db`.

## Using multiple project slugs

Set `GRAPHBASE_PROJECT` per project in your Claude Code workspace settings:

**Project A** (`.vscode/settings.json` or Claude Code project `settings.json`):
```json
{ "env": { "GRAPHBASE_PROJECT": "payment-service" } }
```

**Project B**:
```json
{ "env": { "GRAPHBASE_PROJECT": "user-auth" } }
```

Each project's memories are completely isolated.

## DevTools per project

The DevTools UI is also project-scoped. Start it with the same slug you use for memory storage:

```bash
graphbase-memories devtools --project payment-service
graphbase-memories devtools --project user-auth --open-browser
```

If you launch DevTools as a sidecar from the MCP server, prefer explicit project selection:

```bash
graphbase-memories server --devtools --devtools-project payment-service
```

When multiple sessions are active, each sidecar still needs its own available port. If you see a bind failure, set a different `--devtools-port` for that session.

## Cross-project search

When `project` is omitted from `search_memories`, the server scans all known projects:

```python
# Searches across every project DB on disk
search_memories(query="circuit breaker pattern")
```

Auto-discovery scans `GRAPHBASE_DATA_DIR` for subdirectories containing `memories.db`. Projects are discovered automatically — no manual registration needed.

## Shared context between projects

To propagate a decision from one project to another, export and import:

```bash
graphbase-memories export --project payment-service | \
  graphbase-memories import --file - --merge
```

Or export to a file for review first:

```bash
graphbase-memories export --project payment-service --output /tmp/payment-export.json
# review the file
graphbase-memories import --file /tmp/payment-export.json --merge
```

## Overview of all projects

```bash
graphbase-memories doctor
```

Without `--project`, doctor lists memory counts for all discovered projects.
