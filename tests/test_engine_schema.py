"""
Schema-level tests: B1 (entity-entity edges), B3 (migration idempotent), R7 (WAL),
and v2-specific: updated_at column, partial UNIQUE index scope, upsert stability.
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
    """[B3] schema_version() must return 3 after v3 migration."""
    assert engine.schema_version() == 3


def test_schema_migration_idempotent(tmp_path):
    """[B3] Second initialization of the same DB must not raise."""
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine

    cfg = Config(backend="sqlite", data_dir=tmp_path, log_level="WARNING", log_to_file=False)
    SQLiteEngine(cfg, "idempotent")
    SQLiteEngine(cfg, "idempotent")   # must not raise


def test_schema_v3_indexes_present(engine):
    """[v3] Fresh DB must include the new lookup indexes."""
    me_indexes = {row[1] for row in engine._con.execute("PRAGMA index_list(memory_entities)")}
    memories_indexes = {row[1] for row in engine._con.execute("PRAGMA index_list(memories)")}
    rel_indexes = {row[1] for row in engine._con.execute("PRAGMA index_list(relationships)")}
    assert "idx_me_entity" in me_indexes
    assert "idx_memories_stale" in memories_indexes
    assert "idx_rel_lookup" in rel_indexes


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


# ---------------------------------------------------------------------------
# v2 schema tests: updated_at column, partial UNIQUE index
# ---------------------------------------------------------------------------


def test_v2_migration_populates_updated_at_for_existing_entities(tmp_path):
    """[v2] v1→v2 migration must backfill updated_at = created_at for existing rows."""
    import sqlite3
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine, _SCHEMA_V1

    db_dir = tmp_path / "v1_db"
    db_dir.mkdir()
    db_path = db_dir / "memories.db"

    # Create a v1 DB manually and insert an entity without updated_at
    con = sqlite3.connect(str(db_path))
    con.executescript(_SCHEMA_V1)
    con.execute(
        "INSERT INTO entities (id, name, type, project, metadata, created_at) "
        "VALUES ('eid-1','legacy-svc','service','proj','{}','2026-01-01T00:00:00')"
    )
    con.execute("PRAGMA user_version=1")
    con.commit()
    con.close()

    # Open with v2 engine — triggers migration
    cfg = Config(backend="sqlite", data_dir=tmp_path, log_level="WARNING", log_to_file=False)
    eng = SQLiteEngine(cfg, "v1_db")

    entity = eng.get_entity("legacy-svc", "service", "proj")
    assert entity is not None
    assert entity.updated_at is not None
    assert entity.updated_at == "2026-01-01T00:00:00"   # backfilled from created_at


def test_v3_migration_from_v2_adds_indexes(tmp_path):
    """[v3] v2→v3 migration must add the new indexes sequentially."""
    import sqlite3
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine, _SCHEMA_V1, _SCHEMA_V2

    db_dir = tmp_path / "v2_db"
    db_dir.mkdir()
    db_path = db_dir / "memories.db"

    con = sqlite3.connect(str(db_path))
    con.executescript(_SCHEMA_V1)
    for stmt in _SCHEMA_V2.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            con.execute(stmt)
    con.execute("PRAGMA user_version=2")
    con.commit()
    con.close()

    cfg = Config(backend="sqlite", data_dir=tmp_path, log_level="WARNING", log_to_file=False)
    eng = SQLiteEngine(cfg, "v2_db")

    assert eng.schema_version() == 3
    me_indexes = {row[1] for row in eng._con.execute("PRAGMA index_list(memory_entities)")}
    memories_indexes = {row[1] for row in eng._con.execute("PRAGMA index_list(memories)")}
    rel_indexes = {row[1] for row in eng._con.execute("PRAGMA index_list(relationships)")}
    assert "idx_me_entity" in me_indexes
    assert "idx_memories_stale" in memories_indexes
    assert "idx_rel_lookup" in rel_indexes


def test_v2_upsert_entity_sets_updated_at(engine):
    """[v2] upsert_entity must populate updated_at on the returned EntityNode."""
    e = engine.upsert_entity("new-svc", "service", PROJECT, {"owner": "team-a"})
    assert e.updated_at is not None


def test_v2_upsert_entity_created_at_stable_on_update(engine):
    """[v2] Second upsert must not change created_at (only updated_at and metadata change)."""
    e1 = engine.upsert_entity("stable-svc", "service", PROJECT, {"v": "1"})
    e2 = engine.upsert_entity("stable-svc", "service", PROJECT, {"v": "2"})
    assert e1.id == e2.id
    assert e1.created_at == e2.created_at   # immutable
    assert e2.metadata["v"] == "2"          # metadata replaced


def test_v2_get_entity_updated_at_populated(engine):
    """[v2] get_entity returns EntityNode with updated_at field set after upsert."""
    engine.upsert_entity("queried-svc", "service", PROJECT, {})
    e = engine.get_entity("queried-svc", "service", PROJECT)
    assert e is not None
    assert e.updated_at is not None


def test_v2_partial_unique_entity_edge_idempotent(engine):
    """[v2] Storing the same entity→entity edge twice must not create a duplicate row."""
    engine.upsert_entity("svc-p", "service", PROJECT, {})
    engine.upsert_entity("svc-q", "service", PROJECT, {})
    edge1 = engine.link_entities("svc-p", "service", "svc-q", "service", PROJECT,
                                  "DEPENDS_ON", {})
    edge2 = engine.link_entities("svc-p", "service", "svc-q", "service", PROJECT,
                                  "DEPENDS_ON", {})
    assert edge1.id == edge2.id   # same edge returned, not a second insert


def test_v2_partial_unique_does_not_restrict_memory_memory_edges(engine):
    """[v2] Partial UNIQUE index must not prevent duplicate memory→memory edges."""
    # Two SUPERSEDES edges with same logical endpoints but different IDs must both store.
    edge1 = engine.store_edge(Edge(
        id="mm-dup-1", from_id="mem-a", from_type="memory",
        to_id="mem-b", to_type="memory", type="SUPERSEDES",
        properties={}, created_at="2026-04-04T00:00:00",
    ))
    edge2 = engine.store_edge(Edge(
        id="mm-dup-2", from_id="mem-a", from_type="memory",
        to_id="mem-b", to_type="memory", type="SUPERSEDES",
        properties={}, created_at="2026-04-04T00:00:01",
    ))
    assert edge1.id != edge2.id   # both rows exist — no unique violation


def test_v2_link_entities_invalid_edge_type_raises(engine):
    """[v2] link_entities must reject edge types outside {DEPENDS_ON, IMPLEMENTS}."""
    engine.upsert_entity("a", "service", PROJECT, {})
    engine.upsert_entity("b", "service", PROJECT, {})
    with pytest.raises(ValueError, match="Invalid entity edge type"):
        engine.link_entities("a", "service", "b", "service", PROJECT, "SUPERSEDES", {})


def test_v2_link_entities_missing_entity_raises(engine):
    """[v2] link_entities raises ValueError when either entity doesn't exist."""
    engine.upsert_entity("real", "service", PROJECT, {})
    with pytest.raises(ValueError, match="Entity not found"):
        engine.link_entities("real", "service", "ghost", "service", PROJECT, "DEPENDS_ON", {})


def test_find_edge_absent_returns_none(engine):
    """[v3] find_edge returns None when no matching relationship exists."""
    assert engine.find_edge("missing-from", "missing-to", "RELATES_TO") is None


def test_find_edge_returns_existing_relationship(engine):
    """[v3] find_edge returns the stored relationship without a fan-out scan."""
    edge = Edge(
        id="find-edge-1",
        from_id="mem-a",
        from_type="memory",
        to_id="mem-b",
        to_type="memory",
        type="RELATES_TO",
        properties={},
        created_at="2026-04-04T00:00:00",
    )
    engine.store_edge(edge)
    found = engine.find_edge("mem-a", "mem-b", "RELATES_TO")
    assert found is not None
    assert found.id == edge.id


def test_link_entities_by_id_idempotent(engine):
    """[v3] link_entities_by_id returns the existing entity edge on duplicate calls."""
    from_ent = engine.upsert_entity("svc-id-a", "service", PROJECT, {})
    to_ent = engine.upsert_entity("svc-id-b", "service", PROJECT, {})
    edge1 = engine.link_entities_by_id(
        from_id=from_ent.id,
        from_type="entity",
        to_id=to_ent.id,
        to_type="entity",
        project=PROJECT,
        edge_type="DEPENDS_ON",
        properties={},
    )
    edge2 = engine.link_entities_by_id(
        from_id=from_ent.id,
        from_type="entity",
        to_id=to_ent.id,
        to_type="entity",
        project=PROJECT,
        edge_type="DEPENDS_ON",
        properties={},
    )
    assert edge1.id == edge2.id
