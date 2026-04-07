"""Session repository — CRUD for Session nodes."""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from neo4j import AsyncDriver

from graphbase_memories.graph.models import SessionNode


async def create(
    *,
    objective: str,
    actions_taken: list[str],
    decisions_made: list[str],
    open_items: list[str],
    next_actions: list[str],
    save_scope: str,
    project_id: str,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> SessionNode:
    session_id = str(uuid.uuid4())

    async def _tx(tx):
        # Ensure project exists
        await tx.run(
            "MERGE (p:Project {id: $pid}) ON CREATE SET p.name = $pid, p.created_at = datetime()",
            pid=project_id,
        )
        # Create session + link to project
        await tx.run(
            """
            CREATE (s:Session {
              id: $id, objective: $objective,
              actions_taken: $actions_taken, decisions_made: $decisions_made,
              open_items: $open_items, next_actions: $next_actions,
              save_scope: $save_scope, status: 'saved', created_at: datetime()
            })
            WITH s
            MATCH (p:Project {id: $project_id})
            MERGE (s)-[:BELONGS_TO]->(p)
            """,
            id=session_id,
            objective=objective,
            actions_taken=actions_taken,
            decisions_made=decisions_made,
            open_items=open_items,
            next_actions=next_actions,
            save_scope=save_scope,
            project_id=project_id,
        )
        if focus:
            focus_id = f"{project_id}::{focus}"
            await tx.run(
                """
                MERGE (f:FocusArea {id: $fid})
                ON CREATE SET f.name = $name, f.project_id = $pid, f.created_at = datetime()
                WITH f
                MATCH (s:Session {id: $sid}), (p:Project {id: $pid})
                MERGE (f)-[:BELONGS_TO]->(p)
                MERGE (s)-[:HAS_FOCUS]->(f)
                """,
                fid=focus_id,
                name=focus,
                pid=project_id,
                sid=session_id,
            )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)

    return SessionNode(
        id=session_id,
        objective=objective,
        actions_taken=actions_taken,
        decisions_made=decisions_made,
        open_items=open_items,
        next_actions=next_actions,
        save_scope=save_scope,
        status="saved",
        created_at=datetime.now(UTC),
    )


async def link_produced(
    session_id: str,
    artifact_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> None:
    async def _tx(tx):
        await tx.run(
            """
            MATCH (s:Session {id: $sid}), (a {id: $aid})
            MERGE (s)-[:PRODUCED]->(a)
            """,
            sid=session_id,
            aid=artifact_id,
        )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)


async def get_pending(
    project_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[dict]:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (s:Session)-[:BELONGS_TO]->(p:Project {id: $pid})
            WHERE s.status IN ['pending_retry', 'failed', 'partial']
            RETURN s.id AS id, s.status AS status, s.created_at AS created_at
            ORDER BY s.created_at DESC LIMIT 20
            """,
            pid=project_id,
        )
        return [dict(r) async for r in result]
