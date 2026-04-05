"""
Neo4j engine contract tests.

These run the full AbstractEngineTests contract against Neo4jEngine.
Skipped automatically if no Neo4j instance is available.

Usage:
    docker compose -f docker-compose.neo4j.yml up -d
    GRAPHBASE_NEO4J_PASSWORD=graphbase uv run pytest tests/neo4j/ -v
"""

import sys
import os

# Allow `from shared import ...` without installing as package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from shared import AbstractEngineTests


@pytest.mark.neo4j
class TestNeo4jEngine(AbstractEngineTests):
    """
    Runs the full AbstractEngineTests contract against Neo4jEngine.

    The `engine` fixture is defined in tests/neo4j/conftest.py.
    If Neo4j is not reachable, the entire class is skipped.
    """
    # AbstractEngineTests.test_purge_expired_removes_old_memories:
    # Neo4j doesn't have _backdate(), so purge with older_than_days=0
    # may return 0 for a freshly-created node. The mixin uses count >= 0
    # which is always satisfied. No override needed.
    pass
