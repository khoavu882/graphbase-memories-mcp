"""Analysis tool: route_analysis (deprecated — use the analysis_routing prompt)."""

from __future__ import annotations

import warnings

from graphbase_memories.engines.analysis import route
from graphbase_memories.mcp.schemas.results import AnalysisResult
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def route_analysis(
    task_description: str,
    task_type_hint: str | None = None,
) -> AnalysisResult:
    """
    DEPRECATED: Use the analysis_routing prompt instead.
    This tool will be removed in the next release.

    task_type_hint: optional keyword hint (e.g. "trade-off", "strategic", "requirements")
    """
    warnings.warn(
        "route_analysis tool is deprecated. Use the analysis_routing prompt.",
        DeprecationWarning,
        stacklevel=2,
    )
    return route(task_description, task_type_hint)
