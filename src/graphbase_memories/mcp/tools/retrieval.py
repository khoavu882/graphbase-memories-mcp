"""Retrieval tools: retrieve_context, get_scope_state."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import retrieval as retrieval_engine
from graphbase_memories.engines import scope as scope_engine
from graphbase_memories.mcp.schemas import ContextBundle, MemoryScope
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def retrieve_context(
    ctx: Context,
    project_id: str,
    scope: MemoryScope,
    focus: str | None = None,
    categories: list[str] | None = None,
    topic: str | None = None,
) -> ContextBundle:
    """
    Retrieve memory context for a project, ordered by scope priority (focus > project > global).
    Returns ContextBundle with retrieval_status and hygiene_due indicator.
    """
    driver = ctx.lifespan_context["driver"]
    return await retrieval_engine.execute(
        project_id=project_id,
        scope=scope.value,
        focus=focus,
        categories=categories,
        topic=topic,
        driver=driver,
        database=settings.neo4j_database,
    )


@mcp.tool()
async def get_scope_state(
    ctx: Context,
    project_id: str | None = None,
    focus: str | None = None,
) -> dict:
    """
    Check scope resolution state for a project without triggering any MCP read or write.
    Returns scope_state (resolved/uncertain/unresolved) and project_exists flag.
    """
    driver = ctx.lifespan_context["driver"]
    state = await scope_engine.validate(project_id, focus, driver, settings.neo4j_database)

    project_exists = state.value == "resolved"
    return {
        "scope_state": state.value,
        "project_exists": project_exists,
        "project_id": project_id,
        "focus": focus,
    }
