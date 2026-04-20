"""
Integration: devtools tool registry and engine dispatch routes.
Tests list_tools, get_tool, and invoke_tool handler functions directly.
"""

from __future__ import annotations


async def test_list_tools_returns_all_registered(driver):
    """GET /tools returns all MCP-registered tools with required fields."""
    from graphbase_memories.devtools.routes.tools import list_tools

    result = await list_tools()

    assert isinstance(result, list)
    assert len(result) >= 1

    for tool in result:
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert "requires_confirmation" in tool
        assert "module" in tool
        assert "http_invocable" in tool


async def test_list_tools_includes_known_tools(driver):
    """Known tool names are present in the registry."""
    from graphbase_memories.devtools.routes.tools import list_tools

    result = await list_tools()
    names = {t["name"] for t in result}

    expected = {
        "graph_health",
        "list_active_services",
        "search_cross_service",
        "run_hygiene",
        "propagate_impact",
        "link_cross_service",
        "register_service",
        "link_topology_nodes",
        "register_federated_service",
    }
    assert expected.issubset(names), f"Missing tools: {expected - names}"


async def test_list_tools_no_unknown_module(driver):
    """Every tool returned by the MCP registry has a known module (not 'unknown')."""
    from graphbase_memories.devtools.routes.tools import list_tools

    result = await list_tools()
    unknown = [t["name"] for t in result if t["module"] == "unknown"]
    assert unknown == [], (
        f"Tools with module='unknown' are missing from _TOOL_REGISTRY: {unknown}. "
        "Add an entry to _TOOL_REGISTRY in routes/tools.py."
    )


async def test_list_tools_read_only_not_require_confirmation(driver):
    """Read-only tools have requires_confirmation=False."""
    from graphbase_memories.devtools.routes.tools import _READ_ONLY_TOOLS, list_tools

    result = await list_tools()
    by_name = {t["name"]: t for t in result}

    for name in _READ_ONLY_TOOLS:
        if name in by_name:
            assert by_name[name]["requires_confirmation"] is False, f"{name} should be read-only"


async def test_list_tools_write_tools_require_confirmation(driver):
    """Write tools (propagate_impact, link_cross_service, etc.) require confirmation."""
    from graphbase_memories.devtools.routes.tools import list_tools

    result = await list_tools()
    by_name = {t["name"]: t for t in result}

    write_tools = [
        "propagate_impact",
        "link_cross_service",
        "register_federated_service",
        "deregister_service",
    ]
    for name in write_tools:
        if name in by_name:
            assert by_name[name]["requires_confirmation"] is True, (
                f"{name} should require confirmation"
            )


async def test_list_tools_memory_surface_is_http_invocable(driver):
    """memory_surface is in _READ_ONLY_TOOLS and must also be http_invocable."""
    from graphbase_memories.devtools.routes.tools import list_tools

    result = await list_tools()
    by_name = {t["name"]: t for t in result}

    assert "memory_surface" in by_name, "memory_surface not in tool registry"
    tool = by_name["memory_surface"]
    assert tool["http_invocable"] is True, "memory_surface should be http_invocable"
    assert tool["requires_confirmation"] is False, "memory_surface should be read-only"


async def test_get_tool_returns_single_tool(driver):
    """GET /tools/{name} returns the named tool's metadata."""
    from graphbase_memories.devtools.routes.tools import get_tool

    result = await get_tool("graph_health")
    assert result["name"] == "graph_health"
    assert result["module"] == "impact"
    assert result["requires_confirmation"] is False


async def test_get_tool_not_found_raises_404(driver):
    """GET /tools/nonexistent raises HTTPException 404."""
    from fastapi import HTTPException

    from graphbase_memories.devtools.routes.tools import get_tool

    try:
        await get_tool("definitely_not_a_real_tool")
        raise AssertionError("Should have raised HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 404


async def test_invoke_tool_write_without_confirm_returns_preview(driver):
    """POST /tools/propagate_impact/invoke without confirm=True returns status=preview."""
    from graphbase_memories.devtools.deps import set_devtools_token
    from graphbase_memories.devtools.routes.tools import InvokeRequest, invoke_tool

    set_devtools_token("test-devtools-token")

    body = InvokeRequest(
        params={"entity_id": "test-entity", "change_description": "breaking change"},
        confirm=False,
    )
    result = await invoke_tool(
        "propagate_impact",
        body,
        driver,
        x_devtools_token="test-devtools-token",
    )

    assert result["status"] == "preview"
    assert "params_received" in result


async def test_invoke_tool_not_dispatched_returns_501(driver):
    """POST /tools/save_decision/invoke returns HTTP 501 (not 200)."""
    from fastapi import HTTPException

    from graphbase_memories.devtools.routes.tools import InvokeRequest, invoke_tool

    body = InvokeRequest(params={}, confirm=False)
    try:
        await invoke_tool("save_decision", body, driver)
        raise AssertionError("Should have raised HTTPException 501")
    except HTTPException as exc:
        assert exc.status_code == 501


async def test_invoke_read_tool_executes_immediately(driver):
    """POST /tools/run_hygiene/invoke (read-only) executes without confirm."""
    from graphbase_memories.devtools.routes.tools import InvokeRequest, invoke_tool

    body = InvokeRequest(params={"scope": "global"}, confirm=False)
    result = await invoke_tool("run_hygiene", body, driver)

    # Should return ok status with a result (hygiene report)
    assert result["status"] == "ok"
    assert "result" in result
    assert "duration_ms" in result


async def test_invoke_write_tool_requires_token(driver):
    """POST /tools/{name}/invoke rejects write-capable tools without the startup token."""
    from fastapi import HTTPException

    from graphbase_memories.devtools.deps import set_devtools_token
    from graphbase_memories.devtools.routes.tools import InvokeRequest, invoke_tool

    set_devtools_token("expected-token")
    body = InvokeRequest(
        params={"entity_id": "test-entity", "change_description": "breaking change"},
        confirm=False,
    )

    try:
        await invoke_tool("propagate_impact", body, driver)
        raise AssertionError("Should have raised HTTPException 403")
    except HTTPException as exc:
        assert exc.status_code == 403
