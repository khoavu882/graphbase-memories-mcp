"""Session tools: store_session_with_learnings."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import write as write_engine
from graphbase_memories.mcp.schemas import (
    BatchSaveResult,
    DecisionSchema,
    PatternSchema,
    SessionSchema,
)
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def store_session_with_learnings(
    ctx: Context,
    session: SessionSchema,
    project_id: str,
    decisions: list[DecisionSchema] | None = None,
    patterns: list[PatternSchema] | None = None,
    governance_token: str | None = None,
) -> BatchSaveResult:
    """
    Batched save: session summary + related decisions and patterns in one operation (FR-41).
    Returns BatchSaveResult with per-artifact status and overall save status.

    Replaces the removed save_session tool — pass decisions=[] and patterns=[]
    (or omit them) to save a session-only summary.

    governance_token: required when any decision in the batch has scope=global (FR-55).
    Obtain one via request_global_write_approval() before calling this tool.
    """
    driver = ctx.lifespan_context["driver"]
    return await write_engine.save_batch(
        session_data=session,
        decisions=decisions or [],
        patterns=patterns or [],
        project_id=project_id,
        driver=driver,
        database=settings.neo4j_database,
        governance_token=governance_token,
    )
