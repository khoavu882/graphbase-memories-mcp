"""
Integration: schema DDL is idempotent and all constraints/indexes exist.
"""

from __future__ import annotations

from conftest import TEST_DB


async def test_schema_idempotent(driver):
    """Running schema DDL twice must not raise errors."""
    from graphbase_memories.graph.driver import SCHEMA_DDL, split_statements

    async with driver.session(database=TEST_DB) as session:
        for stmt in split_statements(SCHEMA_DDL):
            await session.run(stmt)


async def test_global_scope_singleton_exists(driver):
    """GlobalScope singleton must be created by schema DDL."""
    async with driver.session(database=TEST_DB) as session:
        result = await session.run("MATCH (g:GlobalScope {id: 'global'}) RETURN g.id AS id LIMIT 1")
        record = await result.single()
    assert record is not None, "GlobalScope singleton missing"
    assert record["id"] == "global"


async def test_constraints_present(driver):
    """Key uniqueness constraints must exist."""
    async with driver.session(database=TEST_DB) as session:
        result = await session.run("SHOW CONSTRAINTS YIELD name RETURN collect(name) AS names")
        record = await result.single()
    names: list[str] = record["names"]
    expected = [
        "project_id_unique",
        "decision_id_unique",
        "session_id_unique",
        "entity_fact_id_unique",
        "governance_token_id_unique",
    ]
    for c in expected:
        assert c in names, f"Constraint '{c}' missing from Neo4j"


async def test_fulltext_indexes_present(driver):
    """Full-text indexes required for dedup candidates must exist."""
    async with driver.session(database=TEST_DB) as session:
        result = await session.run("SHOW INDEXES YIELD name, type RETURN collect(name) AS names")
        record = await result.single()
    names: list[str] = record["names"]
    for idx in ["decision_fulltext", "pattern_fulltext", "entity_fulltext"]:
        assert idx in names, f"Full-text index '{idx}' missing"
