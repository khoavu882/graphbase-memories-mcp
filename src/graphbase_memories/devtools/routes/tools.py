"""MCP tool registry and engine-direct invocation routes."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from neo4j import AsyncDriver
from pydantic import BaseModel

from graphbase_memories.config import settings
from graphbase_memories.devtools.deps import DriverDep
from graphbase_memories.engines import federation as federation_engine
from graphbase_memories.engines import hygiene as hygiene_engine
from graphbase_memories.engines import impact as impact_engine
from graphbase_memories.engines.analysis import route as analysis_route
from graphbase_memories.mcp.server import mcp

router = APIRouter(prefix="/tools", tags=["tools"])

# Tools that execute without a write confirmation gate (read-only or report-only)
_READ_ONLY_TOOLS = {
    "route_analysis",
    "retrieve_context",
    "graph_health",
    "list_active_services",
    "search_cross_service",
    "run_hygiene",
    "memory_surface",
}

# Module classification for the registry panel
_MODULE_MAP: dict[str, str] = {
    "route_analysis": "analysis",
    "save_decision": "artifacts",
    "save_pattern": "artifacts",
    "save_context": "artifacts",
    "search_cross_service": "cross_service",
    "link_cross_service": "cross_service",
    "upsert_entity_with_deps": "entity",
    "register_federated_service": "federation",
    "list_active_services": "federation",
    "request_global_write_approval": "governance",
    "run_hygiene": "hygiene",
    "propagate_impact": "impact",
    "graph_health": "impact",
    "retrieve_context": "retrieval",
    "store_session_with_learnings": "session",
    "memory_surface": "retrieval",
    "register_service": "topology",
    "link_topology_nodes": "topology",
    "batch_upsert_shared_infrastructure": "topology",
    "get_service_dependencies": "topology",
    "get_feature_workflow": "topology",
}


# ---------------------------------------------------------------------------
# Dispatch table: tool_name → (async_callable(params, driver), requires_confirm)
# Each lambda maps the HTTP JSON params dict to the exact engine function call.
# Verified against engine source signatures 2026-04-11.
# ---------------------------------------------------------------------------
DispatchFn = Callable[[dict, AsyncDriver], Coroutine[Any, Any, Any]]

_TOOL_DISPATCH: dict[str, tuple[DispatchFn, bool]] = {
    # ── READ-ONLY / REPORT-ONLY ────────────────────────────────────────────
    "route_analysis": (
        lambda p, _d: _sync_wrap(
            analysis_route(
                p["task_description"],
                p.get("task_type_hint"),
            )
        ),
        False,
    ),
    "graph_health": (
        lambda p, d: impact_engine.graph_health(p["workspace_id"], d, settings.neo4j_database),
        False,
    ),
    "list_active_services": (
        lambda p, d: federation_engine.list_services(
            p["workspace_id"],
            p.get("max_idle_minutes", settings.federation_active_window_minutes),
            d,
            settings.neo4j_database,
        ),
        False,
    ),
    "search_cross_service": (
        lambda p, d: federation_engine.search_cross_service(
            p["query"],
            p["workspace_id"],
            p.get("target_project_ids"),
            p.get("node_types"),
            p.get("limit", settings.federation_max_results),
            d,
            settings.neo4j_database,
        ),
        False,
    ),
    "run_hygiene": (
        lambda p, d: hygiene_engine.run(
            project_id=p.get("project_id"),
            scope=p.get("scope", "global"),
            driver=d,
            database=settings.neo4j_database,
        ),
        False,
    ),
    # ── WRITE — require confirm=true ───────────────────────────────────────
    "propagate_impact": (
        lambda p, d: impact_engine.propagate_impact(
            p["entity_id"],
            p["change_description"],
            p.get("impact_type", "breaking"),
            p.get("max_depth", settings.impact_max_depth),
            d,
            settings.neo4j_database,
        ),
        True,
    ),
    "link_cross_service": (
        lambda p, d: federation_engine.create_cross_service_link(
            p["source_entity_id"],
            p["target_entity_id"],
            p["link_type"],
            p.get("rationale", ""),
            p.get("confidence", 0.8),
            p.get("created_by"),
            d,
            settings.neo4j_database,
        ),
        True,
    ),
    "register_federated_service": (
        lambda p, d: federation_engine.register_service(
            p["service_id"],
            p["workspace_id"],
            p.get("display_name"),
            p.get("description"),
            p.get("tags", []),
            d,
            settings.neo4j_database,
        ),
        True,
    ),
}


async def _sync_wrap(result: Any) -> Any:
    """Wrap a synchronous result in a coroutine for uniform dispatch handling."""
    return result


def _serialise(result: Any) -> Any:
    """Convert Pydantic models and lists thereof to JSON-serialisable dicts."""
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, list):
        return [r.model_dump() if hasattr(r, "model_dump") else r for r in result]
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_tools():
    """Return all 20 registered MCP tools with input schemas and confirmation requirements."""
    tools = await mcp.list_tools()
    return [
        {
            "name": mt.name,
            "description": mt.description or "",
            "input_schema": (
                mt.inputSchema
                if isinstance(mt.inputSchema, dict)
                else mt.inputSchema.model_dump()
                if mt.inputSchema
                else {}
            ),
            "requires_confirmation": mt.name not in _READ_ONLY_TOOLS,
            "module": _MODULE_MAP.get(mt.name, "unknown"),
            "http_invocable": mt.name in _TOOL_DISPATCH,
        }
        for t in tools
        for mt in [t.to_mcp_tool()]
    ]


@router.get("/{name}")
async def get_tool(name: str):
    """Return schema and metadata for a single MCP tool by name."""
    tools = await mcp.list_tools()
    for t in tools:
        mt = t.to_mcp_tool()
        if mt.name == name:
            return {
                "name": mt.name,
                "description": mt.description or "",
                "input_schema": (
                    mt.inputSchema
                    if isinstance(mt.inputSchema, dict)
                    else mt.inputSchema.model_dump()
                    if mt.inputSchema
                    else {}
                ),
                "requires_confirmation": mt.name not in _READ_ONLY_TOOLS,
                "module": _MODULE_MAP.get(mt.name, "unknown"),
                "http_invocable": mt.name in _TOOL_DISPATCH,
            }
    raise HTTPException(status_code=404, detail=f"Tool {name!r} not found")


class InvokeRequest(BaseModel):
    params: dict
    confirm: bool = False


@router.post("/{name}/invoke")
async def invoke_tool(name: str, body: InvokeRequest, driver: DriverDep):
    """
    Invoke an MCP tool via the engine layer.

    Read-only tools execute immediately. Write tools require confirm=true;
    without it they return a dry-run preview describing what would be written.
    Tools not in the dispatch table (complex Pydantic-input tools) return
    not_supported — use the MCP stdio server for those.
    """
    if name not in _TOOL_DISPATCH:
        return {
            "status": "not_supported",
            "message": (
                f"Tool {name!r} requires structured Pydantic input not expressible "
                "as a flat JSON params dict. Use the MCP stdio server instead."
            ),
        }

    fn, requires_confirm = _TOOL_DISPATCH[name]

    if requires_confirm and not body.confirm:
        return {
            "status": "preview",
            "message": (
                f"Tool {name!r} performs a durable write operation. "
                "Review params_received and re-send with confirm=true to execute."
            ),
            "params_received": body.params,
        }

    t_start = time.monotonic()
    try:
        result = await fn(body.params, driver)
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required parameter: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    duration_ms = round((time.monotonic() - t_start) * 1000)
    return {"status": "ok", "result": _serialise(result), "duration_ms": duration_ms}
