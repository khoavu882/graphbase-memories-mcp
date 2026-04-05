"""
Graph tools: graph_view.

Registered onto the FastMCP instance via register_graph_tools(mcp).

Design decisions:
  graph_view returns a compact serialisable dict suitable for direct D3.js
  consumption (nodes array + links array). Entity nodes and memory nodes share
  the same `nodes` array, distinguished by the `node_type` field.

  limit=200 default matches the CTL Graph View default to keep payloads
  token-efficient for agent use while still covering typical project sizes.
"""

from __future__ import annotations

from fastmcp import FastMCP

from graphbase_memories._provider import get_engine
from graphbase_memories.graph.engine import EntityNode


def register_graph_tools(mcp: FastMCP) -> None:
    """Register the graph_view tool."""

    @mcp.tool()
    def graph_view(
        project: str,
        limit: int = 200,
        entity_filter: str | None = None,
    ) -> dict:
        """
        Return a graph snapshot of memories and entities for a project.

        Useful for understanding the knowledge graph structure — which entities
        are most referenced, how memories are connected, and what clusters exist.

        Args:
            project:       Project slug.
            limit:         Max memories to include (newest first). Default 200.
            entity_filter: Optional entity name — if provided, return only
                           memories that reference this entity (and their
                           co-occurring entities).

        Returns:
            {
              project, total_memories, generated_at,
              nodes: [
                {id, label, node_type: "memory"|"entity", type, tags?, project}
              ],
              links: [
                {source, target, type}
              ]
            }

        Note: `total_memories` is the project's full non-deleted count.
        `len(nodes filtered to memory)` may be less if limit was applied.
        """
        engine = get_engine(project)
        data = engine.get_graph_data(project, limit=limit)

        # [P0-1] Build memory_id → {entity_id} lookup from pre-fetched links.
        # Replaces N+1 get_entities_for_memory() calls with a single dict lookup.
        entity_id_by_memory: dict[str, set[str]] = {}
        for memory_id, entity_id in data.memory_entity_links:
            entity_id_by_memory.setdefault(memory_id, set()).add(entity_id)

        # Build entity_id → EntityNode lookup for name resolution
        entity_by_id: dict[str, EntityNode] = {e.id: e for e in data.entities}

        # Build node list — memories first, then entities
        nodes = []
        seen_entity_ids: set[str] = set()

        for m in data.memories:
            # Apply entity_filter: keep only memories referencing the named entity
            if entity_filter is not None:
                linked_entity_ids = entity_id_by_memory.get(m.id, set())
                entity_names = {
                    entity_by_id[eid].name
                    for eid in linked_entity_ids
                    if eid in entity_by_id
                }
                if entity_filter not in entity_names:
                    continue
            nodes.append({
                "id":         m.id,
                "label":      m.title,
                "node_type":  "memory",
                "type":       m.type,
                "tags":       m.tags,
                "project":    m.project,
                "updated_at": m.updated_at,
                "is_expired": m.is_expired,
            })

        included_memory_ids = {n["id"] for n in nodes}

        for e in data.entities:
            if e.id not in seen_entity_ids:
                seen_entity_ids.add(e.id)
                nodes.append({
                    "id":        e.id,
                    "label":     e.name,
                    "node_type": "entity",
                    "type":      e.type,
                    "project":   e.project,
                })

        # Build links — only between nodes present in the result set
        all_node_ids = {n["id"] for n in nodes}
        links = [
            {
                "source": edge.from_id,
                "target": edge.to_id,
                "type":   edge.type,
            }
            for edge in data.edges
            if edge.from_id in all_node_ids and edge.to_id in all_node_ids
        ]

        # Add memory→entity REFERENCES links using the pre-fetched join (0 extra queries)
        for memory_id in included_memory_ids:
            for entity_id in entity_id_by_memory.get(memory_id, set()):
                if entity_id in all_node_ids:
                    links.append({
                        "source": memory_id,
                        "target": entity_id,
                        "type":   "REFERENCES",
                    })

        return {
            "project":        project,
            "total_memories": data.total_memories,
            "generated_at":   data.generated_at,
            "nodes":          nodes,
            "links":          links,
        }
