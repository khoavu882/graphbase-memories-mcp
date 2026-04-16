"""
Shared BM25 full-text search across the four memory node indexes.

Both RetrievalEngine and SurfaceEngine use the same four-index loop pattern.
This module provides a single implementation so divergence is impossible.

Design note: CALL UNION ALL is unreliable in Neo4j 5 Community, so we run
one session.run() per index and merge results in Python. Partial failures
(one index unavailable) are logged and skipped — callers always receive
whatever results are available.
"""

from __future__ import annotations

import logging

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

# (index_name, neo4j_label) — order determines merge priority when scores tie
_BM25_INDEXES = [
    ("decision_fulltext", "Decision"),
    ("pattern_fulltext", "Pattern"),
    ("context_fulltext", "Context"),
    ("entity_fulltext", "EntityFact"),
]


async def bm25_fetch(
    *,
    search_text: str,
    project_id: str | None,
    limit: int,
    driver: AsyncDriver,
    database: str,
) -> list[dict]:
    """
    Run BM25 across all four fulltext indexes and return merged, deduplicated results.

    Each returned dict contains all node properties plus:
      _label     — Neo4j label string (e.g. "Decision")
      bm25_score — float score from the fulltext index

    Results are deduplicated by node id. Items with no id are silently dropped.
    """
    all_items: list[dict] = []
    seen: set[str] = set()

    async with driver.session(database=database) as session:
        for index_name, _label in _BM25_INDEXES:
            try:
                # Traverse BELONGS_TO relationship to find project-scoped nodes.
                # Also match when project_id is a workspace_id (p.workspace_id).
                # Nodes with scope='global' are always included.
                # Falls back to returning all nodes when project_id is empty.
                result = await session.run(
                    "CALL db.index.fulltext.queryNodes($index_name, $search_text) "
                    "YIELD node, score "
                    "WHERE ("
                    "  node.scope = 'global' "
                    "  OR $project_id = '' "
                    "  OR EXISTS { "
                    "    MATCH (node)-[:BELONGS_TO]->(p:Project) "
                    "    WHERE p.id = $project_id OR p.workspace_id = $project_id "
                    "  } "
                    ") "
                    "RETURN node {.*} AS item, labels(node)[0] AS label, score AS bm25_score "
                    "ORDER BY bm25_score DESC LIMIT $limit",
                    index_name=index_name,
                    search_text=search_text,
                    project_id=project_id or "",
                    limit=limit,
                )
                async for record in result:
                    item = dict(record["item"])
                    uid = item.get("id")
                    if uid and uid not in seen:
                        seen.add(uid)
                        item["_label"] = record["label"]
                        item["bm25_score"] = float(record["bm25_score"])
                        all_items.append(item)
            except Exception:
                logger.warning("BM25 query failed for index %s — skipping", index_name)

    return all_items
