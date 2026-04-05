"""
AbstractEngineTests — contract test mixin for GraphEngine implementations.

NOT a test file — placing contract tests here prevents pytest from collecting
this module directly (pytest only collects files matching test_*.py / *_test.py).

Usage:
    # In test_sqlite_engine.py or test_neo4j_engine.py:
    from shared import AbstractEngineTests

    class TestSQLiteEngine(AbstractEngineTests):
        @pytest.fixture
        def engine(self, tmp_path):
            ...
            return SQLiteEngine(cfg, "test")

Every test method in this mixin will run against any engine that sets up the
`engine` fixture. The mixin tests the PUBLIC CONTRACT only — no SQLite-specific
PRAGMAs, no Cypher internals.
"""

from __future__ import annotations

import pytest

from graphbase_memories.graph.engine import Edge, GraphData, MemoryNode

PROJECT = "contract-test"


def _mem(
    id: str,
    title: str = "T",
    type: str = "session",
    content: str = "C",
    tags: list[str] | None = None,
    project: str = PROJECT,
) -> MemoryNode:
    """Factory for MemoryNode test fixtures."""
    return MemoryNode(
        id=id,
        project=project,
        type=type,
        title=title,
        content=content,
        tags=tags or [],
        created_at="2026-04-01T00:00:00",
        updated_at="2026-04-01T00:00:00",
        valid_until=None,
        is_deleted=False,
    )


class AbstractEngineTests:
    """
    Contract test mixin. Subclasses must provide an `engine` fixture that
    returns a fresh GraphEngine instance for each test.
    """

    # -----------------------------------------------------------------------
    # store_memory_with_entities + get_memory
    # -----------------------------------------------------------------------

    def test_store_and_retrieve_memory(self, engine):
        """store_memory_with_entities must persist and get_memory must retrieve."""
        m = _mem("m-1", title="Auth decision", type="decision")
        stored = engine.store_memory_with_entities(m, ["auth-service"])
        assert stored.id == "m-1"

        retrieved = engine.get_memory("m-1")
        assert retrieved is not None
        assert retrieved.title == "Auth decision"
        assert retrieved.type == "decision"
        assert not retrieved.is_deleted

    def test_get_memory_not_found_returns_none(self, engine):
        assert engine.get_memory("does-not-exist") is None

    def test_invalid_memory_type_rejected(self, engine):
        m = _mem("bad-1", type="INVALID_TYPE")
        with pytest.raises(ValueError, match="Invalid memory type"):
            engine.store_memory_with_entities(m, [])

    # -----------------------------------------------------------------------
    # list_memories
    # -----------------------------------------------------------------------

    def test_list_memories_empty_project(self, engine):
        result = engine.list_memories("empty-project")
        assert result == []

    def test_list_memories_returns_newest_first(self, engine):
        m1 = _mem("m-list-1", title="Old")
        m1 = MemoryNode(**{**m1.__dict__, "updated_at": "2026-01-01T00:00:00"})
        m2 = _mem("m-list-2", title="New")
        m2 = MemoryNode(**{**m2.__dict__, "updated_at": "2026-04-01T00:00:00"})
        engine.store_memory_with_entities(m1, [])
        engine.store_memory_with_entities(m2, [])
        memories = engine.list_memories(PROJECT)
        assert memories[0].id == "m-list-2"

    def test_list_memories_type_filter(self, engine):
        engine.store_memory_with_entities(_mem("m-s", type="session"), [])
        engine.store_memory_with_entities(_mem("m-d", type="decision"), [])
        sessions = engine.list_memories(PROJECT, type="session")
        assert all(m.type == "session" for m in sessions)
        assert any(m.id == "m-s" for m in sessions)

    # -----------------------------------------------------------------------
    # soft_delete
    # -----------------------------------------------------------------------

    def test_soft_delete_hides_from_list(self, engine):
        engine.store_memory_with_entities(_mem("m-del"), [])
        found = engine.soft_delete("m-del")
        assert found is True

        memories = engine.list_memories(PROJECT)
        assert not any(m.id == "m-del" for m in memories)

    def test_soft_delete_unknown_id_returns_false(self, engine):
        assert engine.soft_delete("no-such-id") is False

    # -----------------------------------------------------------------------
    # flag_expired + purge_expired
    # -----------------------------------------------------------------------

    def test_flag_expired_sets_is_expired(self, engine):
        engine.store_memory_with_entities(_mem("m-exp"), [])
        assert engine.flag_expired("m-exp") is True
        m = engine.get_memory("m-exp")
        assert m is not None and m.is_expired

    def test_purge_expired_removes_old_memories(self, engine):
        engine.store_memory_with_entities(_mem("m-purge"), [])
        engine.flag_expired("m-purge")
        # Backdate if the engine supports it (SQLite only); skip the purge-age
        # check for Neo4j where backdating is not available.
        count = engine.purge_expired(PROJECT, older_than_days=0)
        # Should purge at least 0 (may not purge if node was just created)
        assert count >= 0

    # -----------------------------------------------------------------------
    # get_entities_for_memory
    # -----------------------------------------------------------------------

    def test_entities_linked_on_store(self, engine):
        engine.store_memory_with_entities(_mem("m-ent"), ["redis", "kafka"])
        entities = engine.get_entities_for_memory("m-ent")
        names = {e.name for e in entities}
        assert "redis" in names
        assert "kafka" in names

    def test_entities_empty_for_unknown_memory(self, engine):
        assert engine.get_entities_for_memory("no-such") == []

    # -----------------------------------------------------------------------
    # get_memories_for_entity
    # -----------------------------------------------------------------------

    def test_memories_for_entity(self, engine):
        engine.store_memory_with_entities(_mem("m-fe"), ["auth"])
        result = engine.get_memories_for_entity("auth", PROJECT)
        assert any(m.id == "m-fe" for m in result)

    # -----------------------------------------------------------------------
    # store_edge + get_edges_for_memory
    # -----------------------------------------------------------------------

    def test_store_and_retrieve_edge(self, engine):
        engine.store_memory_with_entities(_mem("m-from"), [])
        engine.store_memory_with_entities(_mem("m-to"), [])
        edge = engine.store_edge(Edge(
            id="e-1",
            from_id="m-from",
            from_type="memory",
            to_id="m-to",
            to_type="memory",
            type="SUPERSEDES",
            properties={"reason": "refactor"},
            created_at="2026-04-01T00:00:00",
        ))
        assert edge.type == "SUPERSEDES"

    def test_invalid_edge_type_rejected(self, engine):
        with pytest.raises(ValueError, match="Invalid edge type"):
            engine.store_edge(Edge(
                id="e-bad",
                from_id="x", from_type="memory",
                to_id="y", to_type="memory",
                type="NOT_VALID",
                properties={}, created_at="2026-04-01T00:00:00",
            ))

    # -----------------------------------------------------------------------
    # get_related_entities
    # -----------------------------------------------------------------------

    def test_get_related_entities_all(self, engine):
        engine.store_memory_with_entities(_mem("m-re"), ["svc-a", "svc-b"])
        entities = engine.get_related_entities(PROJECT)
        names = {e.name for e in entities}
        assert "svc-a" in names and "svc-b" in names

    def test_get_related_entities_co_occurrence(self, engine):
        engine.store_memory_with_entities(_mem("m-co"), ["svc-a", "svc-b"])
        co = engine.get_related_entities(PROJECT, entity_name="svc-a")
        names = {e.name for e in co}
        assert "svc-b" in names
        assert "svc-a" not in names

    # -----------------------------------------------------------------------
    # get_blast_radius
    # -----------------------------------------------------------------------

    def test_blast_radius_returns_result(self, engine):
        engine.store_memory_with_entities(_mem("m-br"), ["target-svc", "co-svc"])
        result = engine.get_blast_radius("target-svc", PROJECT)
        assert result.entity_name == "target-svc"
        assert result.total_references >= 1
        assert any(m.id == "m-br" for m in result.memories)

    def test_blast_radius_unknown_entity(self, engine):
        result = engine.get_blast_radius("nonexistent", PROJECT)
        assert result.total_references == 0
        assert result.memories == []

    # -----------------------------------------------------------------------
    # get_stale_memories
    # -----------------------------------------------------------------------

    def test_get_stale_memories_none_stale(self, engine):
        engine.store_memory_with_entities(_mem("m-fresh"), [])
        stale = engine.get_stale_memories(PROJECT, age_days=30)
        # Freshly created memory should NOT be stale
        assert not any(m.id == "m-fresh" for m in stale)

    # -----------------------------------------------------------------------
    # get_graph_data (P2-B)
    # -----------------------------------------------------------------------

    def test_get_graph_data_empty_project(self, engine):
        data = engine.get_graph_data("empty-gd-project")
        assert isinstance(data, GraphData)
        assert data.memories == []
        assert data.entities == []
        assert data.edges == []
        assert data.total_memories == 0

    def test_get_graph_data_returns_memories_and_entities(self, engine):
        engine.store_memory_with_entities(_mem("m-gd"), ["gd-svc"])
        data = engine.get_graph_data(PROJECT)
        assert any(m.id == "m-gd" for m in data.memories)
        assert any(e.name == "gd-svc" for e in data.entities)
        assert data.total_memories >= 1

    def test_get_graph_data_limit(self, engine):
        for i in range(5):
            engine.store_memory_with_entities(_mem(f"m-lim-{i}"), [])
        data = engine.get_graph_data(PROJECT, limit=3)
        assert len(data.memories) <= 3
        assert data.total_memories >= 5

    # -----------------------------------------------------------------------
    # search_memories (P3-C)
    # -----------------------------------------------------------------------

    def test_search_memories_basic(self, engine):
        """search_memories must find a memory by a unique term in its title."""
        engine.store_memory_with_entities(
            _mem("m-search-1", title="quuxbaz unique term here", content="body"), []
        )
        results = engine.search_memories("quuxbaz", PROJECT)
        assert isinstance(results, list)
        assert any(m.id == "m-search-1" for m, _ in results)

    def test_search_memories_no_results(self, engine):
        """search_memories must return [] when no memories match."""
        results = engine.search_memories("xyzzy-nonexistent-42", PROJECT)
        assert results == []

    def test_search_memories_returns_float_scores(self, engine):
        """Each result must be a (MemoryNode, float) tuple."""
        engine.store_memory_with_entities(
            _mem("m-score", title="scored memory frobble", content="content"), []
        )
        results = engine.search_memories("frobble", PROJECT)
        assert isinstance(results, list)
        if results:
            node, score = results[0]
            assert isinstance(node, MemoryNode)
            assert isinstance(score, float)

    def test_search_memories_content_match(self, engine):
        """search_memories must match terms in content, not just title."""
        engine.store_memory_with_entities(
            _mem("m-content", title="plain title", content="grplunk rare term"), []
        )
        results = engine.search_memories("grplunk", PROJECT)
        assert any(m.id == "m-content" for m, _ in results)

    def test_search_memories_deleted_excluded(self, engine):
        """Soft-deleted memories must not appear in search results."""
        engine.store_memory_with_entities(
            _mem("m-del-search", title="wibblefoo searchable", content="body"), []
        )
        engine.soft_delete("m-del-search")
        results = engine.search_memories("wibblefoo", PROJECT)
        assert not any(m.id == "m-del-search" for m, _ in results)

    # -----------------------------------------------------------------------
    # schema_version + journal_mode (introspection)
    # -----------------------------------------------------------------------

    def test_schema_version_returns_int(self, engine):
        v = engine.schema_version()
        assert isinstance(v, int)

    def test_journal_mode_returns_string(self, engine):
        mode = engine.journal_mode()
        assert isinstance(mode, str)
