"""
DedupEngine — S-2: hash-first + Jaccard-based fuzzy check.

Step 1: Exact SHA-256 content_hash match → duplicate_skip (deterministic, O(1))
Step 2: FULLTEXT top-5 candidates → Jaccard similarity on title token sets
        Jaccard ≥ 0.7  → supersede
        Jaccard 0.5-0.69 → manual_review
        Jaccard < 0.5  → new

NOTE: dedup check is called INSIDE the write transaction function to ensure
      correct behavior under neo4j driver's idempotent retry mechanism.
"""

from __future__ import annotations

import re

from neo4j import AsyncDriver

from graphbase_memories.graph.repositories import decision_repo, pattern_repo
from graphbase_memories.mcp.schemas.enums import DedupOutcome


def _tokenize(text: str) -> set[str]:
    """Lowercase word tokens for Jaccard."""
    text = text.lower()
    return set(re.findall(r"\w+", text))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


async def check_decision(
    *,
    title: str,
    rationale: str,
    content_hash: str,
    scope: str,
    new_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> tuple[DedupOutcome, str | None]:
    """
    Returns (DedupOutcome, older_decision_id_if_superseding).
    """
    # Step 1: exact hash
    existing = await decision_repo.find_by_hash(content_hash, scope, driver, database)
    if existing:
        return DedupOutcome.duplicate_skip, existing["id"]

    # Step 2: FULLTEXT candidates → Jaccard
    query = f"{title} {rationale}"
    candidates = await decision_repo.fulltext_candidates(query, scope, new_id, driver, database)

    new_tokens = _tokenize(title + " " + rationale)
    best_score = 0.0
    best_id = None

    for candidate in candidates:
        candidate_tokens = _tokenize(candidate["title"] + " " + candidate.get("rationale", ""))
        score = _jaccard(new_tokens, candidate_tokens)
        if score > best_score:
            best_score = score
            best_id = candidate["id"]

    if best_score >= 0.7:
        return DedupOutcome.supersede, best_id
    if best_score >= 0.5:
        return DedupOutcome.manual_review, best_id

    return DedupOutcome.new, None


async def check_pattern(
    *,
    trigger: str,
    content_hash: str,
    scope: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> DedupOutcome:
    """Pattern dedup — hash-only (patterns are more structured, exact match is sufficient)."""
    existing = await pattern_repo.find_by_hash(content_hash, scope, driver, database)
    return DedupOutcome.duplicate_skip if existing else DedupOutcome.new
