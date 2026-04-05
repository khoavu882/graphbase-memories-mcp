"""
pytest fixtures for Neo4j integration tests.

Skips automatically if:
  1. The neo4j driver is not installed  (ImportError)
  2. A Neo4j instance is not reachable at GRAPHBASE_NEO4J_URI

Run these tests with a live Neo4j:
    docker compose -f docker-compose.neo4j.yml up -d
    GRAPHBASE_NEO4J_PASSWORD=graphbase uv run pytest tests/neo4j/ -v
"""

from __future__ import annotations

import os
import uuid

import pytest

NEO4J_URI  = os.getenv("GRAPHBASE_NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER = os.getenv("GRAPHBASE_NEO4J_USER",     "neo4j")
NEO4J_PASS = os.getenv("GRAPHBASE_NEO4J_PASSWORD", "graphbase")

# Unique project slug per test run — prevents cross-test pollution
TEST_PROJECT = f"neo4j-test-{uuid.uuid4().hex[:8]}"


def pytest_configure(config):
    """Register the 'neo4j' marker to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line("markers", "neo4j: marks tests requiring a live Neo4j instance")


@pytest.fixture(scope="session")
def neo4j_driver():
    """
    Session-scoped driver. Skip the entire test session if Neo4j is unavailable.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError:
        pytest.skip("neo4j driver not installed — run: pip install 'graphbase-memories-mcp[neo4j]'")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS), connection_timeout=3.0)
    try:
        driver.verify_connectivity()
    except Exception as exc:
        driver.close()
        pytest.skip(f"Neo4j not reachable at {NEO4J_URI}: {exc}")
    yield driver
    driver.close()


@pytest.fixture
def engine(neo4j_driver, tmp_path):
    """
    Fresh Neo4jEngine scoped to TEST_PROJECT for this test.
    Cleans up all test nodes after each test.
    """
    from graphbase_memories.config import Config
    from graphbase_memories.graph.neo4j_engine import Neo4jEngine

    cfg = Config(
        backend="neo4j",
        data_dir=tmp_path,
        log_level="WARNING",
        neo4j_uri=NEO4J_URI,
        neo4j_user=NEO4J_USER,
        neo4j_password=NEO4J_PASS,
    )
    eng = Neo4jEngine(cfg, TEST_PROJECT)
    yield eng

    # Teardown: delete all nodes created for this test project
    with neo4j_driver.session() as s:
        s.execute_write(lambda tx: tx.run(
            "MATCH (n {project: $p}) DETACH DELETE n",
            p=TEST_PROJECT,
        ))
    eng.close()
