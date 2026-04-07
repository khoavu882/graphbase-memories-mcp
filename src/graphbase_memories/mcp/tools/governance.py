"""Governance tool: request_global_write_approval."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.graph.repositories import token_repo
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def request_global_write_approval(
    ctx: Context,
    content_preview: str,
) -> dict:
    """
    Request approval to write to global scope (FR-55, S-1).
    Returns a one-time token valid for governance_token_ttl_s seconds.
    Pass the token as governance_token in save_decision(scope=global).

    Token is stored in Neo4j — durable across process restarts within TTL.
    """
    driver = ctx.lifespan_context["driver"]
    token = await token_repo.create(
        content_preview=content_preview,
        ttl_s=settings.governance_token_ttl_s,
        driver=driver,
        database=settings.neo4j_database,
    )
    return {
        "token": token.id,
        "expires_at": token.expires_at.isoformat(),
        "ttl_seconds": settings.governance_token_ttl_s,
        "instructions": "Pass this token as governance_token in save_decision(scope='global').",
    }
