"""
RetrievalEngine — priority merge (focus > project > global), 5s timeout, 1 retry.
M-4: sets hygiene_due=True if project.last_hygiene_at > 30 days ago.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import logging

from neo4j import AsyncDriver
from neo4j.exceptions import Neo4jError

from graphbase_memories.config import settings
from graphbase_memories.engines import scope as scope_engine
from graphbase_memories.engines.freshness import compute_freshness_str
from graphbase_memories.mcp.schemas.enums import RetrievalStatus
from graphbase_memories.mcp.schemas.results import ContextBundle

logger = logging.getLogger(__name__)


async def execute(
    *,
    project_id: str,
    scope: str,
    focus: str | None,
    categories: list[str] | None,
    keyword: str | None = None,
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
            items, truncated_scopes = await asyncio.wait_for(
                _fetch_all(
                    project_id=project_id,
                    scope=scope,
                    focus=focus,
                    categories=categories,
                    driver=driver,
                    database=database,
                ),
                timeout=settings.retrieval_timeout_s,
            )
            if keyword and settings.fts_enabled:
                fts_items = await _fetch_bm25(
                    project_id=project_id,
                    search_text=keyword,
                    driver=driver,
                    database=database,
                )
                items = _rrf_fuse(items, fts_items)
            hygiene_due = await _check_hygiene_due(project_id, driver, database)
            conflicts = _has_conflicts(items)

            status = RetrievalStatus.empty if not items else RetrievalStatus.succeeded
            if conflicts:
                status = RetrievalStatus.conflicted

            bundle = ContextBundle(
                items=items,
                retrieval_status=status,
                scope_state=scope_state,
                conflicts_found=conflicts,
                hygiene_due=hygiene_due,
                truncated_scopes=truncated_scopes,
            )
            bundle.next_step = _build_next_step(bundle, project_id)
            return bundle

        except TimeoutError:
            if attempt < settings.retrieval_max_retries:
                continue
            return ContextBundle(
                items=[],
                retrieval_status=RetrievalStatus.timed_out,
                scope_state=scope_state,
            )
        except Neo4jError:
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


def _build_next_step(bundle: ContextBundle, project_id: str) -> str:
    """Return a contextual next-step hint based on the bundle's retrieval state."""
    if bundle.conflicts_found:
        return (
            "Conflicts detected: call detect_conflicts(workspace_id=...) to resolve CONTRADICTS edges."
        )
    if bundle.hygiene_due:
        return f"Hygiene overdue: call run_hygiene(project_id='{project_id}') to clean stale nodes."
    if bundle.retrieval_status.value == "empty":
        return "No memories found. Try retrieve_context with scope='global' or a broader topic."
    if bundle.truncated_scopes:
        scopes = ", ".join(bundle.truncated_scopes)
        return f"Results truncated in: [{scopes}]. Narrow with focus= or categories= to get full results."
    return "Deepen with search_cross_service() or save new learnings with save_decision()."


async def _fetch_all(
    *,
    project_id: str,
    scope: str,
    focus: str | None,
    categories: list[str] | None,
    driver: AsyncDriver,
    database: str,
) -> tuple[list[dict], list[str]]:
    """Priority merge: focus > project > global. Returns (items, truncated_scopes)."""
    items: list[dict] = []
    seen_ids: set[str] = set()
    truncated_scopes: list[str] = []

    async with driver.session(database=database) as session:
        # Focus-level items first (highest priority)
        if focus and scope in ("focus", "project"):
            focus_items = await _query_focus(
                session, project_id, focus, categories, settings.retrieval_focus_limit
            )
            if len(focus_items) == settings.retrieval_focus_limit:
                truncated_scopes.append("focus")
            items += focus_items

        # Project-level items
        if scope in ("focus", "project"):
            project_items = await _query_project(
                session, project_id, categories, settings.retrieval_project_limit
            )
            if len(project_items) == settings.retrieval_project_limit:
                truncated_scopes.append("project")
            items += project_items

        # Global items last (lowest priority)
        if scope in ("focus", "project", "global"):
            global_items = await _query_global(session, categories, settings.retrieval_global_limit)
            if len(global_items) == settings.retrieval_global_limit:
                truncated_scopes.append("global")
            items += global_items

    # Deduplicate by id, preserve priority order
    unique: list[dict] = []
    for item in items:
        if item.get("id") not in seen_ids:
            seen_ids.add(item.get("id"))
            unique.append(item)

    return unique, truncated_scopes


async def _query_focus(
    session, project_id: str, focus: str, categories: list[str] | None, limit: int
) -> list[dict]:
    label_filter = _label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{label_filter})-[:HAS_FOCUS]->(f:FocusArea {{name: $focus, project_id: $pid}})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT $limit
        """,
        focus=focus,
        pid=project_id,
        limit=limit,
    )
    return [_to_dict(r) async for r in result]


async def _query_project(
    session, project_id: str, categories: list[str] | None, limit: int
) -> list[dict]:
    label_filter = _label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{label_filter})-[:BELONGS_TO]->(p:Project {{id: $pid}})
        WHERE NOT (n:Decision AND EXISTS {{ MATCH (:Decision)-[:SUPERSEDES]->(n) }})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT $limit
        """,
        pid=project_id,
        limit=limit,
    )
    return [_to_dict(r) async for r in result]


async def _query_global(session, categories: list[str] | None, limit: int) -> list[dict]:
    label_filter = _label_filter(categories)
    result = await session.run(
        f"""
        MATCH (n{label_filter})-[:BELONGS_TO]->(g:GlobalScope)
        WHERE NOT (n:Decision AND EXISTS {{ MATCH (:Decision)-[:SUPERSEDES]->(n) }})
        RETURN n {{.*}} AS node, labels(n)[0] AS label
        ORDER BY n.created_at DESC LIMIT $limit
        """,
        limit=limit,
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

    ts_raw = node.get("updated_at") or node.get("created_at")
    if ts_raw is not None:
        node["_freshness"] = compute_freshness_str(ts_raw)

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


def _rrf_fuse(
    graph_items: list[dict],
    fts_items: list[dict],
    fts_weight: float = 0.4,
    k: int | None = None,
) -> list[dict]:
    """Reciprocal Rank Fusion: fuse graph traversal + BM25 results.

    Each item is scored as Σ weight_r / (k + rank_r) across both ranked lists.
    Items appearing in both lists accumulate scores from both — naturally
    boosting results that are semantically relevant AND structurally connected.
    The `_rrf_score` field is added to every returned item.
    """
    rrf_k = k if k is not None else settings.rrf_k
    graph_weight = 1.0 - fts_weight
    scores: dict[str, float] = {}
    meta: dict[str, dict] = {}

    for rank, item in enumerate(graph_items, start=1):
        uid = item.get("id")
        if not uid:
            continue
        scores[uid] = scores.get(uid, 0.0) + graph_weight / (rrf_k + rank)
        meta[uid] = item

    for rank, item in enumerate(fts_items, start=1):
        uid = item.get("id")
        if not uid:
            continue
        scores[uid] = scores.get(uid, 0.0) + fts_weight / (rrf_k + rank)
        if uid not in meta:
            meta[uid] = item

    sorted_ids = sorted(scores, key=lambda uid: scores[uid], reverse=True)
    result = []
    for uid in sorted_ids:
        fused = dict(meta[uid])
        fused["_rrf_score"] = round(scores[uid], 6)
        result.append(fused)
    return result


async def _fetch_bm25(
    *,
    project_id: str,
    search_text: str,
    driver: AsyncDriver,
    database: str,
) -> list[dict]:
    """Delegate to shared BM25 repo. Times the full fetch and warns if >500 ms."""
    import time

    from graphbase_memories.graph.repositories.search_repo import bm25_fetch

    t0 = time.monotonic()
    items = await bm25_fetch(
        search_text=search_text,
        project_id=project_id,
        limit=settings.fts_limit,
        driver=driver,
        database=database,
    )
    elapsed_ms = (time.monotonic() - t0) * 1000
    if elapsed_ms > 500:
        logger.warning("BM25 fetch took %.0f ms (>500ms threshold)", elapsed_ms)
    return items
