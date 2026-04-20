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

    # Install the package
    pip install -e .
    ```

Verify the CLI is available:

```bash
graphbase --help
# Expected output:
#  Usage: graphbase [OPTIONS] COMMAND [ARGS]...
#  Commands: serve, devtools, hygiene, surface
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

`empty` with `scope_state: "uncertain"` is correct — the server is reachable, but the `project_id`
does not map to an existing `:Project` node yet.

Writes require `scope_state: "resolved"`. In service-oriented setups, the simplest bootstrap path is
to register the service first:

```python
register_federated_service(
    service_id="my-first-project",
    workspace_id="demo-workspace"
)
```

Then you can persist a session summary:

```python
store_session_with_learnings(
    session={
        "objective": "Testing graphbase",
        "actions_taken": ["Installed the server", "Ran quick start"],
        "decisions_made": [],
        "open_items": [],
        "next_actions": ["Explore MCP tools"],
        "save_scope": "project"
    },
    project_id="my-first-project",
    decisions=[],
    patterns=[]
)
```

After that, `retrieve_context(project_id="my-first-project", scope="project")` should return
`scope_state: "resolved"`.

---

## CLI commands

```bash
# Start the MCP stdio server (primary agent mode)
graphbase serve

# Start the HTTP devtools inspection server (human browsing)
graphbase devtools --port 8765
# Console prints: DevTools write token: <token>

# Run the memory hygiene cycle and print report as JSON
graphbase hygiene --project-id <uuid>
graphbase hygiene --scope global

# Surface relevant memories for a keyword or symbol
graphbase surface "dedup hash" --project-id my-project
```

## Devtools UI quick tour

After starting `graphbase devtools`, open `http://localhost:8765`:

- `/` redirects to `/ui`
- The main dashboard uses a sidebar for Projects, Memory, Tools, and Operations
- `/ui/graph.html` is the standalone graph canvas with deep-link support
- The graph canvas can export the current visible subgraph as JSON or CSV

For write actions in the UI:

- Copy the startup token printed by the server
- Paste it into the `Write Token` field in the header
- The UI stores it in `localStorage` and uses it for Inspector edit/delete actions

The main interactive flows are:

- Projects: browse projects and drill into project-scoped memory
- Memory: paginated search with filters, sort, and keyboard shortcuts
- Inspector: navigate relationships, edit/delete memory nodes, copy/download per-node JSON
- Operations: inspect workspace health, run hygiene, and repair orphaned `EntityFact` nodes
