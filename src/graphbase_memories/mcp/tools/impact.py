"""Impact tools: propagate_impact, graph_health."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import impact as impact_engine
from graphbase_memories.mcp.schemas.errors import MCPError
from graphbase_memories.mcp.schemas.results import ImpactReport, WorkspaceHealthReport
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def propagate_impact(
    ctx: Context,
    entity_id: str,
    change_description: str,
    impact_type: str = "breaking",
    max_depth: int = 3,
) -> ImpactReport | MCPError:
    """
    Run BFS from entity_id across CROSS_SERVICE_LINK edges to find all affected services.
    Writes an ImpactEvent audit node. max_depth is capped at settings.impact_max_depth.
    Risk levels: d=1→HIGH, d=2→MEDIUM, d=3→LOW, CONTRADICTS edge→CRITICAL.
    Returns MCPError with code=ENTITY_NOT_FOUND if entity_id does not exist in the graph.
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
    include_conflicts: bool = True,
) -> WorkspaceHealthReport:
    """
    Return health metrics for all services in the workspace.
    When include_conflicts=True (default): also returns all CONTRADICTS cross-service
    links as conflict_records (replaces the removed detect_conflicts tool).
    hygiene_status: "clean" | "needs_hygiene" | "critical".
    """
    driver = ctx.lifespan_context["driver"]
    return await impact_engine.graph_health(
        workspace_id, driver, settings.neo4j_database, include_conflicts=include_conflicts
    )
