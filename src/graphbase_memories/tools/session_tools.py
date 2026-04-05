"""
Session tools: store_session_with_learnings.

Registered onto the FastMCP instance via register_session_tools(mcp).

Design decisions:
  [S1] store_session_with_learnings is a composite workflow tool — it owns the
       HOW of persisting a session narrative with its associated decisions and
       patterns, including SUPERSEDES deduplication and LEARNED_DURING edges.
       Skills call this tool with WHAT (synthesised content); the graph mechanics
       are fully encapsulated here.

  [S2] Session commit is atomic. Decision and pattern writes are individually
       atomic. A failure at item N does not roll back items 0..N-1. The errors
       list identifies failed items; callers can retry via store_memory +
       relate_memories primitives.

  [S3] Dedup uses a hybrid strategy:
       (a) Exact title equality — catches cold-start cases when only 1 decision
           exists in the corpus (BM25 IDF → 0 when N=df=1, making scores near-zero
           regardless of match quality).
       (b) BM25 score > _SUPERSEDES_THRESHOLD — catches near-duplicates in a
           mature corpus where IDF is meaningful.
       The engine negates raw FTS5 rank (sqlite_engine.py ~557: `(-f.rank) AS score`)
       so scores are positive; higher = better match. 1.5 ≈ strong partial overlap.
       Neo4j Lucene BM25 scores may differ — add Config support when Neo4j is primary.

  [S4] _fts5_phrase() wraps titles in FTS5 phrase syntax to prevent injection
       from special characters (", *, (, ), -) that would cause OperationalError
       or silently skip dedup.

Implementation note (Phase 8):
  Core batch logic has been extracted to _session_batch.py so both this MCP tool
  and the lifecycle coordinator share the same dedup/edge behavior (review C1).
"""

from __future__ import annotations

from fastmcp import FastMCP

from graphbase_memories._provider import get_engine
from graphbase_memories.tools._session_batch import store_session_batch
from graphbase_memories.tools._types import MemoryInput


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_session_tools(mcp: FastMCP) -> None:
    """Register store_session_with_learnings (Phase 7)."""

    @mcp.tool()
    def store_session_with_learnings(
        project: str,
        session: MemoryInput,
        decisions: list[MemoryInput],
        patterns: list[MemoryInput],
    ) -> dict:
        """
        Store a session memory with all its decisions and patterns in one call.

        Encapsulates the graph mechanics the skill should not own:
          - LEARNED_DURING edges from each decision/pattern to the session node
          - SUPERSEDES dedup: searches for a prior decision with the same title
            (BM25 score > 1.5) and links the new one as superseding it
          - SESSION_ID threading across all items

        Args:
            project:   Project slug.
            session:   Session narrative — title, content, entities, tags.
            decisions: List of decisions discovered or revised this session.
            patterns:  List of patterns observed or formalised this session.

        Returns:
            {
                session_id:  str            — UUID of the stored session memory
                decisions:   [{id, superseded_id}]   — per-decision result
                patterns:    [{id}]                   — per-pattern result
                errors:      [{index, type, message}] — per-item failures
            }

        Atomicity [S2]:
            Session memory commit is atomic. Each decision and pattern is
            individually atomic. A failure at item N does NOT roll back
            items 0..N-1. Use the errors list to identify and retry failed
            items via store_memory + relate_memories primitives.
        """
        engine = get_engine(project)
        return store_session_batch(engine, project, session, decisions, patterns)
