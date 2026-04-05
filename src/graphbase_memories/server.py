"""
graphbase-memories MCP server entry point.

Run as MCP stdio server:
    python -m graphbase_memories server
    python -m graphbase_memories          (default)

Tool registration: each phase adds a register_*_tools(mcp) call here.
The mcp instance is the single FastMCP singleton shared across the process.
"""

from fastmcp import FastMCP

mcp = FastMCP(
    name="graphbase-memories",
    instructions=(
        "Graph-backed coding agent memory. "
        "Stores episodic memories (sessions, decisions, patterns) as a graph. "
        "Tools: store_memory, relate_memories (Phase 2+), "
        "get_memory, list_memories, search_memories, delete_memory (Phase 3+), "
        "get_blast_radius, get_stale_memories, purge_expired_memories (Phase 4+), "
        "get_context (Phase 5+)."
    ),
)

# --- Phase 2: Write tools ---
from graphbase_memories.tools.write_tools import register_write_tools  # noqa: E402
register_write_tools(mcp)

# --- Phase 3: Read tools ---
from graphbase_memories.tools.read_tools import register_read_tools  # noqa: E402
register_read_tools(mcp)

# --- Phase 4: Analysis tools ---
from graphbase_memories.tools.analysis_tools import register_analysis_tools  # noqa: E402
register_analysis_tools(mcp)

# --- Phase 5: Context tools ---
from graphbase_memories.tools.context_tools import register_context_tools  # noqa: E402
register_context_tools(mcp)

# --- Phase 2 (P2-B): Graph view tool ---
from graphbase_memories.tools.graph_tools import register_graph_tools  # noqa: E402
register_graph_tools(mcp)


def get_mcp() -> FastMCP:
    """Return the configured FastMCP instance (used by __main__ and tests)."""
    return mcp
