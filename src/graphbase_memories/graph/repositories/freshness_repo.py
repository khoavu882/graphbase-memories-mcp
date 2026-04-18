"""
FreshnessRepo — stale memory node scan query.

Scans Decision, Pattern, Context, EntityFact nodes for a given project whose
most-recent timestamp (updated_at, fallback created_at) is older than
stale_after_days. Returns raw records; the FreshnessEngine builds StaleItem
objects and computes freshness labels from these records.
"""

from __future__ import annotations

from neo4j import AsyncDriver

_SCAN_QUERY = """
MATCH (n)
WHERE (n:Decision OR n:Pattern OR n:Context OR n:EntityFact)
  AND EXISTS {
    MATCH (n)-[:BELONGS_TO]->(p:Project {id: $project_id})
  }
WITH n,
     CASE WHEN n.updated_at IS NOT NULL THEN n.updated_at ELSE n.created_at END AS ts
WHERE ts IS NOT NULL
  AND ts < datetime() - duration({days: $stale_after_days})
OPTIONAL MATCH (n)-[:BELONGS_TO]->(proj:Project)
RETURN
  n.id AS node_id,
  CASE
    WHEN n:Decision   THEN "Decision"
    WHEN n:Pattern    THEN "Pattern"
    WHEN n:Context    THEN "Context"
    WHEN n:EntityFact THEN "EntityFact"
    ELSE "Unknown"
  END AS label,
  CASE
    WHEN n:Decision   THEN n.title
    WHEN n:Pattern    THEN n.trigger
    WHEN n:Context    THEN n.topic
    WHEN n:EntityFact THEN n.entity_name
    ELSE null
  END AS title,
  ts,
  proj.id AS project_id
ORDER BY ts ASC
LIMIT $scan_limit
"""


async def scan_stale_records(
    project_id: str,
    stale_after_days: int,
    scan_limit: int,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[dict]:
    """Execute the stale-node scan and return raw records as dicts.

    Each dict contains: node_id, label, title, ts (Neo4j DateTime), project_id.
    The caller (FreshnessEngine) is responsible for building typed result objects.
    """
    async with driver.session(database=database) as session:
        result = await session.run(
            _SCAN_QUERY,
            project_id=project_id,
            stale_after_days=stale_after_days,
            scan_limit=scan_limit,
        )
        return [dict(record) async for record in result]
