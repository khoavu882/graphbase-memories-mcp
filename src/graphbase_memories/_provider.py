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

import importlib.metadata
import re
import threading

from graphbase_memories.config import Config
from graphbase_memories.graph.engine import GraphEngine

_VALID_PROJECT_SLUG = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')

_config: Config = Config()
_engines: dict[str, GraphEngine] = {}
_engines_lock = threading.Lock()
_discovered: bool = False   # sentinel: _discover_all_projects() has run once
_discover_lock = threading.Lock()


def _load_backend_class(name: str) -> type[GraphEngine]:
    """
    Load a backend class by name via entry_points.

    Built-in backends (sqlite, neo4j) are registered in pyproject.toml under
    [project.entry-points."graphbase_memories.backends"].
    Community backends can register the same group in their own package.
    """
    eps = importlib.metadata.entry_points(group="graphbase_memories.backends")
    for ep in eps:
        if ep.name == name:
            cls = ep.load()
            if not (isinstance(cls, type) and issubclass(cls, GraphEngine)):
                raise TypeError(
                    f"Backend entry point {ep.value!r} must subclass GraphEngine"
                )
            return cls
    available = [e.name for e in eps]
    raise ValueError(
        f"Unknown GRAPHBASE_BACKEND={name!r}. "
        f"Available backends: {available or ['none registered — re-install package']}"
    )


def get_engine(project: str) -> GraphEngine:
    """
    Return the engine for `project`, creating it on first access.

    Backend is selected by GRAPHBASE_BACKEND env var (default: sqlite).
    Thread-safe: double-checked locking prevents duplicate instantiation.
    Backend class is resolved via entry_points for community extensibility.

    Raises ValueError for project slugs that could escape the data directory.
    """
    if not _VALID_PROJECT_SLUG.match(project):
        raise ValueError(
            f"Invalid project slug {project!r}. "
            "Must match [a-z0-9][a-z0-9_-]{{0,63}} (lowercase, no path separators)."
        )
    if project not in _engines:
        with _engines_lock:
            if project not in _engines:
                cls = _load_backend_class(_config.backend)
                _engines[project] = cls(_config, project)
    return _engines[project]


def _discover_all_projects() -> None:
    """
    Scan GRAPHBASE_DATA_DIR and load engines for all existing project DBs.

    Called once before any cross-project operation (e.g. search with project=None).
    Idempotent: the _discovered sentinel prevents repeated filesystem scans.
    Thread-safe: serialised by _discover_lock.
    """
    global _discovered
    if _discovered:
        return
    with _discover_lock:
        if _discovered:
            return
        data_dir = _config.data_dir
        if data_dir.exists():
            for subdir in data_dir.iterdir():
                if subdir.is_dir() and (subdir / "memories.db").exists():
                    project = subdir.name
                    if project not in _engines:
                        get_engine(project)
        _discovered = True


def get_all_known_projects() -> list[str]:
    """
    Return all project slugs that have an existing DB on disk.

    Triggers _discover_all_projects() on first call so cross-project
    operations see all projects, not just those loaded in the current session.
    """
    _discover_all_projects()
    return list(_engines.keys())


def list_known_project_ids() -> list[str]:
    """
    Return project directory names that contain memories.db.

    Unlike get_all_known_projects(), this does NOT load engines.
    Suitable for lightweight lifecycle resolution without side effects.
    """
    data_dir = _config.data_dir
    if not data_dir.exists():
        return []
    return [
        subdir.name
        for subdir in sorted(data_dir.iterdir())
        if subdir.is_dir() and (subdir / "memories.db").exists()
    ]


def _set_engine_for_test(project: str, engine: GraphEngine) -> None:
    """Inject a test/mock engine. Used by pytest conftest only."""
    _engines[project] = engine


def _clear_engines() -> None:
    """Reset all engines and discovery state. Used by pytest conftest between tests."""
    global _discovered
    _engines.clear()
    _discovered = False


def _set_config_for_test(config: Config) -> None:
    """Replace the provider's Config singleton. Used by pytest conftest only."""
    global _config
    _config = config