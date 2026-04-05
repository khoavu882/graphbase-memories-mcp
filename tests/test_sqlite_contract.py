"""
SQLite engine contract tests — validates AbstractEngineTests against SQLiteEngine.

These run without any external services (in-memory SQLite via tmp_path).
If these pass, the mixin contract is correct for the SQLite implementation.
"""

import pytest
from shared import AbstractEngineTests

PROJECT = "contract-test"


class TestSQLiteEngineContract(AbstractEngineTests):
    """Run the full contract test suite against SQLiteEngine."""

    @pytest.fixture
    def engine(self, tmp_path):
        from graphbase_memories.config import Config
        from graphbase_memories.graph.sqlite_engine import SQLiteEngine
        from graphbase_memories._provider import _clear_engines

        _clear_engines()
        cfg = Config(
            backend="sqlite",
            data_dir=tmp_path,
            log_level="WARNING",
            log_to_file=False,
        )
        eng = SQLiteEngine(cfg, PROJECT)
        yield eng
        _clear_engines()
