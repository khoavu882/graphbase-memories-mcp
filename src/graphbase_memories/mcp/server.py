"""
FastMCP server — B-1: imports ONLY from fastmcp, never from mcp.server.fastmcp.
B-2: driver lifecycle owned by neo4j_lifespan context manager.
"""

from fastmcp import FastMCP  # B-1: sole FastMCP import

from graphbase_memories.graph.driver import neo4j_lifespan

mcp = FastMCP("graphbase-memories", lifespan=neo4j_lifespan)


def _register_tools() -> None:
    """
    Import tool modules to trigger @mcp.tool() registration.
    Using a factory function makes the dependency direction explicit
    and prevents fragile module-level circular import ordering.
    """
    from graphbase_memories.mcp.tools import (  # noqa: F401
        analysis,
        artifacts,
        cross_service,
        entity,
        federation,
        freshness,
        governance,
        hygiene,
        impact,
        retrieval,
        session,
        topology,
    )


def _register_resources() -> None:
    """Import resource modules to trigger @mcp.resource() registration."""
    from graphbase_memories.mcp import resources  # noqa: F401


def _register_prompts() -> None:
    """Import prompt modules to trigger @mcp.prompt() registration."""
    from graphbase_memories.mcp import prompts  # noqa: F401


_register_tools()
_register_resources()
_register_prompts()
