# Quick Start

Get `graphbase` running in three steps.

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

=== "uv (recommended)"

    ```bash
    # uv respects the lockfile for reproducible installs
    uv sync
    ```

=== "pip"

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
graphbase --help
# Expected output:
#  Usage: graphbase [OPTIONS] COMMAND [ARGS]...
#  Commands: serve, devtools, hygiene
```

---

## Step 3 — Connect to your agent

Copy `.mcp.json.example` to `.mcp.json` in your project root and edit it with the absolute path to your virtual environment binary. Restart your agent host — the 21 `graphbase-memories` tools will appear in the tool list.

See [Connect to Your Agent](connect.md) for full configuration details, including global install and setup for Cursor, Cline, and other MCP hosts.

---

## Verify it works

In Claude Code, load context to confirm the server is reachable:

```
retrieve_context(project_id="my-first-project", scope="project")
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

`empty` with `scope_state: "uncertain"` is correct — no project node exists in the graph yet. Save a session to create it:

```
save_session(
  session={
    "objective": "Testing graphbase",
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
graphbase serve

# Start the HTTP devtools inspection server (human browsing)
graphbase devtools --port 8765

# Run the memory hygiene cycle and print report as JSON
graphbase hygiene --project-id <uuid>
graphbase hygiene --scope global
```
