"""Hygiene tools: run_hygiene, get_save_status (S-4 replaces get_pending_saves)."""

from __future__ import annotations

from datetime import datetime

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import hygiene as hygiene_engine
from graphbase_memories.graph.repositories import session_repo
from graphbase_memories.mcp.schemas import MemoryScope
from graphbase_memories.mcp.schemas.enums import SaveStatus
from graphbase_memories.mcp.schemas.results import HygieneReport, SaveStatusSummary
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def run_hygiene(
    ctx: Context,
    project_id: str | None = None,
    scope: MemoryScope | None = None,
) -> HygieneReport:
    """
    Run the memory hygiene cycle for a project or globally (FR-58-61).

    Detects: duplicate decisions, outdated decisions (>180d), obsolete patterns (>90d),
    entity fact drift, and unresolved save failures.

    Returns a HygieneReport with candidate node IDs. Does NOT auto-mutate — all
    changes must be applied explicitly by the caller after reviewing the report.
    """
    driver = ctx.lifespan_context["driver"]
    return await hygiene_engine.run(
        project_id=project_id,
        scope=(scope.value if scope else "global"),
        driver=driver,
        database=settings.neo4j_database,
    )


@mcp.tool()
async def get_save_status(
    ctx: Context,
    project_id: str,
    session_id: str | None = None,
) -> SaveStatusSummary:
    """
    S-4: Typed replacement for raw get_pending_saves.
    Returns a SaveStatusSummary with count, oldest pending timestamp, and artifact IDs.
    """
    driver = ctx.lifespan_context["driver"]
    pending = await session_repo.get_pending(project_id, driver, settings.neo4j_database)

    if not pending:
        return SaveStatusSummary(status=SaveStatus.saved, count=0)

    artifact_ids = [r["id"] for r in pending]
    timestamps = [r["created_at"] for r in pending if r.get("created_at")]

    oldest = None
    if timestamps:
        raw = min(timestamps)
        oldest = raw.to_native() if hasattr(raw, "to_native") else raw
        if not isinstance(oldest, datetime):
            oldest = None

    return SaveStatusSummary(
        status=SaveStatus.pending_retry,
        count=len(pending),
        oldest_pending_at=oldest,
        artifact_ids=artifact_ids,
    )
