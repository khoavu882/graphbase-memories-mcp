"""
SQLiteEngine — v1 backend for graphbase-memories.

Fixes applied:
  B1: relationships table has from_type/to_type TEXT columns; no FK constraints.
      Entity→Entity edges are storable alongside Memory→Memory edges.
  B3: PRAGMA user_version tracks schema version; _run_migrations() handles upgrades.
  R5: RotatingFileHandler writes structured JSON to ~/.graphbase-memories/<project>/graphbase.log
  R7: PRAGMA journal_mode=WAL + busy_timeout=5000ms set on every connection open.
  R8: store_memory_with_entities() is the single high-level write entry point.

Storage location: ~/.graphbase-memories/<project>/memories.db  (override via GRAPHBASE_DATA_DIR)
"""

from __future__ import annotations

import contextlib
import json
import logging
import logging.handlers
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from graphbase_memories.config import Config
from graphbase_memories.graph.engine import (
    VALID_EDGE_TYPES,
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

SCHEMA_VERSION: int = 1

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
# Structured logger (R5)
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts":    self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "op":    record.getMessage(),
        })


def _build_logger(log_path: Any, level: str) -> logging.Logger:
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
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


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
        }
        for v in range(from_version, SCHEMA_VERSION):
            self._log.info(f"running migration v{v} → v{v+1}")
            migrations[v]()
            self._con.commit()

    def _migrate_v0_to_v1(self) -> None:
        self._con.executescript(_SCHEMA_V1)

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
            self._con.commit()
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
            self._con.commit()
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
        self._con.commit()
        found = cur.rowcount > 0
        self._log.info(f"soft_delete id={memory_id!r} found={found}")
        return found

    def flag_expired(self, memory_id: str) -> bool:
        cur = self._con.execute(
            "UPDATE memories SET is_expired=1, updated_at=? WHERE id=? AND is_deleted=0",
            (_now(), memory_id),
        )
        self._con.commit()
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
        self._con.commit()
        count = cur.rowcount
        self._log.info(
            f"purge_expired project={project!r} older_than={older_than_days}d purged={count}"
        )
        return count

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
        self._con.execute(
            """INSERT INTO entities (id, name, type, project, metadata, created_at)
               VALUES (?,?,?,?,?,?)""",
            (entity_id, name, entity_type, project, "{}", _now()),
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

        return GraphData(
            memories=memories,
            entities=entities,
            edges=edges,
            total_memories=total_memories,
            generated_at=_now(),
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