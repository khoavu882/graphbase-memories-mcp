# Configuration

All settings are read from **environment variables** with the `GRAPHBASE_` prefix, using `pydantic-settings`. No config files are required — defaults work for local development with the provided Docker Compose setup.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `GRAPHBASE_NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `GRAPHBASE_NEO4J_USER` | `neo4j` | Neo4j username |
| `GRAPHBASE_NEO4J_PASSWORD` | `graphbase` | Neo4j password |
| `GRAPHBASE_NEO4J_DATABASE` | `neo4j` | Neo4j database name |
| `GRAPHBASE_NEO4J_MAX_POOL_SIZE` | `10` | Connection pool size |
| `GRAPHBASE_NEO4J_CONNECTION_TIMEOUT` | `5.0` | Connection timeout for Neo4j driver creation |
| `GRAPHBASE_RETRIEVAL_TIMEOUT_S` | `5.0` | Per-attempt retrieval timeout (seconds) |
| `GRAPHBASE_RETRIEVAL_MAX_RETRIES` | `1` | Max retries on timeout or transient error |
| `GRAPHBASE_RETRIEVAL_FOCUS_LIMIT` | `10` | Max focus-scope results returned per retrieval |
| `GRAPHBASE_RETRIEVAL_PROJECT_LIMIT` | `20` | Max project-scope results returned per retrieval |
| `GRAPHBASE_RETRIEVAL_GLOBAL_LIMIT` | `5` | Max global-scope results returned per retrieval |
| `GRAPHBASE_WRITE_MAX_RETRIES` | `1` | Max retries on `ServiceUnavailable` |
| `GRAPHBASE_GOVERNANCE_TOKEN_TTL_S` | `60` | GovernanceToken expiry (seconds) |
| `GRAPHBASE_FEDERATION_ACTIVE_WINDOW_MINUTES` | `60` | Service liveness window for federation queries |
| `GRAPHBASE_FEDERATION_MAX_RESULTS` | `100` | Max cross-service search results |
| `GRAPHBASE_IMPACT_MAX_DEPTH` | `3` | Max BFS depth for impact propagation |
| `GRAPHBASE_WORKSPACE_ENFORCE_ISOLATION` | `true` | Enforce workspace isolation boundaries |
| `GRAPHBASE_FTS_ENABLED` | `true` | Enable hybrid full-text retrieval features |
| `GRAPHBASE_FTS_LIMIT` | `20` | BM25 candidates per full-text index |
| `GRAPHBASE_RRF_K` | `60` | Reciprocal rank fusion damping constant |
| `GRAPHBASE_FRESHNESS_RECENT_DAYS` | `7` | Threshold for `recent` freshness labels |
| `GRAPHBASE_FRESHNESS_STALE_DAYS` | `30` | Threshold for `stale` freshness labels |

---

## Setting variables

=== "Shell export"

    ```bash
    export GRAPHBASE_NEO4J_URI=bolt://my-host:7687
    export GRAPHBASE_NEO4J_PASSWORD=my-secret
    graphbase serve
    ```

=== "Shell-sourced .env"

    The current `Settings` model does not auto-load `.env` files. If you prefer a local file,
    source it explicitly before starting the server:

    ```bash
    cat > .env <<'EOF'
    GRAPHBASE_NEO4J_URI=bolt://my-host:7687
    GRAPHBASE_NEO4J_USER=neo4j
    GRAPHBASE_NEO4J_PASSWORD=my-secret
    GRAPHBASE_NEO4J_DATABASE=neo4j
    EOF

    set -a
    source .env
    set +a
    ```

=== "MCP JSON config"

    Pass variables via the `env` block in `.mcp.json`:

    ```json
    {
      "mcpServers": {
        "graphbase-memories": {
          "command": "/path/to/.venv/bin/graphbase",
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

---

## Connection pool

`GRAPHBASE_NEO4J_MAX_POOL_SIZE` controls the maximum number of concurrent Bolt connections to Neo4j for the MCP server process. The default of `10` is appropriate for a single-agent setup. The devtools server uses a separate fixed pool of `2`, so the default combined ceiling is `12` concurrent connections.

`GRAPHBASE_NEO4J_CONNECTION_TIMEOUT` controls how long the driver waits when opening a connection
to Neo4j. Increase it if your database is remote or often cold-starts.

---

## Retrieval timeout and retries

The retrieval engine enforces a hard timeout per attempt (`GRAPHBASE_RETRIEVAL_TIMEOUT_S`). After a timeout or transient error, it retries once. After retry exhaustion, the tool returns `retrieval_status: "failed"` and the agent continues in local/no-memory mode — it does not crash.

!!! warning "Tuning for slow Neo4j"
    If your Neo4j instance is hosted remotely with high latency, increase `GRAPHBASE_RETRIEVAL_TIMEOUT_S`
    to `10.0` or higher. Keeping retries at `1` is still recommended to avoid cascading delays.

---

## Governance token TTL

`request_global_write_approval` creates a one-time token stored as a `GovernanceToken` node in Neo4j. The token expires after `GRAPHBASE_GOVERNANCE_TOKEN_TTL_S` seconds (default: 60). Expired tokens are rejected and cleaned up by the hygiene engine.

See [Governance tool](tools/governance.md) for the full write approval flow.
