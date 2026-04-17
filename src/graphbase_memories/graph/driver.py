"""
Neo4j async driver lifecycle + Cypher query file loader.

B-2 fix: driver lifecycle owned by FastMCP lifespan context manager.
         driver.close() is only called after all in-flight tool calls finish.
M-3 fix: all .cypher files loaded at import time — missing file = FileNotFoundError
         at startup, not at first query execution.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from neo4j import AsyncGraphDatabase

from graphbase_memories.config import settings

QUERIES_DIR = Path(__file__).parent / "queries"


def _load_cypher(name: str) -> str:
    """Load a named .cypher file. Raises FileNotFoundError at import if missing."""
    path = QUERIES_DIR / f"{name}.cypher"
    if not path.exists():
        raise FileNotFoundError(
            f"Required Cypher query file is missing: {path}\n"
            f"Ensure all files in {QUERIES_DIR} are present before starting."
        )
    return path.read_text(encoding="utf-8")


# Load all query files at module import — M-3 fast-fail validation.
# Constants are exported only for files whose content is read at runtime.
# Remaining files are validated (FileNotFoundError at startup if missing)
# but their content is embedded inline in the calling module.
SCHEMA_DDL = _load_cypher("schema")
FEDERATION_QUERIES = _load_cypher("federation")
IMPACT_QUERIES = _load_cypher("impact")
TOPOLOGY_QUERIES = _load_cypher("topology")
TOPOLOGY_Q_QUERIES = _load_cypher("topology_queries")
_load_cypher("retrieval")
_load_cypher("write")
_load_cypher("dedup")
_load_cypher("hygiene")
_load_cypher("surface")


@asynccontextmanager
async def neo4j_lifespan(server):
    """
    FastMCP lifespan: create driver, run schema DDL, yield driver in context,
    then close safely after all tool calls complete.

    Usage in FastMCP:
        mcp = FastMCP("graphbase-memories", lifespan=neo4j_lifespan)

    Tools access driver via:
        driver = ctx.lifespan_context["driver"]
    """
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        max_connection_pool_size=settings.neo4j_max_pool_size,
        connection_timeout=settings.neo4j_connection_timeout,
    )

    try:
        # Fail fast: verify connectivity before accepting any tool calls
        await driver.verify_connectivity()

        # Run idempotent schema DDL on every startup
        # Neo4j 5: each statement in the file runs separately via session.run()
        async with driver.session(database=settings.neo4j_database) as session:
            for statement in split_statements(SCHEMA_DDL):
                await session.run(statement)

        yield {"driver": driver}
    finally:
        # Safe: FastMCP ensures this runs only after all in-flight tool calls finish.
        # try/finally wraps the full lifespan so driver.close() is called even if
        # connectivity check or schema DDL raises before yield.
        await driver.close()


def split_statements(cypher: str) -> list[str]:
    """Split a multi-statement Cypher file by semicolons, yielding non-empty statements.

    Limitations (safe for schema DDL, but callers should be aware):
    - Splits on bare `;` — semicolons inside quoted string literals would break the split.
      None of the current schema or query files use semicolons in string values.
    - Full-line `//` comments are stripped by this function; inline `//` comments are
      passed through to Neo4j, which handles them natively.
    - A trailing `;` at EOF produces an empty final segment, which is skipped correctly.
    """
    statements = []
    for stmt in cypher.split(";"):
        cleaned = "\n".join(
            line for line in stmt.splitlines() if line.strip() and not line.strip().startswith("//")
        ).strip()
        if cleaned:
            statements.append(cleaned)
    return statements
