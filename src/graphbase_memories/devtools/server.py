"""
Devtools HTTP inspection server — FastAPI app for human memory browsing.
Start with: graphbase-memories-mcp devtools --port 8765
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from neo4j import AsyncDriver, AsyncGraphDatabase

from graphbase_memories.config import settings
from graphbase_memories.devtools.routes import events, health, hygiene, memory, projects, tools
from graphbase_memories.graph.driver import SCHEMA_DDL, split_statements

# UI static files directory
UI_DIR = Path(__file__).parent / "ui"

_driver: AsyncDriver | None = None

# Devtools uses a capped pool (2) to stay within Neo4j Community Edition's
# connection limit when running alongside the MCP server (pool=8).
_DEVTOOLS_POOL_SIZE = 2


def _get_driver() -> AsyncDriver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized — lifespan not started")
    return _driver


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _driver
    _driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        max_connection_pool_size=_DEVTOOLS_POOL_SIZE,
    )
    await _driver.verify_connectivity()
    async with _get_driver().session(database=settings.neo4j_database) as session:
        for stmt in split_statements(SCHEMA_DDL):
            await session.run(stmt)
    yield
    await _driver.close()


app = FastAPI(
    title="graphbase-memories devtools",
    description="HTTP interface for inspecting graph memory nodes and invoking MCP tools",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Mount route modules
# ---------------------------------------------------------------------------

app.include_router(events.router)
app.include_router(memory.router)
app.include_router(projects.router)
app.include_router(tools.router)
app.include_router(health.router)
app.include_router(hygiene.router)

# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect browser root to the devtools UI."""
    return RedirectResponse(url="/ui")
