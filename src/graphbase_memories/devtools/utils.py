"""Shared devtools utilities — staleness computation and threshold constants."""

from __future__ import annotations

from datetime import datetime

# Number of days since last_seen before a Project is considered stale.
# This is the single authoritative threshold for all devtools routes.
STALE_SEEN_DAYS = 7


def staleness(last_seen, now: datetime) -> tuple[float | None, bool]:
    """Return (staleness_days, is_stale) from a Neo4j datetime value or None.

    Handles both neo4j.time.DateTime (has .to_native()) and plain datetime objects
    so that test fixtures can pass either type without special-casing.
    """
    if last_seen is None:
        return None, False
    ls = last_seen.to_native() if hasattr(last_seen, "to_native") else last_seen
    days = (now - ls).total_seconds() / 86400
    return round(days, 2), days > STALE_SEEN_DAYS
