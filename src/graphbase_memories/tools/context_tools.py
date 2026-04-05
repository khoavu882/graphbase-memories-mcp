"""
Context tools: get_context.

Registered onto the FastMCP instance via register_context_tools(mcp).

Design decisions:
  [Q3] Hard token cap with priority ordering:
       decisions → service_metadata → patterns → stale_warnings
       → related_entities → recent sessions.
       Implemented in formatters/yaml_context.py — tool layer just assembles inputs.

  get_context returns empty string if no memories exist yet.
  Callers (hooks, agents) must handle empty-string gracefully.
"""

from __future__ import annotations

from fastmcp import FastMCP

from graphbase_memories._provider import get_engine
from graphbase_memories.formatters.yaml_context import render_context


def register_context_tools(mcp: FastMCP) -> None:
    """Register get_context tool."""

    @mcp.tool()
    def get_context(
        project: str,
        entity: str | None = None,
        entity_type: str = "service",
        max_tokens: int = 500,
    ) -> str:
        """
        Return a compact YAML context block for hook injection. [Q3]

        The output is hard-capped at max_tokens using priority-ordered selection:
          decisions → service_metadata → patterns → stale_warnings
          → related_entities → recent sessions.

        Designed to be called from session-start.sh via CLI subcommand:
            python -m graphbase_memories inject --project <slug>

        Returns empty string if no memories exist (graceful degradation —
        do not raise an error for empty projects).

        Args:
            project:     Project slug.
            entity:      Focus entity name. When given, only memories that reference
                         this entity are included, and co-occurring entities are
                         added under related_entities. Entity metadata is rendered
                         as service_metadata at P2 priority.
            entity_type: Entity type for the focus entity (default: "service").
                         Used only when entity is provided.
            max_tokens:  Hard cap on output size (default 500).

        Returns:
            YAML string (may be empty).
        """
        engine = get_engine(project)

        entity_metadata: dict | None = None
        if entity:
            memories = engine.get_memories_for_entity(entity, project)
            entities = engine.get_related_entities(project, entity)
            focus_node = engine.get_entity(entity, entity_type, project)
            if focus_node is not None and focus_node.metadata:
                entity_metadata = focus_node.metadata
        else:
            memories = engine.list_memories(project, limit=50)
            entities = []

        stale = engine.get_stale_memories(project, age_days=30)
        return render_context(
            memories, entities, stale, entity, max_tokens, entity_metadata
        )
