"""
SurfaceEngine — BM25 memory surface for hook injection and explicit MCP tool use.

Design:
- BM25 path: delegates to search_repo.bm25_fetch (shared with RetrievalEngine)
- Keyword path: label-scan for PostToolUse staleness detection
- Output cap: 800 characters (deterministic; no tokenizer dependency)
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from neo4j import AsyncDriver

from graphbase_memories.engines.freshness import compute_freshness_str
from graphbase_memories.mcp.schemas.results import SurfaceMatch, SurfaceResult

logger = logging.getLogger(__name__)

# Label → (name_field, content_field) for mapping BM25 node dicts to SurfaceMatch
_LABEL_FIELDS: dict[str, tuple[str, str]] = {
    "Decision": ("title", "rationale"),
    "Pattern": ("trigger", "repeatable_steps_text"),
    "Context": ("topic", "content"),
    "EntityFact": ("entity_name", "fact"),
}

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
    """Delegate to shared BM25 repo and map results to SurfaceMatch."""
    from graphbase_memories.graph.repositories.search_repo import bm25_fetch

    all_items = await bm25_fetch(
        search_text=query,
        project_id=project_id,
        limit=limit,
        driver=driver,
        database=database,
    )
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
    label = item.get("_label", "Unknown")
    name_field, content_field = _LABEL_FIELDS.get(label, ("entity_name", "fact"))

    ts_raw = item.get("updated_at") or item.get("created_at")

    return SurfaceMatch(
        id=item.get("id", ""),
        label=label,
        name=str(item.get(name_field, "")),
        content=str(item.get(content_field, "")),
        scope=str(item.get("scope", "")),
        freshness=compute_freshness_str(ts_raw),
        bm25_score=item.get("bm25_score", 0.0),
        project_id=item.get("project_id"),
    )


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
