"""
SurfaceEngine — BM25 memory surface for hook injection and explicit MCP tool use.

Design:
- BM25 path: four-index loop (mirrors _fetch_bm25 in retrieval.py exactly)
- Keyword path: label-scan for PostToolUse staleness detection
- Output cap: 800 characters (deterministic; no tokenizer dependency)
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from neo4j import AsyncDriver

from graphbase_memories.config import settings
from graphbase_memories.mcp.schemas.results import SurfaceMatch, SurfaceResult

logger = logging.getLogger(__name__)

# Four FTS indexes — one per node label (CALL UNION ALL is unreliable in Neo4j 5 Community)
_INDEX_CONFIGS: list[tuple[str, str, str, str]] = [
    ("decision_fulltext", "Decision", "title", "rationale"),
    ("pattern_fulltext", "Pattern", "trigger", "repeatable_steps_text"),
    ("context_fulltext", "Context", "topic", "content"),
    ("entity_fulltext", "EntityFact", "entity_name", "fact"),
]

_SURFACE_BY_KEYWORD = """
MATCH (n)
WHERE (n:Decision OR n:Pattern OR n:Context OR n:EntityFact)
  AND any(kw IN $keywords WHERE
    toLower(n.title) CONTAINS kw OR
    toLower(n.entity_name) CONTAINS kw OR
    toLower(n.trigger) CONTAINS kw OR
    toLower(n.topic) CONTAINS kw
  )
  AND coalesce(n.updated_at, n.created_at) < datetime($threshold_iso)
RETURN
  labels(n)[0] AS label,
  coalesce(n.title, n.entity_name, n.trigger, n.topic) AS entity_name
ORDER BY coalesce(n.updated_at, n.created_at) ASC
LIMIT 20
"""

_OUTPUT_CHAR_CAP = 800


async def execute(
    *,
    query: str | None,
    keywords: list[str] | None = None,
    project_id: str | None = None,
    limit: int = 5,
    driver: AsyncDriver,
    database: str,
) -> SurfaceResult:
    """Entry point: BM25 path (query) or keyword-staleness path (keywords)."""
    if keywords:
        return await _execute_keyword(keywords, driver, database)
    if not query or len(query.strip()) < 3:
        return SurfaceResult(matches=[], query_used=query or "", total_found=0)
    return await _execute_bm25(query.strip(), project_id, limit, driver, database)


async def _execute_bm25(
    query: str,
    project_id: str | None,
    limit: int,
    driver: AsyncDriver,
    database: str,
) -> SurfaceResult:
    """Four-index BM25 loop — same pattern as _fetch_bm25() in retrieval.py."""
    all_items: list[dict] = []
    seen: set[str] = set()

    async with driver.session(database=database) as session:
        for index_name, label, name_field, content_field in _INDEX_CONFIGS:
            try:
                result = await session.run(
                    "CALL db.index.fulltext.queryNodes($index_name, $search_text) "
                    "YIELD node, score "
                    "WHERE node.project_id = $project_id OR node.scope = 'global' "
                    "RETURN node {.*} AS item, $label AS label, score AS bm25_score "
                    "ORDER BY bm25_score DESC LIMIT $limit",
                    index_name=index_name,
                    search_text=query,
                    project_id=project_id or "",
                    label=label,
                    limit=limit,
                )
                async for record in result:
                    item = dict(record["item"])
                    uid = item.get("id", "")
                    if uid and uid not in seen:
                        seen.add(uid)
                        all_items.append(
                            {
                                **item,
                                "_label": label,
                                "_name_field": name_field,
                                "_content_field": content_field,
                                "bm25_score": float(record["bm25_score"]),
                            }
                        )
            except Exception:
                logger.warning("Surface BM25 query failed for index %s — skipping", index_name)
                continue  # partial results acceptable

    all_items.sort(key=lambda x: x.get("bm25_score", 0.0), reverse=True)
    matches = [_to_surface_match(item) for item in all_items[:limit]]

    return SurfaceResult(
        matches=matches,
        query_used=query,
        total_found=len(all_items),
        next_step=_build_next_step(matches, len(all_items), limit),
    )


async def _execute_keyword(
    keywords: list[str],
    driver: AsyncDriver,
    database: str,
) -> SurfaceResult:
    """Keyword staleness check for PostToolUse hook path."""
    threshold_iso = datetime.now(UTC).isoformat()
    safe_kw = [k.lower() for k in keywords if len(k) >= 3]

    if not safe_kw:
        return SurfaceResult(matches=[], query_used=",".join(keywords), total_found=0)

    async with driver.session(database=database) as session:
        result = await session.run(
            _SURFACE_BY_KEYWORD,
            keywords=safe_kw,
            threshold_iso=threshold_iso,
        )
        rows = [dict(r) async for r in result]

    if not rows:
        return SurfaceResult(matches=[], query_used=",".join(keywords), total_found=0)

    matches = [
        SurfaceMatch(
            id="",
            label=row.get("label", ""),
            name=row.get("entity_name", ""),
            content="",
            scope="",
            freshness="stale",
            bm25_score=0.0,
        )
        for row in rows
    ]
    return SurfaceResult(
        matches=matches,
        query_used=",".join(keywords),
        total_found=len(rows),
        next_step="Consider updating memories or running: graphbase hygiene --scope project",
    )


def _to_surface_match(item: dict) -> SurfaceMatch:
    """Map label-specific property names to unified SurfaceMatch fields."""
    name_field = item.get("_name_field", "entity_name")
    content_field = item.get("_content_field", "fact")

    ts_raw = item.get("updated_at") or item.get("created_at")
    freshness = _compute_freshness(ts_raw)

    return SurfaceMatch(
        id=item.get("id", ""),
        label=item.get("_label", "Unknown"),
        name=str(item.get(name_field, "")),
        content=str(item.get(content_field, "")),
        scope=str(item.get("scope", "")),
        freshness=freshness,
        bm25_score=item.get("bm25_score", 0.0),
        project_id=item.get("project_id"),
    )


def _compute_freshness(ts_raw) -> str:
    """Replicates freshness logic from retrieval.py _to_dict()."""
    if ts_raw is None:
        return "unknown"
    ts = ts_raw.to_native() if hasattr(ts_raw, "to_native") else ts_raw
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    age_days = (datetime.now(UTC) - ts).days
    if age_days <= settings.freshness_recent_days:
        return "current"
    if age_days <= settings.freshness_stale_days:
        return "recent"
    return "stale"


def _build_next_step(matches: list[SurfaceMatch], total: int, limit: int) -> str | None:
    if not matches:
        return "No memories found. Try retrieve_context(scope='global') or broaden query."
    if total > limit:
        return (
            f"More matches available ({total} total). Increase limit= or narrow with project_id=."
        )
    return "Use upsert_entity_with_deps to update if decisions have changed."


def format_for_hook(result: SurfaceResult) -> str:
    """
    Format SurfaceResult as human-readable string for stderr injection.
    Capped at 800 characters. Returns empty string if no matches.
    """
    if not result.matches:
        return ""

    lines = [
        f'[Graphbase] {result.total_found} related memories found for "{result.query_used}":\n'
    ]
    for match in result.matches:
        lines.append(f"● {match.name} ({match.label})")
        if match.content:
            preview = match.content[:120] + ("..." if len(match.content) > 120 else "")
            lines.append(f"  {preview}")
        lines.append("")

    output = "\n".join(lines)
    if len(output) > _OUTPUT_CHAR_CAP:
        output = output[: _OUTPUT_CHAR_CAP - 15] + "\n... (truncated)"
    return output


def format_staleness_for_hook(result: SurfaceResult, keywords: list[str]) -> str:
    """Format keyword-staleness result as advisory message for PostToolUse hook."""
    if not result.matches:
        return ""
    names = ", ".join(m.name for m in result.matches[:5])
    if len(result.matches) > 5:
        names += f" (+{len(result.matches) - 5} more)"
    lines = [
        f"[Graphbase] Memories may be stale for changed keywords: {', '.join(keywords)}",
        f"Potentially affected entities: {names}",
        "Consider: graphbase hygiene --scope project",
    ]
    return "\n".join(lines)
