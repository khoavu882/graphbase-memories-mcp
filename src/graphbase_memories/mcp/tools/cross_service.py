"""Cross-service search and linking tools."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import federation as federation_engine
from graphbase_memories.mcp.schemas.enums import CrossServiceLinkType
from graphbase_memories.mcp.schemas.results import CrossServiceBundle, SaveResult
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def search_cross_service(
    ctx: Context,
    query: str,
    workspace_id: str,
    target_project_ids: list[str] | None = None,
    node_types: list[str] | None = None,
    limit: int = 50,
) -> CrossServiceBundle:
    """
    Full-text search across all services in a workspace.
    node_types filters by node label: "EntityFact", "Decision" (default: both).
    target_project_ids narrows search to specific services.
    """
    driver = ctx.lifespan_context["driver"]
    return await federation_engine.search_cross_service(
        query,
        workspace_id,
        target_project_ids,
        node_types,
        limit,
        driver,
        settings.neo4j_database,
    )


@mcp.tool()
async def link_cross_service(
    ctx: Context,
    source_entity_id: str,
    target_entity_id: str,
    relationship_type: CrossServiceLinkType,
    rationale: str,
    confidence: float = 1.0,
    created_by: str | None = None,
) -> SaveResult:
    """
    Create a typed CROSS_SERVICE_LINK between entities in different services.
    Same-project links are rejected. Duplicate links are silently skipped (duplicate_skip).
    """
    driver = ctx.lifespan_context["driver"]
    return await federation_engine.create_cross_service_link(
        source_entity_id,
        target_entity_id,
        relationship_type.value,
        rationale,
        confidence,
        created_by,
        driver,
        settings.neo4j_database,
    )
