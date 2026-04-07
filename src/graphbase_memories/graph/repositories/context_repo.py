"""Context repository."""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from neo4j import AsyncDriver

from graphbase_memories.graph.models import ContextNode


async def create(
    *,
    content: str,
    topic: str,
    scope: str,
    relevance_score: float,
    project_id: str,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> ContextNode:
    context_id = str(uuid.uuid4())

    async def _tx(tx):
        await tx.run(
            "MERGE (p:Project {id: $pid}) ON CREATE SET p.name = $pid, p.created_at = datetime()",
            pid=project_id,
        )
        scope_query = (
            "MATCH (g:GlobalScope {id: 'global'}) WITH c, g MERGE (c)-[:BELONGS_TO]->(g)"
            if scope == "global"
            else "MATCH (proj:Project {id: $project_id}) MERGE (c)-[:BELONGS_TO]->(proj)"
        )
        await tx.run(
            f"""
            CREATE (c:Context {{
              id: $id, content: $content, topic: $topic,
              scope: $scope, relevance_score: $relevance_score, created_at: datetime()
            }})
            WITH c
            {scope_query}
            """,
            id=context_id,
            content=content,
            topic=topic,
            scope=scope,
            relevance_score=relevance_score,
            project_id=project_id,
        )
        if focus and scope != "global":
            focus_id = f"{project_id}::{focus}"
            await tx.run(
                """
                MERGE (f:FocusArea {id: $fid})
                ON CREATE SET f.name = $name, f.project_id = $pid, f.created_at = datetime()
                WITH f
                MATCH (c:Context {id: $cid}), (p:Project {id: $pid})
                MERGE (f)-[:BELONGS_TO]->(p)
                MERGE (c)-[:HAS_FOCUS]->(f)
                """,
                fid=focus_id,
                name=focus,
                pid=project_id,
                cid=context_id,
            )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)

    return ContextNode(
        id=context_id,
        content=content,
        topic=topic,
        scope=scope,
        relevance_score=relevance_score,
        created_at=datetime.now(UTC),
    )
