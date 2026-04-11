"""Impact tools: propagate_impact, graph_health, detect_conflicts."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import impact as impact_engine
from graphbase_memories.mcp.schemas.results import (
    ConflictRecord,
    ImpactReport,
    WorkspaceHealthReport,
)
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def propagate_impact(
    ctx: Context,
    entity_id: str,
    change_description: str,
    impact_type: str = "breaking",
    max_depth: int = 3,
) -> ImpactReport:
    """
    Run BFS from entity_id across CROSS_SERVICE_LINK edges to find all affected services.
    Writes an ImpactEvent audit node. max_depth is capped at settings.impact_max_depth.
    Risk levels: d=1→HIGH, d=2→MEDIUM, d=3→LOW, CONTRADICTS edge→CRITICAL.
    """
    driver = ctx.lifespan_context["driver"]
    return await impact_engine.propagate_impact(
        entity_id,
        change_description,
        impact_type,
        min(max_depth, settings.impact_max_depth),
        driver,
        settings.neo4j_database,
    )


@mcp.tool()
async def graph_health(
    ctx: Context,
    workspace_id: str,
) -> WorkspaceHealthReport:
    """
    Return health metrics for all services in the workspace.
    hygiene_status: "clean" | "needs_hygiene" | "critical".
    """
    driver = ctx.lifespan_context["driver"]
    return await impact_engine.graph_health(workspace_id, driver, settings.neo4j_database)


@mcp.tool()
async def detect_conflicts(
    ctx: Context,
    workspace_id: str,
    limit: int = 100,
) -> list[ConflictRecord]:
    """
    Return all CONTRADICTS cross-service links between services in the workspace.
    Returns empty list when no conflicts exist (not an error).
    """
    driver = ctx.lifespan_context["driver"]
    return await impact_engine.detect_conflicts(
        workspace_id, limit, driver, settings.neo4j_database
    )
