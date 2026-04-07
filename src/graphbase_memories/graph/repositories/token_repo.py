"""
GovernanceToken repository — S-1: tokens stored in Neo4j, not in-memory.
Durable across process restarts. Scoped to content_preview.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

from neo4j import AsyncDriver

from graphbase_memories.graph.models import GovernanceTokenNode


async def create(
    content_preview: str,
    ttl_s: int,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> GovernanceTokenNode:
    token_id = str(uuid.uuid4())
    expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_s)).isoformat()

    async with driver.session(database=database) as session:
        await session.run(
            """
            CREATE (t:GovernanceToken {
              id: $id,
              content_preview: $content_preview,
              expires_at: datetime($expires_at),
              used: false,
              created_at: datetime()
            })
            """,
            id=token_id,
            content_preview=content_preview,
            expires_at=expires_at,
        )

    return GovernanceTokenNode(
        id=token_id,
        content_preview=content_preview,
        expires_at=datetime.fromisoformat(expires_at),
    )


async def validate_and_consume(
    token_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> bool:
    """Returns True if token is valid and marks it as used. False otherwise."""
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (t:GovernanceToken {id: $token_id})
            WHERE t.used = false AND t.expires_at > datetime()
            SET t.used = true
            RETURN t.id AS id
            """,
            token_id=token_id,
        )
        record = await result.single()
        return record is not None


async def cleanup_expired(driver: AsyncDriver, database: str = "neo4j") -> int:
    """Delete used or expired tokens. Returns count deleted."""
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (t:GovernanceToken)
            WHERE t.expires_at < datetime() OR t.used = true
            WITH t, t.id AS id
            DELETE t
            RETURN count(id) AS deleted
            """
        )
        record = await result.single()
        return record["deleted"] if record else 0
