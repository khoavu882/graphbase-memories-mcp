"""Impact tools: propagate_impact, graph_health, detect_conflicts."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import impact as impact_engine
from graphbase_memories.mcp.schemas.errors import ErrorCode, MCPError
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
) -> ImpactReport | MCPError:
    """
    Run BFS from entity_id across CROSS_SERVICE_LINK edges to find all affected services.
    Writes an ImpactEvent audit node. max_depth is capped at settings.impact_max_depth.
    Risk levels: d=1→HIGH, d=2→MEDIUM, d=3→LOW, CONTRADICTS edge→CRITICAL.
    Returns MCPError with code=ENTITY_NOT_FOUND if entity_id does not exist in the graph.
    """
    driver = ctx.lifespan_context["driver"]

    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (n {id: $id}) RETURN count(n) AS cnt LIMIT 1",
            id=entity_id,
        )
        record = await result.single()
        if not record or record["cnt"] == 0:
            return MCPError(
                code=ErrorCode.ENTITY_NOT_FOUND,
                message=f"Entity '{entity_id}' not found in the graph.",
                context={"entity_id": entity_id},
                next_step="Call upsert_entity_with_deps() to create the entity first.",
            )

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
