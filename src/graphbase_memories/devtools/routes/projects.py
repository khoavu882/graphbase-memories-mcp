"""Project registry routes — list and detail with staleness and node counts."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from graphbase_memories.config import settings
from graphbase_memories.devtools.deps import DriverDep
from graphbase_memories.devtools.utils import staleness

router = APIRouter(tags=["projects"])


@router.get("/projects")
async def list_projects(driver: DriverDep):
    """List all Project nodes with node counts and staleness indicators."""
    now = datetime.now(UTC)
    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(
            """
            MATCH (p:Project)
            WITH p ORDER BY p.created_at DESC LIMIT 50
            OPTIONAL MATCH (n)-[rel]->(p)
            WHERE type(rel) = "BELONGS_TO"
            RETURN p {.*} AS project,
                   count(DISTINCT CASE WHEN n IS NOT NULL AND "Session" IN labels(n) THEN n END) AS sessions,
                   count(DISTINCT CASE WHEN n IS NOT NULL AND "Decision" IN labels(n) THEN n END) AS decisions,
                   count(DISTINCT CASE WHEN n IS NOT NULL AND "Pattern" IN labels(n) THEN n END) AS patterns,
                   count(DISTINCT CASE WHEN n IS NOT NULL AND "Context" IN labels(n) THEN n END) AS contexts,
                   count(DISTINCT CASE WHEN n IS NOT NULL AND "EntityFact" IN labels(n) THEN n END) AS entities
            """
        )
        projects = []
        async for r in result:
            p = dict(r["project"])
            staleness_days, is_stale = staleness(p.get("last_seen"), now)
            projects.append(
                {
                    **p,
                    "staleness_days": staleness_days,
                    "is_stale": is_stale,
                    "node_counts": {
                        "Session": r["sessions"],
                        "Decision": r["decisions"],
                        "Pattern": r["patterns"],
                        "Context": r["contexts"],
                        "EntityFact": r["entities"],
                    },
                }
            )
    return projects


@router.get("/projects/{project_id}")
async def get_project(project_id: str, driver: DriverDep):
    """Get a single Project node by id."""
    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (p:Project {id: $id}) RETURN p {.*} AS project LIMIT 1",
            id=project_id,
        )
        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
        return dict(record["project"])
