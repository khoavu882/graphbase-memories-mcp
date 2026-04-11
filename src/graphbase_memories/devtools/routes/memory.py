"""Memory inspection routes — list, get, search, and relationship traversal."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from neo4j import AsyncDriver
from pydantic import BaseModel

from graphbase_memories.config import settings

router = APIRouter(tags=["memory"])

_ALLOWED_LABELS = {"Session", "Decision", "Pattern", "Context", "EntityFact"}


def _get_driver() -> AsyncDriver:
    from graphbase_memories.devtools.server import _get_driver as _gd

    return _gd()


@router.get("/memory")
async def list_memory(
    project_id: str = Query(None),
    label: str = Query(None, description="Node label: Session, Decision, Pattern, Context, EntityFact"),
    limit: int = Query(20, ge=1, le=100),
):
    """List recent memory nodes, optionally filtered by project and label."""
    label_clause = f":{label}" if label in _ALLOWED_LABELS else ""
    project_clause = (
        "AND EXISTS { MATCH (n)-[:BELONGS_TO]->(:Project {id: $pid}) }" if project_id else ""
    )
    async with _get_driver().session(database=settings.neo4j_database) as session:
        result = await session.run(
            f"""
            MATCH (n{label_clause})
            WHERE 1=1 {project_clause}
            RETURN n {{.*}} AS node, labels(n)[0] AS label
            ORDER BY n.created_at DESC LIMIT $limit
            """,
            pid=project_id,
            limit=limit,
        )
        nodes = []
        async for r in result:
            item = dict(r["node"])
            item["_label"] = r["label"]
            nodes.append(item)
    return nodes


@router.get("/memory/{node_id}/relationships")
async def node_relationships(node_id: str):
    """Return incoming and outgoing relationships for any memory node."""
    async with _get_driver().session(database=settings.neo4j_database) as session:
        node_result = await session.run(
            "MATCH (n {id: $id}) RETURN n {.*} AS node, labels(n)[0] AS label LIMIT 1",
            id=node_id,
        )
        record = await node_result.single()
        if not record:
            raise HTTPException(status_code=404, detail=f"Node {node_id!r} not found")
        node_data = dict(record["node"])
        node_data["_label"] = record["label"]

        out_result = await session.run(
            """
            MATCH (n {id: $id})-[r]->(m)
            RETURN type(r) AS rel_type, m.id AS to_id,
                   labels(m)[0] AS to_label, m.title AS to_title
            LIMIT 50
            """,
            id=node_id,
        )
        outgoing = [
            {
                "to_id": r["to_id"],
                "to_label": r["to_label"],
                "type": r["rel_type"],
                "to_title": r["to_title"],
            }
            async for r in out_result
        ]

        in_result = await session.run(
            """
            MATCH (m)-[r]->(n {id: $id})
            RETURN type(r) AS rel_type, m.id AS from_id,
                   labels(m)[0] AS from_label, m.title AS from_title
            LIMIT 50
            """,
            id=node_id,
        )
        incoming = [
            {
                "from_id": r["from_id"],
                "from_label": r["from_label"],
                "type": r["rel_type"],
                "from_title": r["from_title"],
            }
            async for r in in_result
        ]

    return {"node": node_data, "outgoing": outgoing, "incoming": incoming}


@router.get("/memory/{node_id}")
async def get_node(node_id: str):
    """Get a single memory node by id."""
    async with _get_driver().session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (n {id: $id}) RETURN n {.*} AS node, labels(n)[0] AS label LIMIT 1",
            id=node_id,
        )
        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
        item = dict(record["node"])
        item["_label"] = record["label"]
        return item


class MemorySearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    label: str | None = None
    limit: int = 20
    since_days: int | None = None


@router.post("/memory/search")
async def search_memory(body: MemorySearchRequest):
    """Full-text search across memory nodes using CONTAINS on content fields."""
    label_clause = f":{body.label}" if body.label in _ALLOWED_LABELS else ""
    project_clause = (
        "AND EXISTS { MATCH (n)-[:BELONGS_TO]->(:Project {id: $pid}) }"
        if body.project_id
        else ""
    )
    since_clause = (
        "AND n.created_at > datetime() - duration({days: $since_days})"
        if body.since_days
        else ""
    )
    async with _get_driver().session(database=settings.neo4j_database) as session:
        result = await session.run(
            f"""
            MATCH (n{label_clause})
            WHERE (
                n.content CONTAINS $search_text
                OR n.title CONTAINS $search_text
                OR n.summary CONTAINS $search_text
                OR n.entity_name CONTAINS $search_text
                OR n.fact CONTAINS $search_text
            )
            {project_clause}
            {since_clause}
            RETURN n {{.*}} AS node, labels(n)[0] AS label
            ORDER BY n.created_at DESC
            LIMIT $limit
            """,
            search_text=body.query,
            pid=body.project_id,
            since_days=body.since_days,
            limit=body.limit,
        )
        nodes = []
        async for r in result:
            item = dict(r["node"])
            item["_label"] = r["label"]
            nodes.append(item)
    return nodes
