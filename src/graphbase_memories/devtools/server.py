"""
Devtools HTTP inspection server — minimal FastAPI app for human memory browsing.
Start with: graphbase-memories-mcp devtools --port 8765
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from neo4j import AsyncDriver, AsyncGraphDatabase

from graphbase_memories.config import settings
from graphbase_memories.graph.driver import SCHEMA_DDL, split_statements

_driver: AsyncDriver | None = None


def _get_driver() -> AsyncDriver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized — lifespan not started")
    return _driver


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _driver
    _driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        max_connection_pool_size=settings.neo4j_max_pool_size,
    )
    await _driver.verify_connectivity()
    async with _get_driver().session(database=settings.neo4j_database) as session:
        for stmt in split_statements(SCHEMA_DDL):
            await session.run(stmt)
    yield
    await _driver.close()


app = FastAPI(
    title="graphbase-memories devtools",
    description="HTTP interface for inspecting graph memory nodes",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Check Neo4j connectivity."""
    try:
        await _get_driver().verify_connectivity()
        return {"status": "ok", "neo4j_uri": settings.neo4j_uri}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@app.get("/projects")
async def list_projects():
    """List all registered Project nodes."""
    async with _get_driver().session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (p:Project) RETURN p {.*} AS project ORDER BY p.created_at DESC LIMIT 50"
        )
        return [dict(r["project"]) async for r in result]


@app.get("/memory")
async def list_memory(
    project_id: str = Query(None),
    label: str = Query(
        None, description="Node label: Session, Decision, Pattern, Context, EntityFact"
    ),
    limit: int = Query(20, ge=1, le=100),
):
    """List recent memory nodes, optionally filtered by project and label."""
    allowed_labels = {"Session", "Decision", "Pattern", "Context", "EntityFact"}
    label_clause = f":{label}" if label in allowed_labels else ""
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


@app.get("/memory/{node_id}")
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
