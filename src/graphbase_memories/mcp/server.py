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
        governance,
        hygiene,
        impact,
        retrieval,
        session,
    )


_register_tools()
