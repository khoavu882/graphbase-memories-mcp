"""FreshnessEngine — compute freshness labels for memory nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from neo4j import AsyncDriver

from graphbase_memories.config import settings
from graphbase_memories.domain.enums import FreshnessLevel
from graphbase_memories.domain.results import FreshnessReport, StaleItem
from graphbase_memories.graph.repositories import freshness_repo


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


async def scan(
    project_id: str,
    stale_after_days: int,
    scan_limit: int,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> FreshnessReport:
    """Scan a project's memory nodes and return those that are stale.

    A node is stale when its most recent timestamp (updated_at fallback created_at)
    is older than stale_after_days. Returns a FreshnessReport with stale_items,
    stale_count, checked_at, and a next_step hint.
    """
    now = datetime.now(UTC)
    stale_items: list[StaleItem] = []

    records = await freshness_repo.scan_stale_records(
        project_id=project_id,
        stale_after_days=stale_after_days,
        scan_limit=scan_limit,
        driver=driver,
        database=database,
    )
    for record in records:
        ts_raw = record["ts"]
        ts = ts_raw.to_native() if hasattr(ts_raw, "to_native") else ts_raw
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        age_days = (now - ts).days
        freshness_str = compute_freshness_str(ts_raw)
        stale_items.append(
            StaleItem(
                node_id=record["node_id"],
                label=record["label"],
                title=record["title"],
                age_days=age_days,
                freshness=FreshnessLevel(freshness_str) if freshness_str != "unknown" else FreshnessLevel.stale,
                project_id=record["project_id"],
            )
        )

    stale_count = len(stale_items)
    if stale_count == 0:
        next_step = None
    else:
        oldest = stale_items[0]  # ordered ASC by ts — oldest first
        next_step = (
            f"{stale_count} stale node(s) found in project '{project_id}'. "
            f"Oldest: {oldest.label} '{oldest.title}' ({oldest.age_days} days). "
            "Call retrieve_context() to review and supersede outdated memories."
        )

    return FreshnessReport(
        project_id=project_id,
        stale_count=stale_count,
        stale_items=stale_items,
        checked_at=now,
        next_step=next_step,
    )
