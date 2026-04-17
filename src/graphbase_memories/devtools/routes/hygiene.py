"""Hygiene control routes — status overview and on-demand hygiene run."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from graphbase_memories.config import settings
from graphbase_memories.devtools.deps import DriverDep
from graphbase_memories.engines import hygiene as hygiene_engine

router = APIRouter(prefix="/hygiene", tags=["hygiene"])

_STALE_HYGIENE_DAYS = 30


@router.get("/status")
async def hygiene_status(driver: DriverDep):
    """Aggregate hygiene status and pending save count across all projects."""
    now = datetime.now(UTC)
    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (p:Project) RETURN p.id AS id, p.last_hygiene_at AS last_hygiene_at ORDER BY p.id"
        )
        projects = []
        async for r in result:
            raw = r["last_hygiene_at"]
            days_since = None
            if raw is not None:
                lh = raw.to_native() if hasattr(raw, "to_native") else raw
                days_since = round((now - lh).total_seconds() / 86400, 2)
            projects.append(
                {
                    "project_id": r["id"],
                    "last_hygiene_at": raw.isoformat() if raw is not None else None,
                    "days_since": days_since,
                    "needs_hygiene": days_since is None or days_since > _STALE_HYGIENE_DAYS,
                }
            )

        pending_result = await session.run(
            "MATCH (n {save_status: 'pending_retry'}) RETURN count(n) AS cnt"
        )
        pending_record = await pending_result.single()
        pending_total = pending_record["cnt"] if pending_record else 0

    return {
        "projects": projects,
        "pending_saves_total": pending_total,
        "checked_at": now.isoformat(),
    }


class HygieneRunRequest(BaseModel):
    project_id: str | None = None
    scope: str = "global"
    check_pending_only: bool = False


@router.post("/run")
async def run_hygiene(body: HygieneRunRequest, driver: DriverDep):
    """Run the memory hygiene cycle. Report-only — does not auto-mutate graph nodes.

    Set check_pending_only=true to skip all content scans and only return pending-save
    status. Does not update last_hygiene_at when check_pending_only is true.
    """
    report = await hygiene_engine.run(
        project_id=body.project_id,
        scope=body.scope,
        check_pending_only=body.check_pending_only,
        driver=driver,
        database=settings.neo4j_database,
    )
    return report.model_dump()
