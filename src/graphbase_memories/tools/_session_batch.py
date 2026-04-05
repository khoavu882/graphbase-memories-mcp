"""
Session batch logic: shared between store_session_with_learnings and lifecycle
save_session_context.

Extracted from session_tools.py to prevent behavioral drift between the
Phase 7 MCP tool and the Phase 8 lifecycle coordinator (architecture review C1).

Design decisions carried forward from session_tools.py:
  [S1] Composite workflow — graph mechanics fully encapsulated.
  [S2] Per-item atomicity — failure at item N does not roll back 0..N-1.
  [S3] Hybrid dedup: exact title equality + BM25 > threshold.
  [S4] FTS5 phrase quoting prevents operator injection.
"""

from __future__ import annotations

from uuid import uuid4

from graphbase_memories._utils import _now
from graphbase_memories.graph.engine import Edge, GraphEngine, MemoryNode
from graphbase_memories.tools._types import (
    DecisionResult,
    ItemError,
    MemoryInput,
    PatternResult,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# BM25 post-negation score threshold for SUPERSEDES dedup.
# engine.search_memories() returns POSITIVE scores (higher = better match)
# because sqlite_engine negates raw FTS5 rank before returning.
# Score > 1.5 → strong title overlap / high-confidence duplicate.
SUPERSEDES_THRESHOLD: float = 1.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fts5_phrase(text: str) -> str:
    """
    Wrap text in FTS5 phrase syntax to prevent operator injection. [S4]

    FTS5 special characters (", *, (, ), -) cause OperationalError when passed
    raw as a query. Quoting the entire title as a phrase prevents this and
    also improves dedup precision (exact phrase vs. tokenised OR).
    """
    return '"' + text.replace('"', '""') + '"'


def make_node(
    project: str,
    item: MemoryInput,
    memory_type: str,
) -> MemoryNode:
    """Build a MemoryNode from a MemoryInput dict."""
    now = _now()
    return MemoryNode(
        id=str(uuid4()),
        project=project,
        type=memory_type,
        title=item["title"],
        content=item["content"],
        tags=item.get("tags") or [],
        created_at=now,
        updated_at=now,
        valid_until=None,
        is_deleted=False,
    )


def make_edge(from_id: str, to_id: str, edge_type: str) -> Edge:
    """Build a directed memory→memory Edge."""
    return Edge(
        id=str(uuid4()),
        from_id=from_id,
        from_type="memory",
        to_id=to_id,
        to_type="memory",
        type=edge_type,
        properties={},
        created_at=_now(),
    )


# ---------------------------------------------------------------------------
# Core batch logic
# ---------------------------------------------------------------------------

def store_session_batch(
    engine: GraphEngine,
    project: str,
    session: MemoryInput,
    decisions: list[MemoryInput],
    patterns: list[MemoryInput],
) -> dict:
    """
    Store a session memory with all its decisions and patterns.

    Encapsulates the graph mechanics the skill should not own:
      - LEARNED_DURING edges from each decision/pattern to the session node
      - SUPERSEDES dedup: searches for a prior decision with the same title
        (BM25 score > threshold) and links the new one as superseding it

    Args:
        engine:    GraphEngine instance for the target project.
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
        items 0..N-1.
    """
    # ------------------------------------------------------------------
    # Step 1: Store session memory (atomic — raises on failure)
    # ------------------------------------------------------------------
    session_node = make_node(project, session, "session")
    session_node = engine.store_memory_with_entities(
        session_node, session.get("entities") or []
    )
    session_id = session_node.id

    decisions_out: list[DecisionResult] = []
    patterns_out: list[PatternResult] = []
    errors: list[ItemError] = []

    # ------------------------------------------------------------------
    # Step 2: Store decisions with dedup + LEARNED_DURING
    # ------------------------------------------------------------------
    for i, decision in enumerate(decisions):
        try:
            prior_id: str | None = None
            try:
                results = engine.search_memories(
                    query=_fts5_phrase(decision["title"]),
                    project=project,
                    type="decision",
                    limit=1,
                )
                if results:
                    top_mem, top_score = results[0]
                    if (top_mem.title == decision["title"]
                            or top_score > SUPERSEDES_THRESHOLD):
                        prior_id = top_mem.id
            except Exception:
                # Search failure (e.g. FTS5 not available) → skip dedup
                prior_id = None

            with engine.batch_write():
                decision_node = make_node(project, decision, "decision")
                decision_node = engine.store_memory_with_entities(
                    decision_node, decision.get("entities") or []
                )

                # SUPERSEDES edge (new → prior), if dedup hit
                if prior_id and prior_id != decision_node.id:
                    engine.store_edge(
                        make_edge(decision_node.id, prior_id, "SUPERSEDES")
                    )

                # LEARNED_DURING edge (decision → session)
                engine.store_edge(
                    make_edge(decision_node.id, session_id, "LEARNED_DURING")
                )

            decisions_out.append(
                DecisionResult(id=decision_node.id, superseded_id=prior_id)
            )

        except Exception as exc:
            errors.append(
                ItemError(index=i, type="decision", message=str(exc))
            )

    # ------------------------------------------------------------------
    # Step 3: Store patterns with LEARNED_DURING
    # ------------------------------------------------------------------
    for i, pattern in enumerate(patterns):
        try:
            with engine.batch_write():
                pattern_node = make_node(project, pattern, "pattern")
                pattern_node = engine.store_memory_with_entities(
                    pattern_node, pattern.get("entities") or []
                )

                # LEARNED_DURING edge (pattern → session)
                engine.store_edge(
                    make_edge(pattern_node.id, session_id, "LEARNED_DURING")
                )

            patterns_out.append(PatternResult(id=pattern_node.id))

        except Exception as exc:
            errors.append(
                ItemError(index=i, type="pattern", message=str(exc))
            )

    return {
        "session_id": session_id,
        "decisions":  decisions_out,
        "patterns":   patterns_out,
        "errors":     errors,
    }
