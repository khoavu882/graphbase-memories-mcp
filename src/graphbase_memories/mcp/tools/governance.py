"""Governance tool: request_global_write_approval."""

from __future__ import annotations

from fastmcp import Context
from neo4j.exceptions import Neo4jError

from graphbase_memories.config import settings
from graphbase_memories.engines import governance as governance_engine
from graphbase_memories.mcp.schemas.errors import ErrorCode, MCPError
from graphbase_memories.mcp.schemas.results import GovernanceTokenResult
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def request_global_write_approval(
    ctx: Context,
    content_preview: str,
) -> GovernanceTokenResult | MCPError:
    """
    Request approval to write to global scope (FR-55, S-1).
    Returns a one-time token valid for governance_token_ttl_s seconds.
    Pass the token as governance_token in save_decision(scope=global).

    Token is stored in Neo4j — durable across process restarts within TTL.
    Returns MCPError with code=INTERNAL_ERROR if Neo4j is unavailable.
    """
    driver = ctx.lifespan_context["driver"]
    try:
        token = await governance_engine.create_token(
            content_preview=content_preview,
            driver=driver,
            database=settings.neo4j_database,
        )
    except Neo4jError as exc:
        return MCPError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to create governance token. Neo4j may be unavailable.",
            context={"detail": str(exc)},
            next_step="Verify Neo4j is running, then retry request_global_write_approval().",
        )
    return GovernanceTokenResult(
        token=token.id,
        expires_at=token.expires_at.isoformat(),
        ttl_seconds=settings.governance_token_ttl_s,
        instructions="Pass this token as governance_token in save_decision(scope='global').",
    )
