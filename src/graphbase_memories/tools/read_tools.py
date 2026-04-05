"""
Read tools: get_memory, list_memories, search_memories, delete_memory.

Registered onto the FastMCP instance via register_read_tools(mcp).

Design decisions:
  [R3] include_deleted=False on get_memory and list_memories.
       Soft-deleted memories are excluded by default but remain queryable.

  delete_memory performs a SOFT DELETE (is_deleted=1).
       The memory remains readable with include_deleted=True.
       Docstring explicitly states this to prevent caller confusion.

  search_memories uses FTS5 BM25 ranking. Returns (id, title, type,
       score, snippet) — snippet shows the matching context window.

  get_memory returns the full enriched dict: node fields + entities + edges.
"""

from __future__ import annotations

from fastmcp import FastMCP

from graphbase_memories._provider import get_engine, get_all_known_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_snippet(content: str, query: str, window: int = 120) -> str:
    """Return a ~window-char excerpt centred on the first query term match."""
    terms = [t for t in query.lower().split() if len(t) > 2]
    text_lower = content.lower()
    best_pos = 0
    for term in terms:
        pos = text_lower.find(term)
        if pos != -1:
            best_pos = pos
            break
    start = max(0, best_pos - 30)
    end = min(len(content), start + window)
    snippet = content[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(content):
        snippet = snippet + "…"
    return snippet


def _memory_to_dict(node) -> dict:
    return {
        "id":          node.id,
        "project":     node.project,
        "type":        node.type,
        "title":       node.title,
        "content":     node.content,
        "tags":        node.tags,
        "created_at":  node.created_at,
        "updated_at":  node.updated_at,
        "valid_until": node.valid_until,
        "is_deleted":  node.is_deleted,
        "is_expired":  node.is_expired,
    }


def _memory_to_summary(node) -> dict:
    """Compact representation for list_memories results."""
    return {
        "id":         node.id,
        "title":      node.title,
        "type":       node.type,
        "updated_at": node.updated_at,
        "tags":       node.tags,
        "is_expired": node.is_expired,
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_read_tools(mcp: FastMCP) -> None:
    """Register get_memory, list_memories, search_memories, delete_memory."""

    @mcp.tool()
    def get_memory(
        project: str,
        memory_id: str,
        include_deleted: bool = False,
    ) -> dict | None:
        """
        Retrieve a memory by ID, with linked entities and outgoing edges.

        Args:
            project:         Project slug.
            memory_id:       UUID of the memory.
            include_deleted: If True, returns soft-deleted memories too. [R3]

        Returns:
            Full memory dict with 'entities' and 'edges' fields, or null if
            not found (or deleted and include_deleted=False).
        """
        engine = get_engine(project)
        node = engine.get_memory(memory_id, include_deleted=include_deleted)
        if node is None:
            return None
        result = _memory_to_dict(node)
        result["entities"] = [
            {"id": e.id, "name": e.name, "type": e.type}
            for e in engine.get_entities_for_memory(memory_id)
        ]
        result["edges"] = [
            {"to_id": edge.to_id, "to_type": edge.to_type, "type": edge.type}
            for edge in engine.get_edges_for_memory(memory_id)
        ]
        return result

    @mcp.tool()
    def list_memories(
        project: str,
        type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[dict]:
        """
        List memories in a project, newest first.

        Args:
            project:         Project slug.
            type:            Filter by type: session | decision | pattern |
                             context | entity_fact  (null = all types).
            limit:           Max results (default 20, max 100).
            offset:          Pagination offset.
            include_deleted: Include soft-deleted memories. [R3]

        Returns:
            [{id, title, type, updated_at, tags, is_expired}]
        """
        limit = min(limit, 100)
        nodes = get_engine(project).list_memories(
            project,
            type=type,
            limit=limit,
            offset=offset,
            include_deleted=include_deleted,
        )
        return [_memory_to_summary(n) for n in nodes]

    @mcp.tool()
    def search_memories(
        query: str,
        project: str | None = None,
        type: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Full-text search across memory titles, content, and tags using FTS5 BM25.

        Returns ranked results with a content snippet showing the matching context.
        Soft-deleted memories are always excluded from search.

        Args:
            query:   Search terms. Supports FTS5 syntax: phrases ("exact match"),
                     prefix (term*), and boolean (term1 OR term2).
            project: Restrict to one project (null = search across all projects,
                     only meaningful if project is omitted from store_memory).
            type:    Restrict to one memory type.
            limit:   Max results (default 10, max 50).

        Returns:
            [{id, title, type, project, score, snippet, updated_at}]
        """
        if not query or not query.strip():
            return []
        limit = min(limit, 50)
        # Determine which engine(s) to search.
        # If project is given, use that engine directly.
        # If not, we can only search the project if we know it —
        # cross-project search requires iterating all known engines.
        if project is not None:
            results = get_engine(project).search_memories(query, project, type, limit)
            return [
                {
                    "id":         m.id,
                    "title":      m.title,
                    "type":       m.type,
                    "project":    m.project,
                    "score":      round(score, 4),
                    "snippet":    _extract_snippet(m.content, query),
                    "updated_at": m.updated_at,
                }
                for m, score in results
            ]
        else:
            # No project specified: search across all known projects on disk
            all_results: list[tuple] = []
            for proj in get_all_known_projects():
                all_results.extend(
                    get_engine(proj).search_memories(query, None, type, limit)
                )
            all_results.sort(key=lambda x: x[1], reverse=True)
            return [
                {
                    "id":         m.id,
                    "title":      m.title,
                    "type":       m.type,
                    "project":    m.project,
                    "score":      round(score, 4),
                    "snippet":    _extract_snippet(m.content, query),
                    "updated_at": m.updated_at,
                }
                for m, score in all_results[:limit]
            ]

    @mcp.tool()
    def delete_memory(
        project: str,
        memory_id: str,
    ) -> dict:
        """
        Soft-delete a memory (sets is_deleted=1).

        The memory is excluded from list_memories and search_memories by default,
        but remains readable via get_memory(memory_id, include_deleted=True).

        This is NOT permanent. To permanently remove memories, use
        purge_expired_memories() after flagging them with get_stale_memories().

        Args:
            project:   Project slug.
            memory_id: UUID of the memory to soft-delete.

        Returns:
            {memory_id, deleted, permanent}
        """
        success = get_engine(project).soft_delete(memory_id)
        return {
            "memory_id": memory_id,
            "deleted":   success,
            "permanent": False,
        }
