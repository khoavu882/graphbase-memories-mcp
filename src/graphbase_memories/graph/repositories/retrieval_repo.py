"""
Retrieval query repository — scope-layered graph traversal queries.

Owns the three core structural queries (focus / project / global) that the
RetrievalEngine uses for priority-merge retrieval. The label filter is also
defined here since it directly shapes query construction.

Note: functions accept a Neo4j AsyncSession (not AsyncDriver + database) so
all three queries can share a single session in _fetch_all, minimising
connection overhead.
"""

from __future__ import annotations

from neo4j import AsyncSession


def label_filter(categories: list[str] | None) -> str:
    """Produce a safe Cypher label filter string from a category list.

    Returns a string like `:Decision|Pattern` or empty string.
    Only labels in the explicit allowlist are accepted — all others are dropped.
    """
    if not categories:
        return ""
    allowed = {"Session", "Decision", "Pattern", "Context", "EntityFact"}
    safe = [c for c in categories if c in allowed]
    if not safe:
        return ""
    return ":" + "|".join(safe)


async def query_focus(
    session: AsyncSession,
    project_id: str,
    focus: str,
    categories: list[str] | None,
    limit: int,
) -> list[dict]:
    """Return nodes linked to a specific FocusArea, ordered by recency."""
    lf = label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{lf})-[:HAS_FOCUS]->(f:FocusArea {{name: $focus, project_id: $pid}})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT $limit
        """,
        focus=focus,
        pid=project_id,
        limit=limit,
    )
    return [_to_raw(r) async for r in result]


async def query_project(
    session: AsyncSession,
    project_id: str,
    categories: list[str] | None,
    limit: int,
) -> list[dict]:
    """Return project-scoped nodes, excluding superseded decisions."""
    lf = label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{lf})-[:BELONGS_TO]->(p:Project {{id: $pid}})
        WHERE NOT (n:Decision AND EXISTS {{ MATCH (:Decision)-[:SUPERSEDES]->(n) }})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT $limit
        """,
        pid=project_id,
        limit=limit,
    )
    return [_to_raw(r) async for r in result]


async def query_global(
    session: AsyncSession,
    categories: list[str] | None,
    limit: int,
) -> list[dict]:
    """Return global-scope nodes, excluding superseded decisions."""
    lf = label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{lf})-[:BELONGS_TO]->(g:GlobalScope)
        WHERE NOT (n:Decision AND EXISTS {{ MATCH (:Decision)-[:SUPERSEDES]->(n) }})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT $limit
        """,
        limit=limit,
    )
    return [_to_raw(r) async for r in result]


def _to_raw(record) -> dict:
    node = dict(record["node"])
    node["_label"] = record["label"]
    return node
