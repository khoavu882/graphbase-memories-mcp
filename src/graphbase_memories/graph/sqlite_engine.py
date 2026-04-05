"""
SQLiteEngine — v1 backend for graphbase-memories.

Fixes applied:
  B1: relationships table has from_type/to_type TEXT columns; no FK constraints.
      Entity→Entity edges are storable alongside Memory→Memory edges.
  B3: PRAGMA user_version tracks schema version; _run_migrations() handles upgrades.
  R5: RotatingFileHandler writes structured JSON to ~/.graphbase/<project>/graphbase.log
  R7: PRAGMA journal_mode=WAL + busy_timeout=5000ms set on every connection open.
  R8: store_memory_with_entities() is the single high-level write entry point.

Storage location: ~/.graphbase/<project>/memories.db  (override via GRAPHBASE_DATA_DIR)
"""

from __future__ import annotations

import contextlib
import json
import logging
import logging.handlers
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from graphbase_memories.config import Config
from graphbase_memories._utils import _now
from graphbase_memories.graph.engine import (
    VALID_EDGE_TYPES,
    VALID_ENTITY_TYPES,
    VALID_MEMORY_TYPES,
    BlastRadiusResult,
    Edge,
    EntityNode,
    GraphData,
    GraphEngine,
    MemoryNode,
)

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

SCHEMA_VERSION: int = 3

# Valid edge types for entity→entity relationships (subset of VALID_EDGE_TYPES)
_ENTITY_EDGE_TYPES: frozenset[str] = frozenset({"DEPENDS_ON", "IMPLEMENTS"})

# ---------------------------------------------------------------------------
# Schema DDL (v0 → v1)
# ---------------------------------------------------------------------------

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    type        TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    valid_until TEXT,
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    is_expired  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS entities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    project     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    UNIQUE (name, type, project)
);

-- [B1 FIX] No FK constraints. from_type/to_type discriminators allow
-- Memory→Memory, Entity→Entity, and Memory→Entity edges in one table.
CREATE TABLE IF NOT EXISTS relationships (
    id          TEXT PRIMARY KEY,
    from_id     TEXT NOT NULL,
    from_type   TEXT NOT NULL,
    to_id       TEXT NOT NULL,
    to_type     TEXT NOT NULL,
    type        TEXT NOT NULL,
    properties  TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_entities (
    memory_id   TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    PRIMARY KEY (memory_id, entity_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    id          UNINDEXED,
    title,
    content,
    tags,
    content     = 'memories',
    content_rowid = 'rowid'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, id, title, content, tags)
    VALUES (new.rowid, new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, id, title, content, tags)
    VALUES ('delete', old.rowid, old.id, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, id, title, content, tags)
    VALUES ('delete', old.rowid, old.id, old.title, old.content, old.tags);
    INSERT INTO memories_fts(rowid, id, title, content, tags)
    VALUES (new.rowid, new.id, new.title, new.content, new.tags);
END;

CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project, type, is_deleted);
CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories(updated_at);
CREATE INDEX IF NOT EXISTS idx_entities_project ON entities(project, type);
CREATE INDEX IF NOT EXISTS idx_rel_from ON relationships(from_id, from_type);
CREATE INDEX IF NOT EXISTS idx_rel_to   ON relationships(to_id, to_type);
"""

# ---------------------------------------------------------------------------
# Schema DDL (v1 → v2)
# ---------------------------------------------------------------------------

_SCHEMA_V2 = """
ALTER TABLE entities ADD COLUMN updated_at TEXT;

UPDATE entities SET updated_at = created_at WHERE updated_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_rel_entity_unique
    ON relationships(from_id, to_id, type)
    WHERE from_type = 'entity' AND to_type = 'entity';
"""

# ---------------------------------------------------------------------------
# Schema DDL (v2 → v3)
# ---------------------------------------------------------------------------

_SCHEMA_V3 = """
CREATE INDEX IF NOT EXISTS idx_me_entity
    ON memory_entities(entity_id);

CREATE INDEX IF NOT EXISTS idx_memories_stale
    ON memories(project, is_deleted, updated_at);

CREATE INDEX IF NOT EXISTS idx_rel_lookup
    ON relationships(from_id, to_id, type);
"""


# ---------------------------------------------------------------------------
# Structured logger (R5)
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts":    self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "op":    record.getMessage(),
        })


def _build_logger(log_path: Path | str, level: str) -> logging.Logger:
    logger = logging.getLogger(f"graphbase.{log_path}")
    if logger.handlers:
        return logger
    handler = logging.handlers.RotatingFileHandler(
        str(log_path), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.WARNING))
    logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Row → dataclass helpers
# ---------------------------------------------------------------------------

def _row_to_memory(row: sqlite3.Row) -> MemoryNode:
    return MemoryNode(
        id=row["id"],
        project=row["project"],
        type=row["type"],
        title=row["title"],
        content=row["content"],
        tags=json.loads(row["tags"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        valid_until=row["valid_until"],
        is_deleted=bool(row["is_deleted"]),
        is_expired=bool(row["is_expired"]),
    )


def _row_to_entity(row: sqlite3.Row) -> EntityNode:
    return EntityNode(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        project=row["project"],
        metadata=json.loads(row["metadata"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"] if "updated_at" in row.keys() else None,
    )


# ---------------------------------------------------------------------------
# SQLiteEngine
# ---------------------------------------------------------------------------

class SQLiteEngine(GraphEngine):
    """
    SQLite + FTS5 implementation of GraphEngine.

    Thread-safety: uses check_same_thread=False with WAL mode.
    WAL allows concurrent reads; writes are serialised by SQLite's busy_timeout.
    """

    def __init__(self, config: Config, project: str) -> None:
        self._config = config
        self._project = project
        self._log = _build_logger(config.log_path(project), config.log_level)
        db_path = config.db_path(project)
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._batch_mode: bool = False
        self._write_lock = threading.Lock()
        self._init_db()
        self._log.info(f"opened project={project!r} db={db_path}")

    # -----------------------------------------------------------------------
    # Initialisation and migrations (B3)
    # -----------------------------------------------------------------------

    def _init_db(self) -> None:
        # [R7] WAL mode + busy timeout — applied before any schema work
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA busy_timeout=5000")
        self._con.execute("PRAGMA foreign_keys=OFF")   # [B1] intentional

        current: int = self._con.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {current} is newer than the installed "
                f"graphbase-memories code (schema version {SCHEMA_VERSION}). "
                f"Upgrade the package or point GRAPHBASE_DATA_DIR at a fresh directory."
            )
        if current < SCHEMA_VERSION:
            self._log.info(f"migrating schema v{current} → v{SCHEMA_VERSION}")
            self._run_migrations(current)
            self._con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self._con.commit()

    def _run_migrations(self, from_version: int) -> None:
        migrations = {
            0: self._migrate_v0_to_v1,
            1: self._migrate_v1_to_v2,
            2: self._migrate_v2_to_v3,
        }
        for v in range(from_version, SCHEMA_VERSION):
            self._log.info(f"running migration v{v} → v{v+1}")
            migrations[v]()
            self._con.commit()

    def _migrate_v0_to_v1(self) -> None:
        self._con.executescript(_SCHEMA_V1)

    def _migrate_v1_to_v2(self) -> None:
        # executescript commits any open transaction; use individual execute() calls
        # so WAL mode and the current transaction are preserved.
        for stmt in _SCHEMA_V2.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._con.execute(stmt)

    def _migrate_v2_to_v3(self) -> None:
        for stmt in _SCHEMA_V3.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._con.execute(stmt)

    # -----------------------------------------------------------------------
    # Batch write helpers (Phase 2)
    # -----------------------------------------------------------------------

    def _commit_unless_batch(self) -> None:
        """Commit immediately unless a batch_write() context is active."""
        if not self._batch_mode:
            self._con.commit()

    @contextlib.contextmanager
    def batch_write(self):
        """
        Defer all _commit_unless_batch() calls within the block to a single
        commit on clean exit. On exception: rollback and re-raise.

        Thread-safety: acquires _write_lock for the duration of the block.
        Do not call batch_write() from within another batch_write() block
        on the same engine instance — _write_lock is non-reentrant.

        Used by store_session_batch to collapse ~22 commits → 9 per session.
        Not used by individual MCP tools (they retain per-call commit semantics).
        """
        with self._write_lock:
            self._batch_mode = True
            try:
                yield
                self._batch_mode = False
                self._con.commit()
            except Exception:
                self._batch_mode = False
                self._con.rollback()
                raise

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    def schema_version(self) -> int:
        return self._con.execute("PRAGMA user_version").fetchone()[0]

    def journal_mode(self) -> str:
        return self._con.execute("PRAGMA journal_mode").fetchone()[0]

    # -----------------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------------

    def store_memory_with_entities(
        self,
        memory: MemoryNode,
        entity_names: list[str],
        entity_type: str = "concept",
    ) -> MemoryNode:
        """[R8] Atomic: store memory + upsert entities + link."""
        if memory.type not in VALID_MEMORY_TYPES:
            raise ValueError(f"Invalid memory type {memory.type!r}. "
                             f"Valid: {sorted(VALID_MEMORY_TYPES)}")
        t0 = datetime.now(timezone.utc)
        try:
            self._con.execute(
                """INSERT INTO memories
                   (id, project, type, title, content, tags,
                    created_at, updated_at, valid_until, is_deleted, is_expired)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    memory.id, memory.project, memory.type,
                    memory.title, memory.content,
                    json.dumps(memory.tags),
                    memory.created_at, memory.updated_at,
                    memory.valid_until,
                    int(memory.is_deleted), int(memory.is_expired),
                ),
            )
            for name in entity_names:
                entity_id = self._upsert_entity(name, entity_type, memory.project)
                self._con.execute(
                    "INSERT OR IGNORE INTO memory_entities (memory_id, entity_id) VALUES (?,?)",
                    (memory.id, entity_id),
                )
            self._commit_unless_batch()
            elapsed = (datetime.now(timezone.utc) - t0).total_seconds() * 1000
            self._log.info(
                f"store_memory id={memory.id!r} project={memory.project!r} "
                f"entities={entity_names} duration_ms={elapsed:.1f}"
            )
            return memory
        except Exception as exc:
            self._con.rollback()
            self._log.error(f"store_memory FAILED id={memory.id!r} err={exc}")
            raise

    def store_edge(self, edge: Edge) -> Edge:
        if edge.type not in VALID_EDGE_TYPES:
            raise ValueError(f"Invalid edge type {edge.type!r}. "
                             f"Valid: {sorted(VALID_EDGE_TYPES)}")
        try:
            self._con.execute(
                """INSERT INTO relationships
                   (id, from_id, from_type, to_id, to_type, type, properties, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    edge.id, edge.from_id, edge.from_type,
                    edge.to_id, edge.to_type, edge.type,
                    json.dumps(edge.properties), edge.created_at,
                ),
            )
            self._commit_unless_batch()
            self._log.info(
                f"store_edge {edge.from_type}:{edge.from_id} "
                f"--{edge.type}--> {edge.to_type}:{edge.to_id}"
            )
            return edge
        except Exception as exc:
            self._con.rollback()
            self._log.error(f"store_edge FAILED id={edge.id!r} err={exc}")
            raise

    def soft_delete(self, memory_id: str) -> bool:
        cur = self._con.execute(
            "UPDATE memories SET is_deleted=1, updated_at=? WHERE id=?",
            (_now(), memory_id),
        )
        self._commit_unless_batch()
        found = cur.rowcount > 0
        self._log.info(f"soft_delete id={memory_id!r} found={found}")
        return found

    def flag_expired(self, memory_id: str) -> bool:
        cur = self._con.execute(
            "UPDATE memories SET is_expired=1, updated_at=? WHERE id=? AND is_deleted=0",
            (_now(), memory_id),
        )
        self._commit_unless_batch()
        return cur.rowcount > 0

    def purge_expired(self, project: str, older_than_days: int) -> int:
        """[Q4] Permanent DELETE of is_expired=1 memories older than N days."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        cur = self._con.execute(
            """DELETE FROM memories
               WHERE project=? AND is_expired=1 AND updated_at < ?""",
            (project, cutoff),
        )
        self._commit_unless_batch()
        count = cur.rowcount
        self._log.info(
            f"purge_expired project={project!r} older_than={older_than_days}d purged={count}"
        )
        return count

    def upsert_entity(
        self,
        name: str,
        type: str,
        project: str,
        metadata: dict[str, Any],
    ) -> EntityNode:
        """
        Create or update entity by (name, type, project).
        Full metadata replacement — not partial merge. Sets updated_at = now().

        Raises ValueError if type not in VALID_ENTITY_TYPES.
        """
        if type not in VALID_ENTITY_TYPES:
            raise ValueError(
                f"Invalid entity type {type!r}. "
                f"Must be one of: {sorted(VALID_ENTITY_TYPES)}"
            )
        now = _now()
        entity_id = str(uuid4())
        self._con.execute(
            """INSERT INTO entities (id, name, type, project, metadata, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(name, type, project)
               DO UPDATE SET metadata=excluded.metadata, updated_at=excluded.updated_at""",
            (entity_id, name, type, project, json.dumps(metadata), now, now),
        )
        self._commit_unless_batch()
        row = self._con.execute(
            "SELECT * FROM entities WHERE name=? AND type=? AND project=?",
            (name, type, project),
        ).fetchone()
        return _row_to_entity(row)

    def link_entities(
        self,
        from_name: str,
        from_type: str,
        to_name: str,
        to_type: str,
        project: str,
        edge_type: str,
        properties: dict[str, Any],
    ) -> Edge:
        """
        Create a directed entity→entity edge. Idempotent via partial UNIQUE index.

        Raises ValueError if either entity missing or edge_type invalid.
        """
        if edge_type not in _ENTITY_EDGE_TYPES:
            raise ValueError(
                f"Invalid entity edge type {edge_type!r}. "
                f"Must be one of: {sorted(_ENTITY_EDGE_TYPES)}"
            )
        from_ent = self.get_entity(from_name, from_type, project)
        if from_ent is None:
            raise ValueError(
                f"Entity not found: name={from_name!r} type={from_type!r} project={project!r}"
            )
        to_ent = self.get_entity(to_name, to_type, project)
        if to_ent is None:
            raise ValueError(
                f"Entity not found: name={to_name!r} type={to_type!r} project={project!r}"
            )
        return self.link_entities_by_id(
            from_id=from_ent.id,
            from_type="entity",
            to_id=to_ent.id,
            to_type="entity",
            project=project,
            edge_type=edge_type,
            properties=properties,
        )

    def link_entities_by_id(
        self,
        from_id: str,
        from_type: str,
        to_id: str,
        to_type: str,
        project: str,
        edge_type: str,
        properties: dict[str, Any],
    ) -> Edge:
        if edge_type not in _ENTITY_EDGE_TYPES:
            raise ValueError(
                f"Invalid entity edge type {edge_type!r}. "
                f"Must be one of: {sorted(_ENTITY_EDGE_TYPES)}"
            )
        if from_type != "entity" or to_type != "entity":
            raise ValueError(
                "link_entities_by_id requires discriminator types "
                "'entity' for both endpoints"
            )
        edge_id = str(uuid4())
        now = _now()
        cur = self._con.execute(
            """INSERT OR IGNORE INTO relationships
               (id, from_id, from_type, to_id, to_type, type, properties, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                edge_id,
                from_id,
                from_type,
                to_id,
                to_type,
                edge_type,
                json.dumps(properties),
                now,
            ),
        )
        self._commit_unless_batch()
        if cur.rowcount == 1:
            return Edge(
                id=edge_id,
                from_id=from_id,
                from_type=from_type,
                to_id=to_id,
                to_type=to_type,
                type=edge_type,
                properties=properties,
                created_at=now,
            )
        row = self._con.execute(
            """SELECT * FROM relationships
               WHERE from_id = ? AND to_id = ? AND type = ?
                 AND from_type = ? AND to_type = ?""",
            (from_id, to_id, edge_type, from_type, to_type),
        ).fetchone()
        return Edge(
            id=row["id"],
            from_id=row["from_id"],
            from_type=row["from_type"],
            to_id=row["to_id"],
            to_type=row["to_type"],
            type=row["type"],
            properties=json.loads(row["properties"]),
            created_at=row["created_at"],
        )

    def unlink_entities(
        self,
        from_name: str,
        from_type: str,
        to_name: str,
        to_type: str,
        project: str,
        edge_type: str,
    ) -> bool:
        """
        Hard-delete the entity→entity edge. Returns True if deleted, False if not found.
        """
        from_ent = self.get_entity(from_name, from_type, project)
        to_ent = self.get_entity(to_name, to_type, project)
        if from_ent is None or to_ent is None:
            return False
        cur = self._con.execute(
            """DELETE FROM relationships
               WHERE from_id=? AND to_id=? AND type=?
               AND from_type='entity' AND to_type='entity'""",
            (from_ent.id, to_ent.id, edge_type),
        )
        self._commit_unless_batch()
        return cur.rowcount > 0

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    def get_memory(
        self, memory_id: str, include_deleted: bool = False
    ) -> MemoryNode | None:
        sql = "SELECT * FROM memories WHERE id=?"
        params: list[Any] = [memory_id]
        if not include_deleted:
            sql += " AND is_deleted=0"
        row = self._con.execute(sql, params).fetchone()
        return _row_to_memory(row) if row else None

    def list_memories(
        self,
        project: str,
        type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[MemoryNode]:
        sql = "SELECT * FROM memories WHERE project=?"
        params: list[Any] = [project]
        if not include_deleted:
            sql += " AND is_deleted=0"
        if type is not None:
            sql += " AND type=?"
            params.append(type)
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = self._con.execute(sql, params).fetchall()
        return [_row_to_memory(r) for r in rows]

    def search_memories(
        self,
        query: str,
        project: str | None = None,
        type: str | None = None,
        limit: int = 10,
    ) -> list[tuple[MemoryNode, float]]:
        """
        FTS5 BM25 search. rank is negative (lower = better); we negate it so
        higher score = better match, consistent with callers' expectations.
        """
        sql = """
            SELECT m.*, (-f.rank) AS score
            FROM memories_fts f
            JOIN memories m ON m.id = f.id
            WHERE memories_fts MATCH ?
              AND m.is_deleted = 0
        """
        params: list[Any] = [query]
        if project is not None:
            sql += " AND m.project = ?"
            params.append(project)
        if type is not None:
            sql += " AND m.type = ?"
            params.append(type)
        sql += " ORDER BY f.rank LIMIT ?"
        params.append(limit)
        try:
            rows = self._con.execute(sql, params).fetchall()
            return [(_row_to_memory(r), float(r["score"])) for r in rows]
        except sqlite3.OperationalError:
            # FTS5 MATCH raises OperationalError for invalid query syntax
            return []

    def get_memories_for_entity(
        self, entity_name: str, project: str
    ) -> list[MemoryNode]:
        rows = self._con.execute(
            """SELECT DISTINCT m.*
               FROM memories m
               JOIN memory_entities me ON m.id = me.memory_id
               JOIN entities e ON e.id = me.entity_id
               WHERE e.name=? AND e.project=? AND m.is_deleted=0
               ORDER BY m.updated_at DESC""",
            (entity_name, project),
        ).fetchall()
        return [_row_to_memory(r) for r in rows]

    def get_entities_for_memory(self, memory_id: str) -> list[EntityNode]:
        rows = self._con.execute(
            """SELECT e.*
               FROM entities e
               JOIN memory_entities me ON e.id = me.entity_id
               WHERE me.memory_id = ?
               ORDER BY e.name""",
            (memory_id,),
        ).fetchall()
        return [_row_to_entity(r) for r in rows]

    def get_edges_for_memory(self, memory_id: str) -> list[Edge]:
        rows = self._con.execute(
            """SELECT * FROM relationships
               WHERE from_id = ? AND from_type = 'memory'
               ORDER BY created_at""",
            (memory_id,),
        ).fetchall()
        return [
            Edge(
                id=r["id"],
                from_id=r["from_id"],
                from_type=r["from_type"],
                to_id=r["to_id"],
                to_type=r["to_type"],
                type=r["type"],
                properties=json.loads(r["properties"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def find_edge(self, from_id: str, to_id: str, edge_type: str) -> Edge | None:
        row = self._con.execute(
            """SELECT *
               FROM relationships
               WHERE from_id = ? AND to_id = ? AND type = ?
               LIMIT 1""",
            (from_id, to_id, edge_type),
        ).fetchone()
        if row is None:
            return None
        return Edge(
            id=row["id"],
            from_id=row["from_id"],
            from_type=row["from_type"],
            to_id=row["to_id"],
            to_type=row["to_type"],
            type=row["type"],
            properties=json.loads(row["properties"]),
            created_at=row["created_at"],
        )

    def get_related_entities(
        self,
        project: str,
        entity_name: str | None = None,
    ) -> list[EntityNode]:
        if entity_name is None:
            rows = self._con.execute(
                "SELECT * FROM entities WHERE project=? ORDER BY name",
                (project,),
            ).fetchall()
        else:
            rows = self._con.execute(
                """SELECT DISTINCT e2.*
                   FROM entities e1
                   JOIN memory_entities me1 ON e1.id = me1.entity_id
                   JOIN memory_entities me2 ON me1.memory_id = me2.memory_id
                   JOIN entities e2 ON e2.id = me2.entity_id
                   WHERE e1.name=? AND e1.project=? AND e2.id != e1.id
                   ORDER BY e2.name""",
                (entity_name, project),
            ).fetchall()
        return [_row_to_entity(r) for r in rows]

    def get_entity(
        self,
        name: str,
        type: str,
        project: str,
    ) -> EntityNode | None:
        """Direct entity lookup by (name, type, project). Returns None if not found."""
        row = self._con.execute(
            "SELECT * FROM entities WHERE name=? AND type=? AND project=? LIMIT 1",
            (name, type, project),
        ).fetchone()
        return _row_to_entity(row) if row else None

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------

    def get_blast_radius(
        self,
        entity_name: str,
        project: str,
        depth: int = 2,
    ) -> BlastRadiusResult:
        """
        Depth-aware blast radius. Current implementation: depth is used to
        find co-occurring entities (entities sharing memories with entity_name).
        Neo4jEngine v2 will use Cypher for true N-hop graph traversal.
        """
        entity_row = self._con.execute(
            "SELECT * FROM entities WHERE name=? AND project=?",
            (entity_name, project),
        ).fetchone()

        if entity_row is None:
            return BlastRadiusResult(
                entity_name=entity_name, project=project, depth=depth,
                memories=[], related_entities=[], total_references=0,
            )

        entity_id: str = entity_row["id"]

        # Memories that directly reference this entity
        memory_rows = self._con.execute(
            """SELECT DISTINCT m.*
               FROM memories m
               JOIN memory_entities me ON m.id = me.memory_id
               WHERE me.entity_id = ? AND m.is_deleted = 0
               ORDER BY m.updated_at DESC""",
            (entity_id,),
        ).fetchall()
        memories = [_row_to_memory(r) for r in memory_rows]

        # Entities co-occurring in those memories (depth=1 pass)
        related_entity_rows = self._con.execute(
            """SELECT DISTINCT e.*
               FROM entities e
               JOIN memory_entities me1 ON e.id = me1.entity_id
               JOIN memory_entities me2 ON me1.memory_id = me2.memory_id
               WHERE me2.entity_id = ? AND e.id != ?
               ORDER BY e.name""",
            (entity_id, entity_id),
        ).fetchall()
        related_entities = [_row_to_entity(r) for r in related_entity_rows]

        return BlastRadiusResult(
            entity_name=entity_name,
            project=project,
            depth=depth,
            memories=memories,
            related_entities=related_entities,
            total_references=len(memories),
        )

    def get_stale_memories(
        self, project: str, age_days: int = 30
    ) -> list[MemoryNode]:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=age_days)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        rows = self._con.execute(
            """SELECT * FROM memories
               WHERE project=? AND is_deleted=0 AND updated_at < ?
               ORDER BY updated_at ASC""",
            (project, cutoff),
        ).fetchall()
        return [_row_to_memory(r) for r in rows]

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _upsert_entity(
        self, name: str, entity_type: str, project: str
    ) -> str:
        """Insert entity if not exists; return its id."""
        existing = self._con.execute(
            "SELECT id FROM entities WHERE name=? AND type=? AND project=?",
            (name, entity_type, project),
        ).fetchone()
        if existing:
            return existing["id"]
        entity_id = str(uuid4())
        now = _now()
        self._con.execute(
            """INSERT OR IGNORE INTO entities
               (id, name, type, project, metadata, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (entity_id, name, entity_type, project, "{}", now, now),
        )
        return entity_id

    # -----------------------------------------------------------------------
    # Graph snapshot (P2-B)
    # -----------------------------------------------------------------------

    def get_graph_data(
        self,
        project: str,
        limit: int = 200,
    ) -> GraphData:
        """
        Return a bulk graph snapshot for CTL Graph View and graph_view tool.

        [Fix C-1] Edges are fetched via a temp table join instead of
        IN (?,?,…) to avoid SQLite's SQLITE_MAX_VARIABLE_NUMBER=999 limit
        when the memory set is large.
        """
        total_memories: int = self._con.execute(
            "SELECT COUNT(*) FROM memories WHERE project=? AND is_deleted=0",
            (project,),
        ).fetchone()[0]

        memory_rows = self._con.execute(
            """SELECT * FROM memories
               WHERE project=? AND is_deleted=0
               ORDER BY updated_at DESC LIMIT ?""",
            (project, limit),
        ).fetchall()
        memories = [_row_to_memory(r) for r in memory_rows]

        if not memories:
            return GraphData(
                memories=[],
                entities=[],
                edges=[],
                total_memories=total_memories,
                generated_at=_now(),
            )

        memory_ids = [(m.id,) for m in memories]

        # [Fix C-1] Use a temp table to avoid SQLITE_MAX_VARIABLE_NUMBER=999
        self._con.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _gd_ids (id TEXT PRIMARY KEY)"
        )
        self._con.execute("DELETE FROM _gd_ids")
        self._con.executemany("INSERT INTO _gd_ids (id) VALUES (?)", memory_ids)

        entity_rows = self._con.execute(
            """SELECT DISTINCT e.*
               FROM entities e
               JOIN memory_entities me ON e.id = me.entity_id
               JOIN _gd_ids gi ON gi.id = me.memory_id
               WHERE e.project=?
               ORDER BY e.name""",
            (project,),
        ).fetchall()
        entities = [_row_to_entity(r) for r in entity_rows]

        # [P0-1] Pre-fetch all memory→entity links for this snapshot in one query.
        # graph_view uses this to build its entity_filter and link list without N+1 calls.
        me_rows = self._con.execute(
            """SELECT me.memory_id, me.entity_id
               FROM memory_entities me
               JOIN _gd_ids gi ON gi.id = me.memory_id""",
        ).fetchall()
        memory_entity_links: list[tuple[str, str]] = [
            (r["memory_id"], r["entity_id"]) for r in me_rows
        ]

        edge_rows = self._con.execute(
            """SELECT r.*
               FROM relationships r
               JOIN _gd_ids gf ON gf.id = r.from_id
               JOIN _gd_ids gt ON gt.id = r.to_id
               ORDER BY r.created_at""",
        ).fetchall()
        edges = [
            Edge(
                id=r["id"],
                from_id=r["from_id"],
                from_type=r["from_type"],
                to_id=r["to_id"],
                to_type=r["to_type"],
                type=r["type"],
                properties=json.loads(r["properties"]),
                created_at=r["created_at"],
            )
            for r in edge_rows
        ]

        self._con.execute("DROP TABLE IF EXISTS _gd_ids")

        # [P0-2] Also fetch entity→entity edges (DEPENDS_ON, IMPLEMENTS).
        # These have entity UUIDs on both ends — never in _gd_ids — so they
        # were silently excluded before this fix.
        entity_edge_rows = self._con.execute(
            """SELECT r.*
               FROM relationships r
               JOIN entities ef ON ef.id = r.from_id AND r.from_type = 'entity'
               JOIN entities et ON et.id = r.to_id   AND r.to_type  = 'entity'
               WHERE ef.project = ? AND et.project = ?
               ORDER BY r.created_at""",
            (project, project),
        ).fetchall()
        edges += [
            Edge(
                id=r["id"],
                from_id=r["from_id"],
                from_type=r["from_type"],
                to_id=r["to_id"],
                to_type=r["to_type"],
                type=r["type"],
                properties=json.loads(r["properties"]),
                created_at=r["created_at"],
            )
            for r in entity_edge_rows
        ]

        return GraphData(
            memories=memories,
            entities=entities,
            edges=edges,
            total_memories=total_memories,
            generated_at=_now(),
            memory_entity_links=memory_entity_links,
        )

    # -----------------------------------------------------------------------
    # Test helper
    # -----------------------------------------------------------------------

    def _backdate(self, memory_id: str, days: int) -> None:
        """Move updated_at back by `days` days. For tests only."""
        backdated = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%S")
        self._con.execute(
            "UPDATE memories SET updated_at=? WHERE id=?",
            (backdated, memory_id),
        )
        self._con.commit()

    def close(self) -> None:  # pragma: no cover
        self._con.close()

    def __del__(self) -> None:  # pragma: no cover
        with contextlib.suppress(Exception):
            self._con.close()
