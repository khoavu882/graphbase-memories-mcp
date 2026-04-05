"""
Analysis tools: get_blast_radius, get_stale_memories, purge_expired_memories.

Registered onto the FastMCP instance via register_analysis_tools(mcp).

Design decisions:
  [R1] get_blast_radius returns a typed dict derived from BlastRadiusResult.
       The tool layer never exposes the dataclass directly over the MCP wire.

  [Q4] Flag-only decay pattern:
       get_stale_memories  — reads stale memories and flags them is_expired=1.
       purge_expired_memories — permanently DELETE memories already is_expired=1.
       This two-step design prevents silent data loss: the agent must explicitly
       call purge after reviewing what get_stale_memories returns.
"""

from __future__ import annotations

from fastmcp import FastMCP

from graphbase_memories._provider import get_engine


def register_analysis_tools(mcp: FastMCP) -> None:
    """Register get_blast_radius, get_stale_memories, purge_expired_memories."""

    @mcp.tool()
    def get_blast_radius(
        entity_name: str,
        project: str,
        depth: int = 2,
    ) -> dict:
        """
        Find all memories and co-occurring entities affected by a named entity.

        Use this before refactoring a component, renaming a service, or changing
        a shared pattern — it shows what memories would be invalidated.

        Args:
            entity_name: Name of the entity to analyse (e.g. "auth-service").
            project:     Project slug.
            depth:       Traversal depth (default 2). SQLite backend uses depth
                         for co-occurrence analysis; Neo4j will use N-hop Cypher.

        Returns:
            {
              entity_name, project, depth, total_references,
              memories: [{id, title, type, updated_at, tags, is_expired}],
              related_entities: [{id, name, type}]
            }
        """
        result = get_engine(project).get_blast_radius(entity_name, project, depth)
        return {
            "entity_name":      result.entity_name,
            "project":          result.project,
            "depth":            result.depth,
            "total_references": result.total_references,
            "memories": [
                {
                    "id":         m.id,
                    "title":      m.title,
                    "type":       m.type,
                    "updated_at": m.updated_at,
                    "tags":       m.tags,
                    "is_expired": m.is_expired,
                }
                for m in result.memories
            ],
            "related_entities": [
                {"id": e.id, "name": e.name, "type": e.type}
                for e in result.related_entities
            ],
        }

    @mcp.tool()
    def get_stale_memories(
        project: str,
        age_days: int = 30,
    ) -> list[dict]:
        """
        List memories not updated in age_days days and flag them is_expired=1. [Q4]

        This is NOT a deletion — it builds a review queue. Call
        purge_expired_memories() to permanently remove them after review.

        Args:
            project:  Project slug.
            age_days: Staleness threshold in days (default 30).

        Returns:
            [{id, title, type, updated_at, tags, is_expired}]
        """
        engine = get_engine(project)
        stale = engine.get_stale_memories(project, age_days)
        # Flag each stale memory as expired (Q4: flag-only, no auto-delete)
        for node in stale:
            if not node.is_expired:
                engine.flag_expired(node.id)
        return [
            {
                "id":         n.id,
                "title":      n.title,
                "type":       n.type,
                "updated_at": n.updated_at,
                "tags":       n.tags,
                "is_expired": True,
            }
            for n in stale
        ]

    @mcp.tool()
    def purge_expired_memories(
        project: str,
        older_than_days: int = 90,
    ) -> dict:
        """
        Permanently DELETE expired memories older than older_than_days. [Q4]

        WARNING: IRREVERSIBLE. Review get_stale_memories() output first.

        Recommended workflow:
          1. Call get_stale_memories(project, age_days=30) — review list
          2. Optionally call delete_memory() on specific records to unmark
          3. Call purge_expired_memories(project, older_than_days=90) to finalize

        Args:
            project:          Project slug.
            older_than_days:  Purge threshold in days (default 90).

        Returns:
            {project, purged_count, older_than_days}
        """
        count = get_engine(project).purge_expired(project, older_than_days)
        return {
            "project":         project,
            "purged_count":    count,
            "older_than_days": older_than_days,
        }
