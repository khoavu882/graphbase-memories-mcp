"""Entity tool: upsert_entity_with_deps."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import write as write_engine
from graphbase_memories.mcp.schemas import EntityFactSchema, EntityRelation, SaveResult, SaveStatus
from graphbase_memories.mcp.schemas.errors import ErrorCode, MCPError
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def upsert_entity_with_deps(
    ctx: Context,
    entity: EntityFactSchema,
    project_id: str,
    related_entities: list[EntityRelation] | None = None,
    focus: str | None = None,
) -> SaveResult | MCPError:
    """
    Upsert an EntityFact node and create typed relationships to related entities (M-2).
    related_entities must specify relationship_type from:
    BELONGS_TO, CONFLICTS_WITH, PRODUCED, MERGES_INTO.
    Returns MCPError with code=SCOPE_VIOLATION if the write is blocked by scope rules.
    """
    driver = ctx.lifespan_context["driver"]
    result = await write_engine.upsert_entity(
        entity, related_entities or [], project_id, focus, driver, settings.neo4j_database
    )
    if result.status == SaveStatus.blocked_scope:
        return MCPError(
            code=ErrorCode.SCOPE_VIOLATION,
            message=result.message or "Write blocked by scope rules.",
            context={"project_id": project_id, "focus": focus},
            next_step="Call request_global_write_approval() to obtain a governance token.",
        )
    return result
