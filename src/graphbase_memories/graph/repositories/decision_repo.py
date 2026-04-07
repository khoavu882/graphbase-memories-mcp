"""
Decision repository — includes S-2 content_hash generation for exact dedup.
content_hash = SHA-256 of normalized(title + rationale) — corpus-independent.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re
import uuid

from neo4j import AsyncDriver

from graphbase_memories.graph.models import DecisionNode


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_content_hash(title: str, rationale: str) -> str:
    normalized = _normalize(title + " " + rationale)
    return hashlib.sha256(normalized.encode()).hexdigest()


async def create(
    *,
    title: str,
    rationale: str,
    owner: str,
    date: str,
    scope: str,
    confidence: float,
    project_id: str,
    focus: str | None,
    dedup_status: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> DecisionNode:
    decision_id = str(uuid.uuid4())
    content_hash = compute_content_hash(title, rationale)

    async def _tx(tx):
        await tx.run(
            "MERGE (p:Project {id: $pid}) ON CREATE SET p.name = $pid, p.created_at = datetime()",
            pid=project_id,
        )
        scope_query = (
            "MATCH (g:GlobalScope {id: 'global'}) WITH d, g MERGE (d)-[:BELONGS_TO]->(g)"
            if scope == "global"
            else "MATCH (p:Project {id: $project_id}) MERGE (d)-[:BELONGS_TO]->(p)"
        )
        await tx.run(
            f"""
            CREATE (d:Decision {{
              id: $id, title: $title, rationale: $rationale,
              owner: $owner, date: date($date), scope: $scope,
              confidence: $confidence, content_hash: $content_hash,
              dedup_status: $dedup_status, created_at: datetime()
            }})
            WITH d
            {scope_query}
            """,
            id=decision_id,
            title=title,
            rationale=rationale,
            owner=owner,
            date=date,
            scope=scope,
            confidence=confidence,
            content_hash=content_hash,
            dedup_status=dedup_status,
            project_id=project_id,
        )
        if focus and scope != "global":
            focus_id = f"{project_id}::{focus}"
            await tx.run(
                """
                MERGE (f:FocusArea {id: $fid})
                ON CREATE SET f.name = $name, f.project_id = $pid, f.created_at = datetime()
                WITH f
                MATCH (d:Decision {id: $did}), (p:Project {id: $pid})
                MERGE (f)-[:BELONGS_TO]->(p)
                MERGE (d)-[:HAS_FOCUS]->(f)
                """,
                fid=focus_id,
                name=focus,
                pid=project_id,
                did=decision_id,
            )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)

    return DecisionNode(
        id=decision_id,
        title=title,
        rationale=rationale,
        owner=owner,
        date=datetime.fromisoformat(date).date() if isinstance(date, str) else date,
        scope=scope,
        confidence=confidence,
        content_hash=content_hash,
        dedup_status=dedup_status,
        created_at=datetime.now(UTC),
    )


async def add_supersedes(
    newer_id: str,
    older_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> None:
    async with driver.session(database=database) as session:
        await session.run(
            """
            MATCH (newer:Decision {id: $newer_id}), (older:Decision {id: $older_id})
            MERGE (newer)-[:SUPERSEDES]->(older)
            """,
            newer_id=newer_id,
            older_id=older_id,
        )


async def find_by_hash(
    content_hash: str,
    scope: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> dict | None:
    async with driver.session(database=database) as session:
        result = await session.run(
            "MATCH (d:Decision {content_hash: $h, scope: $scope}) RETURN d.id AS id, d.title AS title LIMIT 1",
            h=content_hash,
            scope=scope,
        )
        record = await result.single()
        return dict(record) if record else None


async def fulltext_candidates(
    query: str,
    scope: str,
    exclude_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[dict]:
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            CALL db.index.fulltext.queryNodes("decision_fulltext", $search_query)
            YIELD node, score
            WHERE node.scope = $scope AND node.id <> $exclude_id
            RETURN node.id AS id, node.title AS title, node.rationale AS rationale,
                   node.date AS date, score
            ORDER BY score DESC LIMIT 5
            """,
            search_query=query,
            scope=scope,
            exclude_id=exclude_id,
        )
        return [dict(r) async for r in result]
