"""MCP tool registry and engine-direct invocation routes."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
import time
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException
from neo4j import AsyncDriver
from pydantic import BaseModel

from graphbase_memories.config import settings
from graphbase_memories.devtools.deps import DriverDep, validate_devtools_token
from graphbase_memories.engines import federation as federation_engine
from graphbase_memories.engines import hygiene as hygiene_engine
from graphbase_memories.engines import impact as impact_engine
from graphbase_memories.engines import surface as surface_engine
from graphbase_memories.mcp.server import mcp

router = APIRouter(prefix="/tools", tags=["tools"])

# Tools that execute without a write confirmation gate (read-only or report-only).
# Kept as a set for O(1) lookup; derived from _TOOL_REGISTRY below.
_READ_ONLY_TOOLS = {
    "retrieve_context",
    "graph_health",
    "list_active_services",
    "search_cross_service",
    "run_hygiene",
    "memory_surface",
}

DispatchFn = Callable[[dict, AsyncDriver], Coroutine[Any, Any, Any]]


@dataclass
class ToolSpec:
    """Single source of truth for a tool's module, HTTP dispatch, and confirmation requirement.

    dispatch_fn=None signals the tool requires structured Pydantic input not
    expressible as a flat JSON params dict — it will be marked http_invocable=False.
    """

    module: str
    dispatch_fn: DispatchFn | None = field(default=None)
    requires_confirm: bool = True


# ---------------------------------------------------------------------------
# Unified registry: replaces the former separate _MODULE_MAP + _TOOL_DISPATCH dicts.
# Adding a new tool requires a single entry here; module and http_invocable are
# derived from ToolSpec fields, eliminating the prior two-dict sync hazard.
# ---------------------------------------------------------------------------
_TOOL_REGISTRY: dict[str, ToolSpec] = {
    # ── READ-ONLY / REPORT-ONLY ────────────────────────────────────────────
    "graph_health": ToolSpec(
        module="impact",
        dispatch_fn=lambda p, d: impact_engine.graph_health(
            p["workspace_id"], d, settings.neo4j_database
        ),
        requires_confirm=False,
    ),
    "list_active_services": ToolSpec(
        module="federation",
        dispatch_fn=lambda p, d: federation_engine.list_services(
            p["workspace_id"],
            p.get("max_idle_minutes", settings.federation_active_window_minutes),
            d,
            settings.neo4j_database,
        ),
        requires_confirm=False,
    ),
    "search_cross_service": ToolSpec(
        module="cross_service",
        dispatch_fn=lambda p, d: federation_engine.search_cross_service(
            p["query"],
            p["workspace_id"],
            p.get("target_project_ids"),
            p.get("node_types"),
            p.get("limit", settings.federation_max_results),
            d,
            settings.neo4j_database,
        ),
        requires_confirm=False,
    ),
    "run_hygiene": ToolSpec(
        module="hygiene",
        dispatch_fn=lambda p, d: hygiene_engine.run(
            project_id=p.get("project_id"),
            scope=p.get("scope", "global"),
            driver=d,
            database=settings.neo4j_database,
        ),
        requires_confirm=False,
    ),
    "memory_surface": ToolSpec(
        module="retrieval",
        dispatch_fn=lambda p, d: surface_engine.execute(
            query=p["query"],
            project_id=p.get("project_id"),
            limit=p.get("limit", 5),
            driver=d,
            database=settings.neo4j_database,
        ),
        requires_confirm=False,
    ),
    # ── WRITE — require confirm=true ───────────────────────────────────────
    "propagate_impact": ToolSpec(
        module="impact",
        dispatch_fn=lambda p, d: impact_engine.propagate_impact(
            p["entity_id"],
            p["change_description"],
            p.get("impact_type", "breaking"),
            p.get("max_depth", settings.impact_max_depth),
            d,
            settings.neo4j_database,
        ),
    ),
    "link_cross_service": ToolSpec(
        module="cross_service",
        dispatch_fn=lambda p, d: federation_engine.create_cross_service_link(
            p["source_entity_id"],
            p["target_entity_id"],
            p["link_type"],
            p.get("rationale", ""),
            p.get("confidence", 0.8),
            p.get("created_by"),
            d,
            settings.neo4j_database,
        ),
    ),
    "register_federated_service": ToolSpec(
        module="federation",
        dispatch_fn=lambda p, d: federation_engine.register_service(
            p["service_id"],
            p["workspace_id"],
            p.get("display_name"),
            p.get("description"),
            p.get("tags", []),
            d,
            settings.neo4j_database,
        ),
    ),
    # ── NOT HTTP-INVOCABLE: require structured Pydantic input ─────────────
    # dispatch_fn=None → http_invocable=False in list/get responses.
    "save_decision": ToolSpec(module="artifacts"),
    "save_pattern": ToolSpec(module="artifacts"),
    "save_context": ToolSpec(module="artifacts"),
    "upsert_entity_with_deps": ToolSpec(module="entity"),
    "request_global_write_approval": ToolSpec(module="governance"),
    "store_session_with_learnings": ToolSpec(module="session"),
    "retrieve_context": ToolSpec(module="retrieval", requires_confirm=False),
    "register_service": ToolSpec(module="topology"),
    "link_topology_nodes": ToolSpec(module="topology"),
    "batch_upsert_shared_infrastructure": ToolSpec(module="topology"),
    "get_service_dependencies": ToolSpec(module="topology", requires_confirm=False),
    "get_feature_workflow": ToolSpec(module="topology", requires_confirm=False),
}


def _tool_meta(mt_name: str) -> tuple[str, bool, bool]:
    """Return (module, requires_confirmation, http_invocable) for a tool name."""
    spec = _TOOL_REGISTRY.get(mt_name)
    if spec is None:
        return ("unknown", True, False)
    return (spec.module, spec.requires_confirm, spec.dispatch_fn is not None)


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
    """Return all registered MCP tools with input schemas and confirmation requirements."""
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
            "requires_confirmation": module_meta[1],
            "module": module_meta[0],
            "http_invocable": module_meta[2],
        }
        for t in tools
        for mt in [t.to_mcp_tool()]
        for module_meta in [_tool_meta(mt.name)]
    ]


@router.get("/{name}")
async def get_tool(name: str):
    """Return schema and metadata for a single MCP tool by name."""
    tools = await mcp.list_tools()
    for t in tools:
        mt = t.to_mcp_tool()
        if mt.name == name:
            module, requires_confirmation, http_invocable = _tool_meta(mt.name)
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
                "requires_confirmation": requires_confirmation,
                "module": module,
                "http_invocable": http_invocable,
            }
    raise HTTPException(status_code=404, detail=f"Tool {name!r} not found")


class InvokeRequest(BaseModel):
    params: dict
    confirm: bool = False


@router.post("/{name}/invoke")
async def invoke_tool(
    name: str,
    body: InvokeRequest,
    driver: DriverDep,
    x_devtools_token: Annotated[str | None, Header(alias="X-Devtools-Token")] = None,
):
    """
    Invoke an MCP tool via the engine layer.

    Read-only tools execute immediately. Write tools require confirm=true;
    without it they return a dry-run preview describing what would be written.
    Tools not in the dispatch table (complex Pydantic-input tools) return 501 —
    use the MCP stdio server for those.
    """
    spec = _TOOL_REGISTRY.get(name)
    if spec is None or spec.dispatch_fn is None:
        raise HTTPException(
            status_code=501,
            detail=(
                f"Tool {name!r} requires structured Pydantic input not expressible "
                "as a flat JSON params dict. Use the MCP stdio server instead."
            ),
        )

    if spec.requires_confirm:
        validate_devtools_token(x_devtools_token)

    if spec.requires_confirm and not body.confirm:
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
        result = await spec.dispatch_fn(body.params, driver)
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required parameter: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    duration_ms = round((time.monotonic() - t_start) * 1000)
    return {"status": "ok", "result": _serialise(result), "duration_ms": duration_ms}
