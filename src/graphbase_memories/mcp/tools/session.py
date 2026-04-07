"""Session tools: save_session, store_session_with_learnings."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import write as write_engine
from graphbase_memories.mcp.schemas import (
    BatchSaveResult,
    DecisionSchema,
    PatternSchema,
    SaveResult,
    SessionSchema,
)
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def save_session(
    ctx: Context,
    session: SessionSchema,
    project_id: str,
    focus: str | None = None,
) -> SaveResult:
    """
    Save a session summary to memory. Eligible when at least one of:
    a decision was made, context changed, a pattern identified, artifact finalized,
    or next action assigned (FR-39).
    """
    driver = ctx.lifespan_context["driver"]
    return await write_engine.save_session(
        session, project_id, focus, driver, settings.neo4j_database
    )


@mcp.tool()
async def store_session_with_learnings(
    ctx: Context,
    session: SessionSchema,
    project_id: str,
    decisions: list[DecisionSchema] | None = None,
    patterns: list[PatternSchema] | None = None,
) -> BatchSaveResult:
    """
    Batched save: session summary + related decisions and patterns in one operation (FR-41).
    Returns BatchSaveResult with per-artifact status and overall save status.
    """
    driver = ctx.lifespan_context["driver"]
    return await write_engine.save_batch(
        session_data=session,
        decisions=decisions or [],
        patterns=patterns or [],
        project_id=project_id,
        driver=driver,
        database=settings.neo4j_database,
    )
