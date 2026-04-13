"""Retrieval tools: retrieve_context, get_scope_state, memory_surface."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import retrieval as retrieval_engine
from graphbase_memories.engines import scope as scope_engine
from graphbase_memories.engines import surface as surface_engine
from graphbase_memories.mcp.schemas import ContextBundle, MemoryScope, ScopeStateResult
from graphbase_memories.mcp.schemas.enums import ScopeState
from graphbase_memories.mcp.schemas.results import SurfaceResult
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def retrieve_context(
    ctx: Context,
    project_id: str,
    scope: MemoryScope,
    focus: str | None = None,
    categories: list[str] | None = None,
    keyword: str | None = None,
) -> ContextBundle:
    """
    Retrieve memory context for a project, ordered by scope priority (focus > project > global).
    Returns ContextBundle with retrieval_status and hygiene_due indicator.
    When keyword is provided, BM25 full-text search is fused with graph traversal via RRF.
    Each result item will include an _rrf_score field when keyword search is active.
    """
    driver = ctx.lifespan_context["driver"]
    return await retrieval_engine.execute(
        project_id=project_id,
        scope=scope.value,
        focus=focus,
        categories=categories,
        keyword=keyword,
        driver=driver,
        database=settings.neo4j_database,
    )


@mcp.tool()
async def get_scope_state(
    ctx: Context,
    project_id: str | None = None,
    focus: str | None = None,
) -> ScopeStateResult:
    """
    Check scope resolution state for a project without triggering any MCP read or write.
    Returns scope_state (resolved/uncertain/unresolved) and project_exists flag.
    """
    driver = ctx.lifespan_context["driver"]
    state = await scope_engine.validate(project_id, focus, driver, settings.neo4j_database)
    return ScopeStateResult(
        scope_state=state,
        project_exists=state == ScopeState.resolved,
        project_id=project_id,
        focus=focus,
    )


@mcp.tool()
async def memory_surface(
    ctx: Context,
    query: str,
    project_id: str | None = None,
    limit: int = 5,
) -> SurfaceResult:
    """
    Lightweight BM25 memory surface: find relevant memories without full context retrieval.
    Use this before editing a file, starting a task, or when retrieve_context would be too broad.

    Returns SurfaceResult with matched memory nodes (Decision, Pattern, Context, EntityFact),
    their freshness indicator, and a next_step hint.

    Prefer retrieve_context when you need full scope-aware context bundles.
    Use memory_surface when you have a specific topic keyword and want a focused lookup.
    """
    driver = ctx.lifespan_context["driver"]
    return await surface_engine.execute(
        query=query,
        project_id=project_id,
        limit=limit,
        driver=driver,
        database=settings.neo4j_database,
    )
