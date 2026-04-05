"""
Shared utilities for graphbase-memories.

Centralised here to avoid duplication across sqlite_engine and tool modules.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string (second precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
