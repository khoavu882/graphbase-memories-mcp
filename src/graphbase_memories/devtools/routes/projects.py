"""Project registry routes — list and detail with staleness and node counts."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from neo4j import AsyncDriver

from graphbase_memories.config import settings
from graphbase_memories.devtools.utils import staleness

router = APIRouter(tags=["projects"])


def _get_driver() -> AsyncDriver:
    from graphbase_memories.devtools.server import _get_driver as _gd

    return _gd()


@router.get("/projects")
async def list_projects():
    """List all Project nodes with node counts and staleness indicators."""
    now = datetime.now(UTC)
    async with _get_driver().session(database=settings.neo4j_database) as session:
        result = await session.run(
            """
            MATCH (p:Project)
            WITH p ORDER BY p.created_at DESC LIMIT 50
            OPTIONAL MATCH (s:Session)-[:BELONGS_TO]->(p)
            OPTIONAL MATCH (d:Decision)-[:BELONGS_TO]->(p)
            OPTIONAL MATCH (pat:Pattern)-[:BELONGS_TO]->(p)
            OPTIONAL MATCH (c:Context)-[:BELONGS_TO]->(p)
            OPTIONAL MATCH (e:EntityFact)-[:BELONGS_TO]->(p)
            RETURN p {.*} AS project,
                   count(DISTINCT s) AS sessions,
                   count(DISTINCT d) AS decisions,
                   count(DISTINCT pat) AS patterns,
                   count(DISTINCT c) AS contexts,
                   count(DISTINCT e) AS entities
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
async def get_project(project_id: str):
    """Get a single Project node by id."""
    async with _get_driver().session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (p:Project {id: $id}) RETURN p {.*} AS project LIMIT 1",
            id=project_id,
        )
        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
        return dict(record["project"])
