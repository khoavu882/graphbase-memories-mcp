"""
Write tools: store_memory, relate_memories.

Registered onto the FastMCP instance via register_write_tools(mcp).
The tool layer never imports from sqlite_engine directly — only via _provider.

Design decisions:
  [R2] No update_memory tool by design. The graph is append-oriented.
       To update: store_memory() with revised content, then
       relate_memories(new_id, old_id, 'SUPERSEDES').
       The old memory remains readable via get_memory(old_id, include_deleted=False).
       get_context() automatically excludes superseded memories.

  [R8] store_memory calls engine.store_memory_with_entities() — the single
       high-level write method. The 3-step protocol (store + entity upsert + link)
       is encapsulated inside the engine.

  Direction validation for relate_memories:
       LEARNED_DURING: from_type ∈ {decision,pattern,context,entity_fact} → session
       SUPERSEDES:     any memory type → any memory type
       RELATES_TO:     any memory type → any memory type
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastmcp import FastMCP

from graphbase_memories._provider import get_engine
from graphbase_memories.graph.engine import Edge, MemoryNode, VALID_MEMORY_TYPES

# ---------------------------------------------------------------------------
# Direction constraints for relate_memories
# ---------------------------------------------------------------------------

_RELATION_RULES: dict[str, dict[str, set[str] | None]] = {
    "SUPERSEDES": {
        "from_types": None,   # any
        "to_types":   None,   # any
    },
    "RELATES_TO": {
        "from_types": None,
        "to_types":   None,
    },
    "LEARNED_DURING": {
        "from_types": {"decision", "pattern", "context", "entity_fact"},
        "to_types":   {"session"},
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_write_tools(mcp: FastMCP) -> None:
    """Register store_memory and relate_memories onto the FastMCP instance."""

    @mcp.tool()
    def store_memory(
        project: str,
        title: str,
        content: str,
        type: str = "context",
        entities: list[str] | None = None,
        tags: list[str] | None = None,
        valid_until: str | None = None,
    ) -> dict:
        """
        Store a new memory node in the graph.

        Args:
            project:     Project slug (e.g. 'claude-code-agent-workflow').
            title:       Short label for this memory (≤ 100 chars recommended).
            content:     Markdown body of the memory.
            type:        One of: session | decision | pattern | context | entity_fact
            entities:    Canonical names of entities this memory references.
                         Each is auto-created as an Entity node if it doesn't exist.
            tags:        Free-form string tags for filtering and search.
            valid_until: ISO-8601 expiry datetime. Null = perpetual.

        Returns:
            {id, title, created_at}

        Update pattern [R2]:
            There is no update_memory tool — the graph is append-oriented.
            To revise a memory: call store_memory() with new content,
            then relate_memories(new_id, old_id, 'SUPERSEDES').
        """
        if type not in VALID_MEMORY_TYPES:
            raise ValueError(
                f"Invalid type={type!r}. Valid: {sorted(VALID_MEMORY_TYPES)}"
            )
        entity_names: list[str] = entities or []
        memory_tags: list[str] = tags or []

        node = MemoryNode(
            id=str(uuid4()),
            project=project,
            type=type,
            title=title,
            content=content,
            tags=memory_tags,
            created_at=_now(),
            updated_at=_now(),
            valid_until=valid_until,
            is_deleted=False,
        )
        result = get_engine(project).store_memory_with_entities(node, entity_names)
        return {
            "id":         result.id,
            "title":      result.title,
            "type":       result.type,
            "created_at": result.created_at,
        }

    @mcp.tool()
    def relate_memories(
        project: str,
        from_id: str,
        to_id: str,
        relationship: str,
    ) -> dict:
        """
        Create a directed edge between two memory nodes.

        Args:
            project:      Project slug (both memories must be in this project).
            from_id:      UUID of the source memory.
            to_id:        UUID of the target memory.
            relationship: SUPERSEDES | RELATES_TO | LEARNED_DURING

        Direction rules:
            SUPERSEDES:     from=newer → to=older (any memory type)
            RELATES_TO:     any → any
            LEARNED_DURING: from ∈ {decision,pattern,context,entity_fact}
                            to   ∈ {session}

        Returns:
            {id, from_id, to_id, type, created_at}
        """
        if relationship not in _RELATION_RULES:
            valid = sorted(_RELATION_RULES.keys())
            raise ValueError(
                f"Unknown relationship={relationship!r}. Valid: {valid}"
            )
        if from_id == to_id:
            raise ValueError("from_id and to_id must be different memories.")

        engine = get_engine(project)

        # Load both nodes to validate direction constraints
        from_mem = engine.get_memory(from_id, include_deleted=True)
        to_mem   = engine.get_memory(to_id,   include_deleted=True)

        if from_mem is None:
            raise ValueError(f"Memory not found: from_id={from_id!r}")
        if to_mem is None:
            raise ValueError(f"Memory not found: to_id={to_id!r}")

        rules = _RELATION_RULES[relationship]
        from_types: set[str] | None = rules["from_types"]
        to_types:   set[str] | None = rules["to_types"]

        if from_types is not None and from_mem.type not in from_types:
            raise ValueError(
                f"{relationship} requires from memory type ∈ {sorted(from_types)}, "
                f"but from_id has type={from_mem.type!r}"
            )
        if to_types is not None and to_mem.type not in to_types:
            raise ValueError(
                f"{relationship} requires to memory type ∈ {sorted(to_types)}, "
                f"but to_id has type={to_mem.type!r}"
            )

        edge = Edge(
            id=str(uuid4()),
            from_id=from_id,
            from_type="memory",
            to_id=to_id,
            to_type="memory",
            type=relationship,
            properties={},
            created_at=_now(),
        )
        result = engine.store_edge(edge)
        return {
            "id":         result.id,
            "from_id":    result.from_id,
            "to_id":      result.to_id,
            "type":       result.type,
            "created_at": result.created_at,
        }
