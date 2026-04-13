"""FreshnessEngine — scan graph for stale memory nodes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import re
from typing import Any

from neo4j import AsyncDriver

from graphbase_memories.config import settings
from graphbase_memories.graph.driver import FRESHNESS_QUERIES
from graphbase_memories.mcp.schemas.enums import FreshnessLevel
from graphbase_memories.mcp.schemas.results import FreshnessReport, StaleItem

logger = logging.getLogger(__name__)

# Extract the single named query block using the == NAME == convention
_m = re.search(
    r"//\s*==\s*FRESHNESS_SCAN\s*==\s*\n(.*?)(?=\n//\s*==|\Z)",
    FRESHNESS_QUERIES,
    re.DOTALL,
)
if not _m:
    raise KeyError("Query block 'FRESHNESS_SCAN' not found in freshness.cypher")
_FRESHNESS_SCAN_CYPHER = _m.group(1).strip().rstrip(";")


async def scan(
    *,
    project_id: str | None,
    stale_after_days: int | None,
    scan_limit: int,
    driver: AsyncDriver,
    database: str,
) -> FreshnessReport:
    """Scan for nodes older than stale_after_days. Returns FreshnessReport.

    When project_id is None, scans across all projects (global scan).
    FreshnessLevel bands:
    - current:  age <= freshness_recent_days
    - recent:   freshness_recent_days < age <= freshness_stale_days
    - stale:    age > freshness_stale_days
    """
    threshold_days = stale_after_days or settings.freshness_stale_days
    threshold_dt = datetime.now(UTC) - timedelta(days=threshold_days)
    threshold_iso = threshold_dt.isoformat()

    stale_items: list[StaleItem] = []

    async with driver.session(database=database) as session:
        result = await session.run(
            _FRESHNESS_SCAN_CYPHER,
            project_id=project_id,
            threshold_iso=threshold_iso,
            scan_limit=scan_limit,
        )
        async for record in result:
            node = dict(record["node"])
            age_days = record["age_days"]
            label = record["label"]
            # proj_id comes from the BELONGS_TO join — nodes don't store project_id as a property
            proj_id = record.get("proj_id")
            title = (
                node.get("title")
                or node.get("trigger")
                or node.get("entity_name")
                or (str(node.get("content", ""))[:80] if node.get("content") else None)
            )
            freshness = (
                FreshnessLevel.stale
                if age_days > settings.freshness_stale_days
                else FreshnessLevel.recent
                if age_days > settings.freshness_recent_days
                else FreshnessLevel.current
            )
            stale_items.append(
                StaleItem(
                    node_id=node.get("id", ""),
                    label=label,
                    title=title,
                    age_days=age_days,
                    freshness=freshness,
                    project_id=proj_id,
                )
            )

    stale_count = sum(1 for i in stale_items if i.freshness == FreshnessLevel.stale)
    recent_count = sum(1 for i in stale_items if i.freshness == FreshnessLevel.recent)

    next_step: str | None = None
    if stale_count > 0:
        next_step = f"{stale_count} stale nodes found. Run run_hygiene() to review for cleanup."
    elif recent_count > 0:
        next_step = (
            f"{recent_count} recent nodes approaching staleness. Monitor with memory_freshness()."
        )

    return FreshnessReport(
        stale_count=stale_count,
        recent_count=recent_count,
        current_count=0,  # scan only returns nodes below the threshold; current nodes not counted
        stale_items=stale_items,
        checked_at=datetime.now(UTC),
        next_step=next_step,
    )


def compute_freshness_str(ts_raw: Any) -> str:
    """
    Convert a raw timestamp to a freshness label string.

    Accepts Neo4j DateTime objects (which expose `.to_native()`), Python datetime,
    or None. Returns one of: "current", "recent", "stale", "unknown".

    Thresholds are read from settings:
      current  — age <= freshness_recent_days  (default 7)
      recent   — age <= freshness_stale_days   (default 30)
      stale    — age >  freshness_stale_days
    """
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
