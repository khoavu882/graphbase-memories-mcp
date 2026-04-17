"""Hygiene tools: run_hygiene."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import hygiene as hygiene_engine
from graphbase_memories.mcp.schemas import MemoryScope
from graphbase_memories.mcp.schemas.results import HygieneReport
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def run_hygiene(
    ctx: Context,
    project_id: str | None = None,
    scope: MemoryScope | None = None,
    check_pending_only: bool = False,
) -> HygieneReport:
    """
    Run the memory hygiene cycle for a project or globally (FR-58-61).

    When check_pending_only=True: skips all content scans and returns only
    pending/failed write state (replaces the removed get_save_status tool).
    Does NOT update last_hygiene_at or run token cleanup in this mode.

    Full scan detects: duplicate decisions, outdated decisions (>180d),
    obsolete patterns (>90d), entity fact drift, and unresolved save failures.
    Returns a HygieneReport with candidate node IDs. Does NOT auto-mutate — all
    changes must be applied explicitly by the caller after reviewing the report.
    """
    driver = ctx.lifespan_context["driver"]
    return await hygiene_engine.run(
        project_id=project_id,
        scope=(scope.value if scope else "global"),
        driver=driver,
        database=settings.neo4j_database,
        check_pending_only=check_pending_only,
    )
