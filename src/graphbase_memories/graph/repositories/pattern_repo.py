"""Pattern repository."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import re
import uuid

from neo4j import AsyncDriver

from graphbase_memories.graph.models import PatternNode


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_content_hash(trigger: str, steps: list[str]) -> str:
    normalized = _normalize(trigger + " " + " ".join(steps))
    return hashlib.sha256(normalized.encode()).hexdigest()


async def create(
    *,
    trigger: str,
    repeatable_steps: list[str],
    exclusions: list[str],
    scope: str,
    last_validated_at: str,
    project_id: str,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> PatternNode:
    pattern_id = str(uuid.uuid4())
    content_hash = compute_content_hash(trigger, repeatable_steps)
    steps_text = " ".join(repeatable_steps)

    async def _tx(tx):
        await tx.run(
            "MERGE (p:Project {id: $pid}) ON CREATE SET p.name = $pid, p.created_at = datetime()",
            pid=project_id,
        )
        scope_query = (
            "MATCH (g:GlobalScope {id: 'global'}) WITH p, g MERGE (p)-[:BELONGS_TO]->(g)"
            if scope == "global"
            else "MATCH (proj:Project {id: $project_id}) MERGE (p)-[:BELONGS_TO]->(proj)"
        )
        await tx.run(
            f"""
            CREATE (p:Pattern {{
              id: $id, trigger: $trigger,
              repeatable_steps: $steps, repeatable_steps_text: $steps_text,
              exclusions: $exclusions, scope: $scope,
              last_validated_at: datetime($last_validated_at),
              content_hash: $content_hash, created_at: datetime()
            }})
            WITH p
            {scope_query}
            """,
            id=pattern_id,
            trigger=trigger,
            steps=repeatable_steps,
            steps_text=steps_text,
            exclusions=exclusions,
            scope=scope,
            last_validated_at=last_validated_at,
            content_hash=content_hash,
            project_id=project_id,
        )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)

    return PatternNode(
        id=pattern_id,
        trigger=trigger,
        repeatable_steps=repeatable_steps,
        exclusions=exclusions,
        scope=scope,
        last_validated_at=datetime.fromisoformat(last_validated_at),
        content_hash=content_hash,
        created_at=datetime.now(UTC),
    )


async def find_by_hash(
    content_hash: str, scope: str, driver: AsyncDriver, database: str = "neo4j"
) -> dict | None:
    async with driver.session(database=database) as session:
        result = await session.run(
            "MATCH (p:Pattern {content_hash: $h, scope: $scope}) RETURN p.id AS id, p.trigger AS trigger LIMIT 1",
            h=content_hash,
            scope=scope,
        )
        record = await result.single()
        return dict(record) if record else None
