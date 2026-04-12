"""
Integration: scope, dedup, write, and retrieval engines against live Neo4j.
"""

from __future__ import annotations

from datetime import date

from conftest import TEST_DB

# ── Scope engine ─────────────────────────────────────────────────


async def test_scope_unresolved_without_project_id(driver):
    from graphbase_memories.engines.scope import validate
    from graphbase_memories.mcp.schemas.enums import ScopeState

    state = await validate(None, None, driver, TEST_DB)
    assert state == ScopeState.unresolved


async def test_scope_uncertain_unknown_project(driver):
    from graphbase_memories.engines.scope import validate
    from graphbase_memories.mcp.schemas.enums import ScopeState

    state = await validate("nonexistent-project-xyz", None, driver, TEST_DB)
    assert state == ScopeState.uncertain


async def test_scope_resolved_existing_project(driver, fresh_project):
    from graphbase_memories.engines.scope import validate
    from graphbase_memories.mcp.schemas.enums import ScopeState

    state = await validate(fresh_project, None, driver, TEST_DB)
    assert state == ScopeState.resolved


# ── Dedup engine ─────────────────────────────────────────────────


async def test_dedup_new_decision(driver, fresh_project):
    from graphbase_memories.engines.dedup import check_decision
    from graphbase_memories.graph.repositories.decision_repo import compute_content_hash
    from graphbase_memories.mcp.schemas.enums import DedupOutcome

    title = "Use Redis for session store"
    rationale = "stateless API needs external session"
    content_hash = compute_content_hash(title, rationale)

    outcome, related_id = await check_decision(
        title=title,
        rationale=rationale,
        content_hash=content_hash,
        scope="project",
        new_id="test-id-001",
        driver=driver,
        database=TEST_DB,
    )
    assert outcome == DedupOutcome.new
    assert related_id is None


async def test_dedup_exact_duplicate(driver, fresh_project):
    """Saving the same decision twice → second must be duplicate_skip."""
    from graphbase_memories.engines.write import save_decision
    from graphbase_memories.mcp.schemas.artifacts import DecisionSchema
    from graphbase_memories.mcp.schemas.enums import DedupOutcome, MemoryScope

    decision = DecisionSchema(
        title="Adopt trunk-based development",
        rationale="reduces merge conflicts and enables CI",
        owner="team",
        date=date.today(),
        scope=MemoryScope.project,
        confidence=0.9,
    )

    r1 = await save_decision(decision, fresh_project, None, None, driver, TEST_DB)
    assert r1.artifact_id is not None

    r2 = await save_decision(decision, fresh_project, None, None, driver, TEST_DB)
    assert r2.dedup_outcome == DedupOutcome.duplicate_skip
    assert r2.artifact_id == r1.artifact_id, "Duplicate must return original artifact_id"


# ── Write engine ─────────────────────────────────────────────────


async def test_write_session_blocked_unresolved_scope(driver):
    """Write to unresolved scope (no project_id) must be blocked."""
    from graphbase_memories.engines.write import save_session
    from graphbase_memories.mcp.schemas.artifacts import SessionSchema
    from graphbase_memories.mcp.schemas.enums import MemoryScope, SaveStatus

    # fresh unknown project_id
    session_data = SessionSchema(
        objective="test",
        actions_taken=[],
        decisions_made=[],
        open_items=[],
        next_actions=[],
        save_scope=MemoryScope.project,
    )
    result = await save_session(session_data, "unknown-project-xyz", None, driver, TEST_DB)
    assert result.status == SaveStatus.blocked_scope


async def test_write_full_session(driver, fresh_project):
    from graphbase_memories.engines.write import save_session
    from graphbase_memories.mcp.schemas.artifacts import SessionSchema
    from graphbase_memories.mcp.schemas.enums import MemoryScope, SaveStatus

    session_data = SessionSchema(
        objective="Refactor auth service",
        actions_taken=["moved to OAuth2"],
        decisions_made=["drop basic auth"],
        open_items=["update docs"],
        next_actions=["notify mobile team"],
        save_scope=MemoryScope.project,
    )
    result = await save_session(session_data, fresh_project, None, driver, TEST_DB)
    assert result.status == SaveStatus.saved
    assert result.artifact_id is not None


async def test_write_global_decision_requires_token(driver, fresh_project):
    from graphbase_memories.engines.write import save_decision
    from graphbase_memories.mcp.schemas.artifacts import DecisionSchema
    from graphbase_memories.mcp.schemas.enums import MemoryScope, SaveStatus

    decision = DecisionSchema(
        title="Global: all services use OpenTelemetry",
        rationale="unified observability",
        owner="platform-team",
        date=date.today(),
        scope=MemoryScope.global_,
        confidence=0.95,
    )
    result = await save_decision(decision, fresh_project, None, None, driver, TEST_DB)
    assert result.status == SaveStatus.failed
    assert "governance token" in (result.message or "").lower()


async def test_write_global_decision_with_valid_token(driver, fresh_project):
    from graphbase_memories.engines.write import save_decision
    from graphbase_memories.graph.repositories import token_repo
    from graphbase_memories.mcp.schemas.artifacts import DecisionSchema
    from graphbase_memories.mcp.schemas.enums import MemoryScope, SaveStatus

    token = await token_repo.create("Global observability standard", 300, driver, TEST_DB)

    decision = DecisionSchema(
        title="Global: all services emit OpenTelemetry spans",
        rationale="platform-wide observability mandate",
        owner="platform-team",
        date=date.today(),
        scope=MemoryScope.global_,
        confidence=0.95,
    )
    result = await save_decision(decision, fresh_project, None, token.id, driver, TEST_DB)
    assert result.status == SaveStatus.saved
    assert result.artifact_id is not None


# ── Retrieval engine ─────────────────────────────────────────────


async def test_retrieval_empty_new_project(driver, fresh_project):
    from graphbase_memories.engines.retrieval import execute
    from graphbase_memories.mcp.schemas.enums import RetrievalStatus

    bundle = await execute(
        project_id=fresh_project,
        scope="project",
        focus=None,
        categories=None,
        topic=None,
        driver=driver,
        database=TEST_DB,
    )
    assert bundle.retrieval_status == RetrievalStatus.empty
    assert bundle.items == []


async def test_retrieval_returns_saved_decisions(driver, fresh_project):
    from graphbase_memories.engines.retrieval import execute
    from graphbase_memories.engines.write import save_decision
    from graphbase_memories.mcp.schemas.artifacts import DecisionSchema
    from graphbase_memories.mcp.schemas.enums import MemoryScope, RetrievalStatus

    decision = DecisionSchema(
        title="Use gRPC for internal comms",
        rationale="lower latency than HTTP",
        owner="arch-team",
        date=date.today(),
        scope=MemoryScope.project,
        confidence=0.88,
    )
    await save_decision(decision, fresh_project, None, None, driver, TEST_DB)

    bundle = await execute(
        project_id=fresh_project,
        scope="project",
        focus=None,
        categories=None,
        topic=None,
        driver=driver,
        database=TEST_DB,
    )
    assert bundle.retrieval_status == RetrievalStatus.succeeded
    assert len(bundle.items) >= 1
    titles = [item.get("title") for item in bundle.items]
    assert "Use gRPC for internal comms" in titles


async def test_retrieval_keyword_returns_bm25_results(driver, fresh_project):
    """keyword= triggers BM25 fusion; returned items carry _rrf_score."""
    from graphbase_memories.engines.retrieval import execute
    from graphbase_memories.engines.write import save_decision
    from graphbase_memories.mcp.schemas.artifacts import DecisionSchema
    from graphbase_memories.mcp.schemas.enums import MemoryScope, RetrievalStatus

    unique_word = "xyloquuxbm25rrf"
    decision = DecisionSchema(
        title=f"Adopt {unique_word} caching strategy",
        rationale="improves p99 latency with minimal overhead",
        owner="arch-team",
        date=date.today(),
        scope=MemoryScope.project,
        confidence=0.8,
    )
    await save_decision(decision, fresh_project, None, None, driver, TEST_DB)

    bundle = await execute(
        project_id=fresh_project,
        scope="project",
        focus=None,
        categories=None,
        topic=None,
        keyword=unique_word,
        driver=driver,
        database=TEST_DB,
    )
    assert bundle.retrieval_status == RetrievalStatus.succeeded
    titles = [item.get("title") for item in bundle.items]
    assert any(unique_word in (t or "") for t in titles), "BM25 should surface the unique-word decision"
    assert all("_rrf_score" in item for item in bundle.items), "All items must carry _rrf_score"


async def test_retrieval_keyword_none_unchanged(driver, fresh_project):
    """keyword=None leaves items without _rrf_score (legacy path unchanged)."""
    from graphbase_memories.engines.retrieval import execute
    from graphbase_memories.engines.write import save_decision
    from graphbase_memories.mcp.schemas.artifacts import DecisionSchema
    from graphbase_memories.mcp.schemas.enums import MemoryScope

    decision = DecisionSchema(
        title="Cache reads with Redis",
        rationale="reduce DB load",
        owner="team",
        date=date.today(),
        scope=MemoryScope.project,
        confidence=0.85,
    )
    await save_decision(decision, fresh_project, None, None, driver, TEST_DB)

    bundle = await execute(
        project_id=fresh_project,
        scope="project",
        focus=None,
        categories=None,
        topic=None,
        keyword=None,
        driver=driver,
        database=TEST_DB,
    )
    assert not any("_rrf_score" in item for item in bundle.items), "_rrf_score must be absent without keyword"


def test_rrf_fuse_deduplicates():
    """_rrf_fuse merges overlapping lists without duplicates; shared items score highest."""
    from graphbase_memories.engines.retrieval import _rrf_fuse

    graph = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
    fts = [{"id": "b", "title": "B"}, {"id": "c", "title": "C"}]
    result = _rrf_fuse(graph, fts)

    ids = [item["id"] for item in result]
    assert len(ids) == len(set(ids)), "No duplicate IDs in fused result"
    assert set(ids) == {"a", "b", "c"}

    b_score = next(item["_rrf_score"] for item in result if item["id"] == "b")
    c_score = next(item["_rrf_score"] for item in result if item["id"] == "c")
    assert b_score > c_score, "Item in both lists scores higher than FTS-only item"
    assert all("_rrf_score" in item for item in result)
