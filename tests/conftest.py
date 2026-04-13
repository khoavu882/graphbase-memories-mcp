"""
Integration test fixtures — function-scoped async driver to avoid event loop scope issues.
Uses the 'neo4j' database against the running local Neo4j 5 Community container.
"""

from __future__ import annotations

import pathlib
import sys

from neo4j import AsyncGraphDatabase
import pytest_asyncio

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "graphbase"
TEST_DB = "neo4j"

TEST_PROJECT_ID = "test-project-integration"


@pytest_asyncio.fixture
async def driver():
    """Function-scoped async driver — one connection per test."""
    d = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    await d.verify_connectivity()

    # Ensure schema is applied
    from graphbase_memories.graph.driver import SCHEMA_DDL, SCHEMA_V2_DDL, split_statements

    async with d.session(database=TEST_DB) as session:
        for stmt in split_statements(SCHEMA_DDL):
            await session.run(stmt)
        for stmt in split_statements(SCHEMA_V2_DDL):
            await session.run(stmt)

    yield d
    await d.close()


@pytest_asyncio.fixture
async def fresh_project(driver):
    """Per-test fixture: wipe and re-create the test project node."""
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MATCH (n)-[:BELONGS_TO]->(p:Project {id: $pid})
            DETACH DELETE n
            """,
            pid=TEST_PROJECT_ID,
        )
        await session.run(
            "MERGE (p:Project {id: $pid}) ON CREATE SET p.name = $pid, p.created_at = datetime()",
            pid=TEST_PROJECT_ID,
        )
    yield TEST_PROJECT_ID
    # Cleanup after test: project data + any global test artifacts
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MATCH (n)-[:BELONGS_TO]->(p:Project {id: $pid})
            DETACH DELETE n
            WITH p DETACH DELETE p
            """,
            pid=TEST_PROJECT_ID,
        )
        # Remove global-scope artifacts written during this test
        await session.run(
            """
            MATCH (n:Decision)-[:BELONGS_TO]->(g:GlobalScope)
            DETACH DELETE n
            """
        )
        await session.run("MATCH (t:GovernanceToken) DETACH DELETE t")


@pytest_asyncio.fixture
async def fresh_workspace(driver, fresh_project):
    """Per-test fixture: create a Workspace node linked to the test project via MEMBER_OF."""
    ws_id = "test-workspace-graph"
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MERGE (w:Workspace {id: $wid})
            ON CREATE SET w.name = $wid, w.created_at = datetime()
            WITH w
            MATCH (p:Project {id: $pid})
            MERGE (p)-[:MEMBER_OF]->(w)
            """,
            wid=ws_id,
            pid=TEST_PROJECT_ID,
        )
    yield ws_id
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            "MATCH (w:Workspace {id: $wid}) DETACH DELETE w",
            wid=ws_id,
        )


@pytest_asyncio.fixture
async def bulk_projects(driver):
    """Per-test fixture: seed 250 Project nodes for cap testing, cleaned up by prefix."""
    prefix = "test-graph-cap-"
    count = 250
    ids = [f"{prefix}{i}" for i in range(count)]
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            UNWIND $ids AS id
            MERGE (p:Project {id: id})
            ON CREATE SET p.name = id, p.created_at = datetime()
            """,
            ids=ids,
        )
    yield ids
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            "MATCH (p:Project) WHERE p.id STARTS WITH $prefix DETACH DELETE p",
            prefix=prefix,
        )
