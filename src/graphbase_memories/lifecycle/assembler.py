"""
Lifecycle context assembler: builds a structured context bundle for
session startup and continuation.

Uses the existing render_context() for YAML output, and type-specific engine
queries for structured fields to ensure good coverage in large projects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from graphbase_memories._provider import get_engine
from graphbase_memories.config import Config
from graphbase_memories.formatters.yaml_context import render_context
from graphbase_memories.graph.engine import EntityNode, MemoryNode
from graphbase_memories.lifecycle.inventory import get_tool_inventory


@dataclass
class LifecycleContext:
    """Structured context bundle for startup and session continuation."""

    project_id: str
    bootstrap_state: str  # "existing" | "empty" | "created"
    yaml_context: str  # from render_context()
    recent_sessions: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    patterns: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    stale_warnings: list[dict] = field(default_factory=list)
    tool_inventory: dict = field(default_factory=dict)


def _memory_to_dict(m: MemoryNode) -> dict:
    """Convert a MemoryNode to a serializable dict for the lifecycle response."""
    return {
        "id": m.id,
        "title": m.title,
        "content": m.content,
        "type": m.type,
        "tags": m.tags,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def _entity_to_dict(e: EntityNode) -> dict:
    """Convert an EntityNode to a serializable dict."""
    return {
        "name": e.name,
        "type": e.type,
        "metadata": e.metadata,
    }


class LifecycleContextAssembler:
    """Assemble a structured startup context package from engine data."""

    def __init__(self, config: Config) -> None:
        self._config = config

    def assemble(
        self,
        project_id: str,
        entity: str | None = None,
        entity_type: str = "service",
        max_tokens: int = 500,
        include_recent_sessions: bool = True,
        include_inventory: bool = True,
    ) -> LifecycleContext:
        """
        Return a structured lifecycle context bundle.

        Args:
            project_id:  Canonical project key.
            entity:      Optional entity to scope the context to.
            entity_type: Type of the focus entity (default: "service").
            max_tokens:  Token budget for YAML context.
            include_recent_sessions: Whether to populate recent_sessions.
            include_inventory: Whether to include tool_inventory.

        Returns:
            LifecycleContext with YAML + structured fields.
        """
        engine = get_engine(project_id)

        # --- Gather memories ---
        entity_metadata: dict | None = None
        entities: list[EntityNode] = []

        if entity:
            memories = engine.get_memories_for_entity(entity, project_id)
            entities = engine.get_related_entities(project_id, entity)
            focus_node = engine.get_entity(entity, entity_type, project_id)
            entity_metadata = focus_node.metadata if focus_node else None
        else:
            memories = engine.list_memories(project_id, limit=50)
            entities = engine.get_related_entities(project_id)

        # --- Stale warnings ---
        stale = engine.get_stale_memories(project_id, age_days=30)

        # --- YAML context (reuses existing prioritized renderer) ---
        yaml_context = render_context(
            memories, entities, stale, entity, max_tokens, entity_metadata
        )

        # --- Bootstrap state ---
        if not memories and not entities:
            bootstrap_state = "empty"
        else:
            bootstrap_state = "existing"

        # --- Type-specific structured fields (two-path filter) ---
        # Fast path: filter by type from the already-fetched memories list.
        # Fallback: DB query only when the list was saturated AND the type is absent.
        _saturated = len(memories) >= 50
        decisions_nodes = [m for m in memories if m.type == "decision"][:20]
        patterns_nodes = [m for m in memories if m.type == "pattern"][:20]
        if _saturated and not decisions_nodes:
            decisions_nodes = engine.list_memories(project_id, type="decision", limit=20)
        if _saturated and not patterns_nodes:
            patterns_nodes = engine.list_memories(project_id, type="pattern", limit=20)

        decisions_out = [_memory_to_dict(m) for m in decisions_nodes]
        patterns_out = [_memory_to_dict(m) for m in patterns_nodes]

        # --- Recent sessions ---
        sessions_out: list[dict] = []
        if include_recent_sessions:
            sessions_nodes = [m for m in memories if m.type == "session"][:5]
            if _saturated and not sessions_nodes:
                sessions_nodes = engine.list_memories(project_id, type="session", limit=5)
            sessions_out = [
                {
                    "id": m.id,
                    "title": m.title,
                    "created_at": m.created_at,
                }
                for m in sessions_nodes
            ]

        # --- Stale warnings ---
        stale_out = [
            {
                "id": m.id,
                "title": m.title,
                "updated_at": m.updated_at,
            }
            for m in stale
        ]

        # --- Entity summaries ---
        entities_out = [_entity_to_dict(e) for e in entities]

        # --- Tool inventory ---
        inventory_out: dict = {}
        if include_inventory:
            inventory_out = get_tool_inventory()

        return LifecycleContext(
            project_id=project_id,
            bootstrap_state=bootstrap_state,
            yaml_context=yaml_context,
            recent_sessions=sessions_out,
            decisions=decisions_out,
            patterns=patterns_out,
            entities=entities_out,
            stale_warnings=stale_out,
            tool_inventory=inventory_out,
        )
