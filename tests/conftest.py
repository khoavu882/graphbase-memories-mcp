"""
Shared pytest fixtures for graphbase-memories integration tests.

Fixtures:
  engine(tmp_path)  — isolated SQLiteEngine per test
  mcp(engine)       — MCPTestClient wrapping FastMCP with call_tool compat
  parse(r)          — module-level helper: parse ToolResult -> Python object

FastMCP 2.x removed mcp.call_tool(name, args). MCPTestClient restores the
old API via: tool = await mcp.get_tool(name); result = await tool.run(args).
All test files continue to use `await mcp.call_tool(name, args)` unchanged.
"""
from __future__ import annotations

import json
import pytest

PROJECT = "test"


class MCPTestClient:
    """
    Thin wrapper around FastMCP that restores the call_tool(name, args) test
    helper removed in FastMCP 2.x.

    FastMCP 2.x API: `tool = await mcp.get_tool(name); result = await tool.run(args)`
    This wrapper keeps existing test code unchanged.
    """

    def __init__(self, mcp):
        self._mcp = mcp

    async def call_tool(self, name: str, args: dict) -> object:
        tool = await self._mcp.get_tool(name)
        return await tool.run(args)

    def __getattr__(self, name: str):
        # Delegate any other attribute access (get_tools, add_tool, etc.) to mcp
        return getattr(self._mcp, name)


@pytest.fixture
def engine(tmp_path):
    """Fresh SQLiteEngine in a temp directory, cleared from global pool after test."""
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine
    from graphbase_memories._provider import _clear_engines, _set_config_for_test

    _clear_engines()
    cfg = Config(
        backend="sqlite",
        data_dir=tmp_path,
        log_level="WARNING",
        log_to_file=False,
    )
    # Inject test config into provider so lifecycle tools use the same data_dir
    _set_config_for_test(cfg)
    eng = SQLiteEngine(cfg, PROJECT)
    yield eng
    _clear_engines()
    _set_config_for_test(Config())  # restore default


@pytest.fixture
def mcp(engine):
    """MCPTestClient wrapping FastMCP singleton with test engine injected."""
    from graphbase_memories.server import get_mcp
    from graphbase_memories._provider import _set_engine_for_test, _clear_engines

    _set_engine_for_test(PROJECT, engine)
    yield MCPTestClient(get_mcp())
    _clear_engines()


def parse(r) -> object:
    """Parse a FastMCP ToolResult into a Python object."""
    if not r.content:
        return r.structured_content.get("result")
    try:
        return json.loads(r.content[0].text)
    except Exception:
        return r.content[0].text
