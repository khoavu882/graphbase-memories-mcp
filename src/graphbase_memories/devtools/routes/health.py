"""Graph health routes — node/relationship counts, workspace health, conflict detection."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from neo4j import AsyncDriver

from graphbase_memories.config import settings
from graphbase_memories.engines import impact as impact_engine

router = APIRouter(tags=["health"])

_NODE_LABELS = [
    "Project", "Session", "Decision", "Pattern",
    "Context", "EntityFact", "Workspace", "ImpactEvent",
]
_REL_TYPES = ["BELONGS_TO", "CROSS_SERVICE_LINK", "IMPACT_OF"]


def _get_driver() -> AsyncDriver:
    from graphbase_memories.devtools.server import _get_driver as _gd

    return _gd()


@router.get("/graph/stats")
async def graph_stats():
    """Return node counts by label and relationship counts by type."""
    now = datetime.now(UTC)
    node_counts: dict[str, int] = {}
    rel_counts: dict[str, int] = {}

    async with _get_driver().session(database=settings.neo4j_database) as session:
        for lbl in _NODE_LABELS:
            res = await session.run(f"MATCH (n:{lbl}) RETURN count(n) AS cnt")
            rec = await res.single()
            node_counts[lbl] = rec["cnt"] if rec else 0

        for rt in _REL_TYPES:
            res = await session.run(f"MATCH ()-[r:{rt}]->() RETURN count(r) AS cnt")
            rec = await res.single()
            rel_counts[rt] = rec["cnt"] if rec else 0

    return {
        "node_counts": node_counts,
        "relationship_counts": rel_counts,
        "checked_at": now.isoformat(),
    }


@router.get("/graph/stats/workspace/{workspace_id}")
async def workspace_health(workspace_id: str):
    """Return health metrics for all services in a workspace."""
    try:
        report = await impact_engine.graph_health(
            workspace_id, _get_driver(), settings.neo4j_database
        )
        return report.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/graph/conflicts/{workspace_id}")
async def workspace_conflicts(workspace_id: str, limit: int = 100):
    """Return all CONTRADICTS cross-service links in a workspace."""
    try:
        conflicts = await impact_engine.detect_conflicts(
            workspace_id, limit, _get_driver(), settings.neo4j_database
        )
        return [c.model_dump() for c in conflicts]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
