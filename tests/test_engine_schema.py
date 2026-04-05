"""
Schema-level tests: B1 (entity-entity edges), B3 (migration idempotent), R7 (WAL).
These test the SQLiteEngine directly — no MCP layer involved.
"""
from __future__ import annotations

import pytest
from graphbase_memories.graph.engine import Edge
from conftest import PROJECT


def test_wal_mode_enabled(engine):
    """[R7] WAL mode must be set on connection open."""
    assert engine.journal_mode() == "wal"


def test_schema_version(engine):
    """[B3] schema_version() must return 1 after first init."""
    assert engine.schema_version() == 1


def test_schema_migration_idempotent(tmp_path):
    """[B3] Second initialization of the same DB must not raise."""
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine

    cfg = Config(backend="sqlite", data_dir=tmp_path, log_level="WARNING", log_to_file=False)
    SQLiteEngine(cfg, "idempotent")
    SQLiteEngine(cfg, "idempotent")   # must not raise


def test_entity_entity_edge_storable(engine):
    """[B1] Entity→Entity edges must be storable without FK constraint error."""
    edge = engine.store_edge(
        Edge(
            id="ee-1",
            from_id="svc-a",
            from_type="entity",
            to_id="svc-b",
            to_type="entity",
            type="DEPENDS_ON",
            properties={},
            created_at="2026-04-04T00:00:00",
        )
    )
    assert edge.from_type == "entity"
    assert edge.to_type == "entity"


def test_memory_memory_edge_storable(engine):
    """[B1] Memory→Memory edges (SUPERSEDES) must be storable."""
    edge = engine.store_edge(
        Edge(
            id="mm-1",
            from_id="mem-new",
            from_type="memory",
            to_id="mem-old",
            to_type="memory",
            type="SUPERSEDES",
            properties={},
            created_at="2026-04-04T00:00:00",
        )
    )
    assert edge.type == "SUPERSEDES"


def test_invalid_edge_type_rejected(engine):
    """store_edge must raise ValueError for unknown edge types."""
    with pytest.raises(ValueError, match="Invalid edge type"):
        engine.store_edge(
            Edge(
                id="bad-1",
                from_id="x", from_type="memory",
                to_id="y", to_type="memory",
                type="UNKNOWN_TYPE",
                properties={}, created_at="2026-04-04T00:00:00",
            )
        )


def test_schema_downgrade_raises_runtime_error(tmp_path):
    """[M2] Opening a newer-version DB with older code must raise RuntimeError."""
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine, SCHEMA_VERSION
    import sqlite3

    # Manually create a DB with a future schema version
    db_dir = tmp_path / "downgrade_test"
    db_dir.mkdir()
    db_path = db_dir / "memories.db"
    con = sqlite3.connect(str(db_path))
    con.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    con.commit()
    con.close()

    cfg = Config(backend="sqlite", data_dir=tmp_path, log_level="WARNING", log_to_file=False)
    with pytest.raises(RuntimeError, match="newer than the installed"):
        SQLiteEngine(cfg, "downgrade_test")


def test_search_memories_invalid_fts_query_returns_empty(engine):
    """[sqlite_engine] FTS5 OperationalError from bad query syntax must return []."""
    # FTS5 raises OperationalError for unmatched quotes/operators
    results = engine.search_memories('"unclosed quote', PROJECT, None, 10)
    assert results == []


def test_get_related_entities_no_entity_filter(engine):
    """get_related_entities(entity_name=None) returns all entities in the project."""
    from graphbase_memories.graph.engine import MemoryNode
    node = MemoryNode(
        id="m-all-1", project=PROJECT, type="decision",
        title="T", content="C", tags=[],
        created_at="2026-04-04T00:00:00", updated_at="2026-04-04T00:00:00",
        valid_until=None, is_deleted=False,
    )
    engine.store_memory_with_entities(node, ["redis", "kafka"])
    entities = engine.get_related_entities(PROJECT, entity_name=None)
    names = {e.name for e in entities}
    assert "redis" in names
    assert "kafka" in names
