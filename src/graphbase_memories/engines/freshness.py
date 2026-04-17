"""FreshnessEngine — compute freshness labels for memory nodes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from graphbase_memories.config import settings


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
