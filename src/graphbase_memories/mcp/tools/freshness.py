"""Freshness tool: memory_freshness."""

from __future__ import annotations

import logging

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import freshness as freshness_engine
from graphbase_memories.mcp.schemas.enums import MemoryScope
from graphbase_memories.mcp.schemas.results import FreshnessReport
from graphbase_memories.mcp.server import mcp

logger = logging.getLogger(__name__)


@mcp.tool()
async def memory_freshness(
    ctx: Context,
    project_id: str | None = None,
    scope: MemoryScope = MemoryScope.project,
    stale_after_days: int | None = None,
    limit: int = 50,
) -> FreshnessReport:
    """
    Return nodes not updated within the freshness threshold, ranked oldest-first.
    stale_after_days defaults to GRAPHBASE_FRESHNESS_STALE_DAYS (30).
    Use before run_hygiene() to preview which nodes are at risk of being flagged.
    Set project_id=None to scan all projects (global view).
    """
    driver = ctx.lifespan_context["driver"]
    return await freshness_engine.scan(
        project_id=project_id,
        stale_after_days=stale_after_days,
        scan_limit=min(limit, 200),
        driver=driver,
        database=settings.neo4j_database,
    )
