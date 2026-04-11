"""
Impact repository — BFS neighbor fetching and ImpactEvent writes.

B-3: fetch_batch_neighbors uses a single Cypher round-trip per BFS depth level,
     querying all frontier nodes at once via WHERE src.id IN $node_ids.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from neo4j import AsyncDriver

from graphbase_memories.graph.driver import IMPACT_QUERIES
from graphbase_memories.graph.models import ImpactEventNode


def _query(name: str) -> str:
    pattern = rf"//\s*==\s*{re.escape(name)}\s*==\s*\n(.*?)(?=\n//\s*==|\Z)"
    m = re.search(pattern, IMPACT_QUERIES, re.DOTALL)
    if not m:
        raise KeyError(f"Query block '{name}' not found in impact.cypher")
    return m.group(1).strip().rstrip(";")


_BATCH_NEIGHBORS = _query("BATCH_NEIGHBORS")
_WRITE_IMPACT_EVENT = _query("WRITE_IMPACT_EVENT")
_GRAPH_HEALTH = _query("GRAPH_HEALTH")
_DETECT_CONFLICTS = _query("DETECT_CONFLICTS")


@dataclass
class NeighborRecord:
    id: str
    project_id: str
    edge_type: str


async def fetch_batch_neighbors(
    node_ids: list[str],
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[NeighborRecord]:
    """
    Return all cross-service neighbors reachable from any node in node_ids.
    Guards against empty input (an empty IN [] is a valid no-op in Cypher,
    but we skip the round-trip entirely as an optimisation).
    """
    if not node_ids:
        return []
    async with driver.session(database=database) as session:
        result = await session.run(_BATCH_NEIGHBORS, node_ids=node_ids)
        records = await result.data()
    return [
        NeighborRecord(id=r["id"], project_id=r["project_id"], edge_type=r["edge_type"])
        for r in records
    ]


async def write_impact_event(
    *,
    event_id: str,
    source_entity_id: str,
    source_project_id: str,
    change_description: str,
    impact_type: str,
    risk_level: str,
    affected: list[dict],
    driver: AsyncDriver,
    database: str = "neo4j",
) -> ImpactEventNode:
    """
    Write an ImpactEvent node and [:AFFECTS] edges inside a single transaction.
    affected format: [{"project_id": str, "depth": int, "risk_level": str}]
    Returns ImpactEventNode via explicit read-back (execute_write discards return).
    """
    affected_count = len(affected)

    async def _tx(tx):
        await tx.run(
            _WRITE_IMPACT_EVENT,
            event_id=event_id,
            source_entity_id=source_entity_id,
            source_project_id=source_project_id,
            change_description=change_description,
            impact_type=impact_type,
            risk_level=risk_level,
            affected_count=affected_count,
            affected=affected,
        )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)

    async with driver.session(database=database) as session:
        result = await session.run("MATCH (ie:ImpactEvent {id: $eid}) RETURN ie", eid=event_id)
        record = await result.single()

    if record is None:
        raise RuntimeError(f"ImpactEvent write failed — node not found after write: {event_id!r}")
    return ImpactEventNode.from_record(dict(record["ie"]))


async def graph_health(
    *,
    workspace_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[dict]:
    """Return per-service health stats for all services in the workspace."""
    async with driver.session(database=database) as session:
        result = await session.run(_GRAPH_HEALTH, workspace_id=workspace_id)
        return await result.data()


async def detect_conflicts(
    *,
    workspace_id: str,
    limit: int,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[dict]:
    """Return CONTRADICTS cross-service links between services in the workspace."""
    async with driver.session(database=database) as session:
        result = await session.run(_DETECT_CONFLICTS, workspace_id=workspace_id, limit=limit)
        return await result.data()
