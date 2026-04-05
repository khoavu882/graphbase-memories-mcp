"""
Engine provider — manages one SQLiteEngine instance per project.

The tool layer calls get_engine(project) rather than constructing engines
directly. This enables:
  - Lazy initialisation (DB created only when first needed)
  - Backend selection via GRAPHBASE_BACKEND env var
  - Test injection via _set_engine_for_test()
  - Future: Neo4jEngine swap without tool-layer changes

Thread safety: _engines_lock serialises lazy initialisation so that two
concurrent requests for a new project each get the same engine object.
After the first call, _engines[project] is set and the lock is skipped
on the fast path (project already in dict).
"""

from __future__ import annotations

import threading

from graphbase_memories.config import Config
from graphbase_memories.graph.engine import GraphEngine

_config: Config = Config()
_engines: dict[str, GraphEngine] = {}
_engines_lock = threading.Lock()


def get_engine(project: str) -> GraphEngine:
    """
    Return the engine for `project`, creating it on first access.

    Backend is selected by GRAPHBASE_BACKEND env var (default: sqlite).
    Thread-safe: uses a module-level lock to prevent duplicate instantiation.
    """
    if project not in _engines:
        with _engines_lock:
            # Double-checked locking: re-test after acquiring the lock because
            # another thread may have created the engine while we waited.
            if project not in _engines:
                backend = _config.backend
                if backend == "sqlite":
                    from graphbase_memories.graph.sqlite_engine import SQLiteEngine
                    _engines[project] = SQLiteEngine(_config, project)
                elif backend == "neo4j":
                    try:
                        from graphbase_memories.graph.neo4j_engine import Neo4jEngine
                    except ImportError as exc:
                        raise ImportError(
                            "Neo4j backend requires the 'neo4j' extra: "
                            "pip install 'graphbase-memories-mcp[neo4j]'"
                        ) from exc
                    _engines[project] = Neo4jEngine(_config, project)
                else:
                    raise ValueError(
                        f"Unknown GRAPHBASE_BACKEND={backend!r}. Valid: sqlite, neo4j"
                    )
    return _engines[project]


def _set_engine_for_test(project: str, engine: GraphEngine) -> None:
    """Inject a test/mock engine. Used by pytest conftest only."""
    _engines[project] = engine


def _clear_engines() -> None:
    """Reset all engines. Used by pytest conftest between tests."""
    _engines.clear()