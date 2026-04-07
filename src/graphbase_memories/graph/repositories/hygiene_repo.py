"""Hygiene repository — read-only detection queries + last_hygiene_at update."""

from __future__ import annotations

from neo4j import AsyncDriver


async def find_duplicate_decisions(
    project_id: str | None, driver: AsyncDriver, database: str = "neo4j"
) -> list[dict]:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (d1:Decision), (d2:Decision)
            WHERE d1.content_hash = d2.content_hash AND d1.id < d2.id
              AND ($project_id IS NULL OR
                   EXISTS { MATCH (d1)-[:BELONGS_TO]->(:Project {id: $project_id}) })
            RETURN d1.id AS id1, d2.id AS id2, d1.title AS title LIMIT 50
            """,
            project_id=project_id,
        )
        return [dict(r) async for r in result]


async def find_outdated_decisions(
    project_id: str | None, driver: AsyncDriver, database: str = "neo4j"
) -> list[dict]:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (d:Decision)
            WHERE d.created_at < datetime() - duration({days: 180})
              AND NOT EXISTS { MATCH (d)-[:SUPERSEDES]->() }
              AND ($project_id IS NULL OR
                   EXISTS { MATCH (d)-[:BELONGS_TO]->(:Project {id: $project_id}) })
            RETURN d.id AS id, d.title AS title, d.created_at AS created_at
            ORDER BY d.created_at ASC LIMIT 20
            """,
            project_id=project_id,
        )
        return [dict(r) async for r in result]


async def find_obsolete_patterns(
    project_id: str | None, driver: AsyncDriver, database: str = "neo4j"
) -> list[dict]:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (p:Pattern)
            WHERE p.last_validated_at < datetime() - duration({days: 90})
              AND ($project_id IS NULL OR
                   EXISTS { MATCH (p)-[:BELONGS_TO]->(:Project {id: $project_id}) })
            RETURN p.id AS id, p.trigger AS trigger, p.last_validated_at AS last_validated_at
            ORDER BY p.last_validated_at ASC LIMIT 20
            """,
            project_id=project_id,
        )
        return [dict(r) async for r in result]


async def find_entity_drift(
    project_id: str | None, driver: AsyncDriver, database: str = "neo4j"
) -> list[dict]:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (e1:EntityFact), (e2:EntityFact)
            WHERE e1.entity_name = e2.entity_name AND e1.id < e2.id
              AND e1.scope = e2.scope
              AND ($project_id IS NULL OR
                   EXISTS { MATCH (e1)-[:BELONGS_TO]->(:Project {id: $project_id}) })
            RETURN e1.id AS id1, e2.id AS id2, e1.entity_name AS entity_name LIMIT 20
            """,
            project_id=project_id,
        )
        return [dict(r) async for r in result]


async def find_unresolved_saves(
    project_id: str | None, driver: AsyncDriver, database: str = "neo4j"
) -> list[dict]:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (s:Session)
            WHERE s.status IN ['pending_retry', 'failed', 'partial']
              AND ($project_id IS NULL OR
                   EXISTS { MATCH (s)-[:BELONGS_TO]->(:Project {id: $project_id}) })
            RETURN s.id AS id, 'Session' AS type, s.status AS status, s.created_at AS created_at
            ORDER BY s.created_at DESC LIMIT 20
            """,
            project_id=project_id,
        )
        return [dict(r) async for r in result]


async def update_hygiene_timestamp(
    project_id: str | None, driver: AsyncDriver, database: str = "neo4j"
) -> None:
    async with driver.session(database=database) as session:
        if project_id:
            await session.run(
                "MATCH (p:Project {id: $pid}) SET p.last_hygiene_at = datetime()",
                pid=project_id,
            )
        else:
            await session.run(
                "MATCH (g:GlobalScope {id: 'global'}) SET g.last_hygiene_at = datetime()"
            )
