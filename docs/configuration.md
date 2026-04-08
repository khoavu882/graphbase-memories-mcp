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
| `GRAPHBASE_RETRIEVAL_TIMEOUT_S` | `5.0` | Per-attempt retrieval timeout (seconds) |
| `GRAPHBASE_RETRIEVAL_MAX_RETRIES` | `1` | Max retries on timeout or transient error |
| `GRAPHBASE_WRITE_MAX_RETRIES` | `1` | Max retries on `ServiceUnavailable` |
| `GRAPHBASE_GOVERNANCE_TOKEN_TTL_S` | `60` | GovernanceToken expiry (seconds) |

---

## Setting variables

=== "Shell export"

    ```bash
    export GRAPHBASE_NEO4J_URI=bolt://my-host:7687
    export GRAPHBASE_NEO4J_PASSWORD=my-secret
    graphbase-memories-mcp serve
    ```

=== ".env file"

    Create a `.env` file in your working directory:

    ```bash
    GRAPHBASE_NEO4J_URI=bolt://my-host:7687
    GRAPHBASE_NEO4J_USER=neo4j
    GRAPHBASE_NEO4J_PASSWORD=my-secret
    GRAPHBASE_NEO4J_DATABASE=neo4j
    ```

    `pydantic-settings` loads `.env` files automatically if `python-dotenv` is installed.

=== "MCP JSON config"

    Pass variables via the `env` block in `.mcp.json`:

    ```json
    {
      "mcpServers": {
        "graphbase-memories": {
          "command": "/path/to/.venv/bin/graphbase-memories-mcp",
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

`GRAPHBASE_NEO4J_MAX_POOL_SIZE` controls the maximum number of concurrent Bolt connections to Neo4j. The default of `10` is appropriate for a single-agent setup. Increase it if multiple agents share one server instance.

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
