# Quick Start

Get `graphbase-memories-mcp` running in three steps.

---

## Step 1 — Start Neo4j

The server requires a running Neo4j 5 instance. The included Docker Compose file is the fastest way:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Wait ~10 seconds for Neo4j to finish starting. Verify it is healthy:

```bash
docker compose -f docker-compose.neo4j.yml ps
# Expected: State = Up (healthy)
```

Default credentials: `neo4j` / `graphbase` on `bolt://localhost:7687`.

!!! tip "Custom credentials"
    Set `GRAPHBASE_NEO4J_PASSWORD` before starting the server if you use different credentials.
    See [Configuration](configuration.md) for all available options.

---

## Step 2 — Install

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install (editable mode for development)
pip install -e ".[dev]"

# Or install without dev extras
pip install .
```

Verify the CLI is available:

```bash
graphbase-memories-mcp --help
# Expected output:
#  Usage: graphbase-memories-mcp [OPTIONS] COMMAND [ARGS]...
#  Commands: serve, devtools, hygiene
```

---

## Step 3 — Connect to your agent

Copy the example MCP configuration to your project root:

```bash
cp .mcp.json.example .mcp.json
```

Edit `.mcp.json` with the path to your virtual environment:

```json
{
  "mcpServers": {
    "graphbase-memories": {
      "command": "/absolute/path/to/.venv/bin/graphbase-memories-mcp",
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

Restart Claude Code (or your agent host). The 12 memory tools will appear in the tool list.

!!! note "Absolute path required"
    The `command` field must be an absolute path. Using `~` or relative paths will fail when the
    agent host spawns the server from a different working directory.

---

## Verify it works

In Claude Code, call the first tool to check scope state:

```
get_scope_state(project_id="my-first-project")
```

Expected response:
```json
{
  "scope_state": "uncertain",
  "project_exists": false
}
```

`uncertain` is correct — no project node exists in the graph yet. Save a session to create it:

```
save_session(
  session={
    "objective": "Testing graphbase-memories-mcp",
    "actions_taken": ["Installed the server", "Ran quick start"],
    "decisions_made": [],
    "open_items": [],
    "next_actions": ["Explore MCP tools"],
    "save_scope": "project"
  },
  project_id="my-first-project"
)
```

Then retrieve context:

```
retrieve_context(project_id="my-first-project", scope="project")
```

You should see your session node in the response with `retrieval_status: "succeeded"`.

---

## CLI commands

```bash
# Start the MCP stdio server (primary agent mode)
graphbase-memories-mcp serve

# Start the HTTP devtools inspection server (human browsing)
graphbase-memories-mcp devtools --port 8765

# Run the memory hygiene cycle and print report as JSON
graphbase-memories-mcp hygiene --project-id <uuid>
graphbase-memories-mcp hygiene --scope global
```
