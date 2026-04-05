"""
Shared TypedDict definitions for composite MCP tool parameters.

FastMCP derives JSON Schema from TypedDict — this ensures the LLM receives
named field constraints rather than a generic "object" schema, which prevents
silent field-name failures.

Used by:
  session_tools.py  — store_session_with_learnings
  entity_tools.py   — upsert_entity_with_deps
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict


class MemoryInput(TypedDict):
    """Input shape for a memory node to be stored (session, decision, or pattern)."""

    title: str
    content: str
    entities: list[str]
    tags: list[str]


class DecisionResult(TypedDict):
    """Result for a single decision stored by store_session_with_learnings."""

    id: str
    superseded_id: str | None


class PatternResult(TypedDict):
    """Result for a single pattern stored by store_session_with_learnings."""

    id: str


class ItemError(TypedDict):
    """Per-item failure descriptor returned in the errors list of batch tools."""

    index: int
    type: str    # "decision" | "pattern" | "dep"
    message: str


__all__ = [
    "MemoryInput",
    "DecisionResult",
    "PatternResult",
    "ItemError",
]
