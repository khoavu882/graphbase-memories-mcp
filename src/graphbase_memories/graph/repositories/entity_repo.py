"""
Entity repository — M-2: typed EntityRelation with relationship_type.
Handles MERGE (upsert) for EntityFact nodes and typed relationship creation.

Fix C2: execute_write discards tx return value — restructured to always SET e.id = $id
         so the passed-in entity_id is the canonical id for both CREATE and MATCH paths.
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from neo4j import AsyncDriver

from graphbase_memories.graph.models import EntityFactNode

ALLOWED_RELATIONSHIPS = {
    "BELONGS_TO",
    "CONFLICTS_WITH",
    "PRODUCED",
    "MERGES_INTO",
    # topology relationships
    "PRODUCES",   # Service → KafkaTopic (producer)
    "CONSUMES",   # Service → KafkaTopic (consumer)
    "READS",      # Service → DBTable
    "WRITES",     # Service → DBTable
    "INVOLVES",   # Feature → Service
}


async def upsert(
    *,
    entity_name: str,
    fact: str,
    scope: str,
    project_id: str,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> EntityFactNode:
    entity_id = str(uuid.uuid4())

    async def _tx(tx):
        # ON CREATE: set id to the new uuid. ON MATCH: preserve existing id by re-setting it
        # (SET e.id = e.id is a no-op — but we use COALESCE to keep existing id on match).
        # This avoids depending on execute_write return value (which the driver discards).
        #
        # Project lookup: try direct id match first, then workspace_id match.
        # This handles the case where project_id is a workspace id (e.g. "timo-platform"),
        # in which case we link to ANY project that belongs to that workspace.
        await tx.run(
            """
            MERGE (e:EntityFact {entity_name: $entity_name, scope: $scope})
            ON CREATE SET e.id = $id, e.created_at = datetime()
            SET e.fact = $fact
            WITH e
            OPTIONAL MATCH (proj_direct:Project {id: $project_id})
            WITH e, proj_direct
            OPTIONAL MATCH (proj_via_ws:Project {workspace_id: $project_id})
              WHERE proj_direct IS NULL
            WITH e, coalesce(proj_direct, proj_via_ws) AS proj
            FOREACH (_ IN CASE WHEN proj IS NOT NULL THEN [1] ELSE [] END |
              MERGE (e)-[:BELONGS_TO]->(proj)
            )
            """,
            id=entity_id,
            entity_name=entity_name,
            fact=fact,
            scope=scope,
            project_id=project_id,
        )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)

    # Read back the actual id (may differ from entity_id if node already existed)
    async with driver.session(database=database) as session:
        result = await session.run(
            "MATCH (e:EntityFact {entity_name: $name, scope: $scope}) RETURN e.id AS id LIMIT 1",
            name=entity_name,
            scope=scope,
        )
        record = await result.single()
        actual_id = record["id"] if record else entity_id

    return EntityFactNode(
        id=actual_id,
        entity_name=entity_name,
        fact=fact,
        scope=scope,
        normalized_at=None,
        created_at=datetime.now(UTC),
    )


async def link_entities(
    from_id: str,
    to_id: str,
    relationship_type: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> None:
    if relationship_type not in ALLOWED_RELATIONSHIPS:
        raise ValueError(
            f"Invalid relationship_type: {relationship_type!r}. Allowed: {ALLOWED_RELATIONSHIPS}"
        )

    # Safe: relationship_type is whitelisted above before interpolation
    query = f"""
        MATCH (a:EntityFact {{id: $from_id}})
        MATCH (b:EntityFact {{id: $to_id}})
        MERGE (a)-[:{relationship_type}]->(b)
    """
    async with driver.session(database=database) as session:
        await session.run(query, from_id=from_id, to_id=to_id)
