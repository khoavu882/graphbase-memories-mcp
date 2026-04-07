"""Artifact tools: save_decision, save_pattern, save_context."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import write as write_engine
from graphbase_memories.mcp.schemas import ContextSchema, DecisionSchema, PatternSchema, SaveResult
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def save_decision(
    ctx: Context,
    decision: DecisionSchema,
    project_id: str,
    focus: str | None = None,
    governance_token: str | None = None,
) -> SaveResult:
    """
    Save a durable decision to memory. For scope=global, a governance_token is required
    (obtain via request_global_write_approval). Includes dedup check before writing (FR-32).
    """
    driver = ctx.lifespan_context["driver"]
    return await write_engine.save_decision(
        decision, project_id, focus, governance_token, driver, settings.neo4j_database
    )


@mcp.tool()
async def save_pattern(
    ctx: Context,
    pattern: PatternSchema,
    project_id: str,
    focus: str | None = None,
) -> SaveResult:
    """Save a reusable process pattern to memory. Includes dedup check (FR-32)."""
    driver = ctx.lifespan_context["driver"]
    return await write_engine.save_pattern(
        pattern, project_id, focus, driver, settings.neo4j_database
    )


@mcp.tool()
async def save_context(
    ctx: Context,
    context: ContextSchema,
    project_id: str,
    focus: str | None = None,
) -> SaveResult:
    """Save a durable context item to memory."""
    driver = ctx.lifespan_context["driver"]
    return await write_engine.save_context(
        context, project_id, focus, driver, settings.neo4j_database
    )
