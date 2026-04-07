"""
RetrievalEngine — priority merge (focus > project > global), 5s timeout, 1 retry.
M-4: sets hygiene_due=True if project.last_hygiene_at > 30 days ago.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging

from neo4j import AsyncDriver

from graphbase_memories.config import settings
from graphbase_memories.engines import scope as scope_engine
from graphbase_memories.mcp.schemas.enums import RetrievalStatus
from graphbase_memories.mcp.schemas.results import ContextBundle

logger = logging.getLogger(__name__)


async def execute(
    *,
    project_id: str,
    scope: str,
    focus: str | None,
    categories: list[str] | None,
    topic: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> ContextBundle:
    """
    FR-15 to FR-24: retrieve context with priority merge and timeout/retry.
    Returns ContextBundle regardless of retrieval outcome (FR-46, FR-47).
    """
    scope_state = await scope_engine.validate(project_id, focus, driver, database)

    if not scope_engine.is_read_allowed(scope_state):
        return ContextBundle(
            items=[],
            retrieval_status=RetrievalStatus.empty,
            scope_state=scope_state,
        )

    for attempt in range(settings.retrieval_max_retries + 1):
        try:
            items = await asyncio.wait_for(
                _fetch_all(
                    project_id=project_id,
                    scope=scope,
                    focus=focus,
                    categories=categories,
                    topic=topic,
                    driver=driver,
                    database=database,
                ),
                timeout=settings.retrieval_timeout_s,
            )
            hygiene_due = await _check_hygiene_due(project_id, driver, database)
            conflicts = _has_conflicts(items)

            status = RetrievalStatus.empty if not items else RetrievalStatus.succeeded
            if conflicts:
                status = RetrievalStatus.conflicted

            return ContextBundle(
                items=items,
                retrieval_status=status,
                scope_state=scope_state,
                conflicts_found=conflicts,
                hygiene_due=hygiene_due,
            )

        except TimeoutError:
            if attempt < settings.retrieval_max_retries:
                continue
            return ContextBundle(
                items=[],
                retrieval_status=RetrievalStatus.timed_out,
                scope_state=scope_state,
            )
        except Exception:
            logger.exception("Retrieval failed on attempt %d", attempt + 1)
            if attempt < settings.retrieval_max_retries:
                continue
            return ContextBundle(
                items=[],
                retrieval_status=RetrievalStatus.failed,
                scope_state=scope_state,
            )

    return ContextBundle(
        items=[],
        retrieval_status=RetrievalStatus.failed,
        scope_state=scope_state,
    )


async def _fetch_all(
    *,
    project_id: str,
    scope: str,
    focus: str | None,
    categories: list[str] | None,
    topic: str | None,
    driver: AsyncDriver,
    database: str,
) -> list[dict]:
    """Priority merge: focus > project > global."""
    items: list[dict] = []
    seen_ids: set[str] = set()

    async with driver.session(database=database) as session:
        # Focus-level items first (highest priority)
        if focus and scope in ("focus", "project"):
            items += await _query_focus(session, project_id, focus, categories)

        # Project-level items
        if scope in ("focus", "project"):
            items += await _query_project(session, project_id, categories)

        # Global items last (lowest priority)
        if scope in ("focus", "project", "global"):
            items += await _query_global(session, categories)

    # Deduplicate by id, preserve priority order
    unique: list[dict] = []
    for item in items:
        if item.get("id") not in seen_ids:
            seen_ids.add(item.get("id"))
            unique.append(item)

    return unique


async def _query_focus(
    session, project_id: str, focus: str, categories: list[str] | None
) -> list[dict]:
    label_filter = _label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{label_filter})-[:HAS_FOCUS]->(f:FocusArea {{name: $focus, project_id: $pid}})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT 10
        """,
        focus=focus,
        pid=project_id,
    )
    return [_to_dict(r) async for r in result]


async def _query_project(session, project_id: str, categories: list[str] | None) -> list[dict]:
    label_filter = _label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{label_filter})-[:BELONGS_TO]->(p:Project {{id: $pid}})
        WHERE NOT (n:Decision AND EXISTS {{ MATCH (:Decision)-[:SUPERSEDES]->(n) }})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT 20
        """,
        pid=project_id,
    )
    return [_to_dict(r) async for r in result]


async def _query_global(session, categories: list[str] | None) -> list[dict]:
    label_filter = _label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{label_filter})-[:BELONGS_TO]->(g:GlobalScope)
        WHERE NOT (n:Decision AND EXISTS {{ MATCH (:Decision)-[:SUPERSEDES]->(n) }})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT 5
        """,
    )
    return [_to_dict(r) async for r in result]


def _label_filter(categories: list[str] | None) -> str:
    if not categories:
        return ""
    # Whitelist allowed labels to prevent injection
    allowed = {"Session", "Decision", "Pattern", "Context", "EntityFact"}
    safe = [c for c in categories if c in allowed]
    if not safe:
        return ""
    return ":" + "|".join(safe)


def _to_dict(record) -> dict:
    node = dict(record["node"])
    node["_label"] = record["label"]
    return node


def _has_conflicts(items: list[dict]) -> bool:
    # Simplistic check: if any item has conflict_count > 0 this would be set
    # Conflict detection happens at write time via [:CONFLICTS_WITH] edges
    # For retrieval, we return False by default (conflicts surfaced on hygiene run)
    return False


async def _check_hygiene_due(project_id: str, driver: AsyncDriver, database: str) -> bool:
    """M-4: returns True if project hygiene is overdue (>30 days)."""
    async with driver.session(database=database) as session:
        result = await session.run(
            "MATCH (p:Project {id: $pid}) RETURN p.last_hygiene_at AS ts LIMIT 1",
            pid=project_id,
        )
        record = await result.single()
        if not record or record["ts"] is None:
            return True  # never run = overdue
        threshold = datetime.now(UTC) - timedelta(days=30)
        last = record["ts"].to_native() if hasattr(record["ts"], "to_native") else record["ts"]
        return last < threshold
