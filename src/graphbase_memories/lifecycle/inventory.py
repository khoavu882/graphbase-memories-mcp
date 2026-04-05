"""
Tool inventory: static categorized map of available Graphbase MCP tools.

Used by get_lifecycle_context and list_available_tools to communicate
capabilities to agent skills without hardcoding tool names.
"""

from __future__ import annotations

API_VERSION = "8.0"

TOOL_INVENTORY: dict[str, list[str]] = {
    "write": ["store_memory", "relate_memories"],
    "read": ["get_memory", "list_memories", "search_memories", "delete_memory"],
    "analysis": ["get_blast_radius", "get_stale_memories", "purge_expired_memories"],
    "context": ["get_context"],
    "graph": ["get_graph_data"],
    "entity": [
        "upsert_entity",
        "get_entity",
        "link_entities",
        "unlink_entities",
        "upsert_entity_with_deps",
    ],
    "session": ["store_session_with_learnings"],
    "lifecycle": [
        "resolve_active_project",
        "ensure_project",
        "get_lifecycle_context",
        "save_session_context",
        "list_available_tools",
    ],
}


def get_tool_inventory() -> dict[str, list[str] | str]:
    """
    Return a copy of the static tool inventory with API version.

    Project-independent. Safe to call without any engine or project context.
    """
    result: dict[str, list[str] | str] = {"api_version": API_VERSION}
    for category, tools in TOOL_INVENTORY.items():
        result[category] = list(tools)
    return result
