"""Analysis tool: route_analysis."""

from __future__ import annotations

from graphbase_memories.engines.analysis import route
from graphbase_memories.mcp.schemas.results import AnalysisResult
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def route_analysis(
    task_description: str,
    task_type_hint: str | None = None,
) -> AnalysisResult:
    """
    Route a task to the appropriate analysis mode (FR-26).

    Returns: mode (sequential/debate/socratic), rationale, and suggested_steps (M-1).
    Only the final synthesized conclusion from analysis should be saved — not intermediate discussion (FR-27).

    task_type_hint: optional keyword hint (e.g. "trade-off", "strategic", "requirements")
    """
    return route(task_description, task_type_hint)
