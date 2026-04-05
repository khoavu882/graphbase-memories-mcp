"""
Entity tools: upsert_entity, get_entity, link_entities, unlink_entities,
              upsert_entity_with_deps.

Registered onto the FastMCP instance via register_entity_tools(mcp).

Design decisions:
  [R8] Tool layer only calls _provider.get_engine() — never imports engine classes.

  upsert_entity: full metadata replacement (intentional — EntityNode.metadata
    represents current real-world state, not a history log). [Q5]

  link_entities / unlink_entities: DEPENDS_ON and IMPLEMENTS only.
    SUPERSEDES / RELATES_TO / LEARNED_DURING remain memory-scoped edges.

  get_entity: returns None as {"found": false} rather than raising — callers
    should treat not-found as "no prior history" and proceed with defaults.

  upsert_entity_with_deps [E1]: composite tool that upserts the main entity and
    auto-wires its dependency edges in one call. dep_type is REQUIRED (no default)
    because a wrong type creates a phantom entity with the wrong type, silently
    corrupting the dependency graph. The get_entity guard before auto-create
    preserves existing dependency metadata [Q5] — calling upsert with {} on an
    existing entity would wipe its data.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from graphbase_memories._provider import get_engine
from graphbase_memories.graph.engine import VALID_ENTITY_TYPES
from graphbase_memories.tools._types import ItemError


def register_entity_tools(mcp: FastMCP) -> None:
    """Register upsert_entity, get_entity, link_entities, unlink_entities."""

    @mcp.tool()
    def upsert_entity(
        project: str,
        name: str,
        type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """
        Create or update an entity by (name, type, project). [Q5]

        EntityNode.metadata represents current real-world state (service
        dependencies, owners, databases) — not a history log. Each call
        fully replaces the metadata dict. Pass an empty dict to clear it.

        Args:
            project:  Project slug.
            name:     Entity name (e.g. "auth-service", "users_table").
            type:     Entity type. Must be one of: service, file, feature,
                      concept, table, topic.
            metadata: Arbitrary key-value metadata. Default: {}.

        Returns:
            EntityNode dict with id, name, type, project, metadata,
            created_at, updated_at.

        Raises:
            ValueError if type is not a valid entity type.
        """
        engine = get_engine(project)
        entity = engine.upsert_entity(
            name=name,
            type=type,
            project=project,
            metadata=metadata or {},
        )
        return {
            "id":         entity.id,
            "name":       entity.name,
            "type":       entity.type,
            "project":    entity.project,
            "metadata":   entity.metadata,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

    @mcp.tool()
    def get_entity(
        project: str,
        name: str,
        type: str,
    ) -> dict:
        """
        Look up an entity by (name, type, project).

        Returns the entity dict when found, or {"found": false} when absent.
        Callers should treat not-found as "no prior history" — do not raise.

        Args:
            project: Project slug.
            name:    Entity name.
            type:    Entity type (service, file, feature, concept, table, topic).

        Returns:
            EntityNode dict when found, or {"found": false}.
        """
        engine = get_engine(project)
        entity = engine.get_entity(name=name, type=type, project=project)
        if entity is None:
            return {"found": False}
        return {
            "found":      True,
            "id":         entity.id,
            "name":       entity.name,
            "type":       entity.type,
            "project":    entity.project,
            "metadata":   entity.metadata,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }

    @mcp.tool()
    def link_entities(
        project: str,
        from_name: str,
        from_type: str,
        to_name: str,
        to_type: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """
        Create a directed entity→entity edge. Idempotent.

        Use DEPENDS_ON when one service/component requires another at runtime.
        Use IMPLEMENTS when a file/feature implements a concept or spec.

        Both entities must already exist — use upsert_entity first.
        Calling link_entities again with the same arguments returns the
        existing edge without creating a duplicate.

        Args:
            project:   Project slug.
            from_name: Source entity name.
            from_type: Source entity type.
            to_name:   Target entity name.
            to_type:   Target entity type.
            edge_type: Must be DEPENDS_ON or IMPLEMENTS.
            properties: Optional key-value metadata for the edge. Default: {}.

        Returns:
            Edge dict with id, from_id, from_type, to_id, to_type, type,
            properties, created_at.

        Raises:
            ValueError if either entity is not found or edge_type is invalid.
        """
        engine = get_engine(project)
        edge = engine.link_entities(
            from_name=from_name,
            from_type=from_type,
            to_name=to_name,
            to_type=to_type,
            project=project,
            edge_type=edge_type,
            properties=properties or {},
        )
        return {
            "id":         edge.id,
            "from_id":    edge.from_id,
            "from_type":  edge.from_type,
            "to_id":      edge.to_id,
            "to_type":    edge.to_type,
            "type":       edge.type,
            "properties": edge.properties,
            "created_at": edge.created_at,
        }

    @mcp.tool()
    def unlink_entities(
        project: str,
        from_name: str,
        from_type: str,
        to_name: str,
        to_type: str,
        edge_type: str,
    ) -> dict:
        """
        Delete a directed entity→entity edge. Hard-delete (not soft-delete).

        Use this when a DEPENDS_ON or IMPLEMENTS relationship no longer applies
        (e.g. a service was decomissioned or a dependency was removed). Stale
        edges corrupt blast radius analysis — keep the graph current.

        Args:
            project:   Project slug.
            from_name: Source entity name.
            from_type: Source entity type.
            to_name:   Target entity name.
            to_type:   Target entity type.
            edge_type: Must be DEPENDS_ON or IMPLEMENTS.

        Returns:
            {"deleted": true} if the edge was found and removed,
            {"deleted": false} if no matching edge existed.
        """
        engine = get_engine(project)
        deleted = engine.unlink_entities(
            from_name=from_name,
            from_type=from_type,
            to_name=to_name,
            to_type=to_type,
            project=project,
            edge_type=edge_type,
        )
        return {"deleted": deleted}

    @mcp.tool()
    def upsert_entity_with_deps(
        project: str,
        name: str,
        type: str,
        metadata: dict[str, Any],
        depends_on: list[str],
        dep_type: str,
        edge_type: str = "DEPENDS_ON",
    ) -> dict:
        """
        Upsert an entity and wire its dependency edges in one call. [E1]

        Encapsulates the graph mechanics the skill should not own:
          - Auto-creates missing dependency entities (create-only, no metadata wipe)
          - Creates DEPENDS_ON (or IMPLEMENTS) edges between the entity and each dep
          - Idempotent: link_entities is already idempotent; calling twice is safe

        Args:
            project:    Project slug.
            name:       Entity name (e.g. "auth-service").
            type:       Entity type — must be one of: service, file, feature,
                        concept, table, topic.
            metadata:   Current state metadata (full replacement [Q5]).
            depends_on: Names of dependency entities. Each is auto-created as
                        type=dep_type if it doesn't exist.
            dep_type:   Entity type for auto-created dependencies. REQUIRED —
                        no default because a wrong type creates a phantom entity
                        with incorrect type, silently corrupting the dep graph.
            edge_type:  DEPENDS_ON (default) or IMPLEMENTS.

        Returns:
            {
                entity_id:     str        — UUID of the upserted entity
                created_edges: [str]      — UUIDs of created/existing dep edges
                errors:        [{index, type, message}] — per-dep failures
            }

        Dep auto-create guard [Q5]:
            Dependencies are auto-created only when absent. If a dep entity
            already exists, it is NOT re-upserted with empty metadata — doing
            so would wipe its existing metadata due to full-replacement semantics.

        Raises:
            ValueError if type or dep_type is not a valid entity type, or if
            edge_type is not DEPENDS_ON or IMPLEMENTS. Validation runs before
            any writes so no partial state is created on invalid input.
        """
        # Validate types before any writes (fail fast, no partial state)
        if type not in VALID_ENTITY_TYPES:
            raise ValueError(
                f"Invalid type={type!r}. Valid: {sorted(VALID_ENTITY_TYPES)}"
            )
        if dep_type not in VALID_ENTITY_TYPES:
            raise ValueError(
                f"Invalid dep_type={dep_type!r}. Valid: {sorted(VALID_ENTITY_TYPES)}"
            )
        valid_edge_types = {"DEPENDS_ON", "IMPLEMENTS"}
        if edge_type not in valid_edge_types:
            raise ValueError(
                f"Invalid edge_type={edge_type!r}. Valid: {sorted(valid_edge_types)}"
            )

        engine = get_engine(project)

        # Step 1: Upsert the main entity
        entity = engine.upsert_entity(
            name=name,
            type=type,
            project=project,
            metadata=metadata or {},
        )

        created_edges: list[str] = []
        errors: list[ItemError] = []

        # Step 2: For each dep, auto-create if missing, then link
        for i, dep_name in enumerate(depends_on):
            try:
                dep_entity = engine.get_entity(dep_name, dep_type, project)
                if dep_entity is None:
                    dep_entity = engine.upsert_entity(
                        name=dep_name,
                        type=dep_type,
                        project=project,
                        metadata={},
                    )

                edge = engine.link_entities_by_id(
                    from_id=entity.id,
                    from_type="entity",
                    to_id=dep_entity.id,
                    to_type="entity",
                    project=project,
                    edge_type=edge_type,
                    properties={},
                )
                created_edges.append(edge.id)

            except Exception as exc:
                errors.append(
                    ItemError(index=i, type="dep", message=str(exc))
                )

        return {
            "entity_id":     entity.id,
            "created_edges": created_edges,
            "errors":        errors,
        }
