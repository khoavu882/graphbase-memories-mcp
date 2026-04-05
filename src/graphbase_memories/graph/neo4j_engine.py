"""
Neo4jEngine — v2 backend for graphbase-memories.

Requires: pip install 'graphbase-memories-mcp[neo4j]'
          Neo4j 5.x running at GRAPHBASE_NEO4J_URI (default bolt://localhost:7687)

Quick start (Docker):
    docker compose -f docker-compose.neo4j.yml up -d
    GRAPHBASE_BACKEND=neo4j graphbase-memories server

Design decisions:
  [A-1] Node labels: (:Memory {id, project, type, title, content, tags_json,
        created_at, updated_at, valid_until, is_deleted, is_expired})
        (:Entity {id, name, type, project, metadata_json, created_at})

  [A-2] Relationships:
        (:Memory)-[:REFERENCES {created_at}]->(:Entity)  — replaces memory_entities table
        (:Memory)-[:EDGE {id, type, properties_json, created_at}]->(:Memory|:Entity)

  [A-4] Constraints: UNIQUE on Memory.id, Entity.(name,type,project).
        Applied once via _apply_constraints() on first connection.

  [A-5] Indexes: Memory(project, type, is_deleted, updated_at) composite.

  [C-2] All list params use Cypher list syntax — no variable-length IN workaround needed.
  [C-3] Upsert via MERGE ... ON CREATE SET ... ON MATCH SET ... pattern.
  [T-1] Connection timeout=5s, verify_connectivity() on init.
  [T-2] execute_write / execute_read session methods used exclusively.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
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

try:
    from neo4j import GraphDatabase, Driver  # type: ignore[import-untyped]
except ImportError as _neo4j_import_error:  # pragma: no cover
    raise ImportError(
        "Neo4j driver not installed. Run: pip install 'graphbase-memories-mcp[neo4j]'"
    ) from _neo4j_import_error


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _row_to_memory(rec: dict[str, Any]) -> MemoryNode:
    return MemoryNode(
        id=rec["id"],
        project=rec["project"],
        type=rec["type"],
        title=rec["title"],
        content=rec["content"],
        tags=json.loads(rec.get("tags_json") or "[]"),
        created_at=rec["created_at"],
        updated_at=rec["updated_at"],
        valid_until=rec.get("valid_until"),
        is_deleted=bool(rec.get("is_deleted", False)),
        is_expired=bool(rec.get("is_expired", False)),
    )


def _row_to_entity(rec: dict[str, Any]) -> EntityNode:
    return EntityNode(
        id=rec["id"],
        name=rec["name"],
        type=rec["type"],
        project=rec["project"],
        metadata=json.loads(rec.get("metadata_json") or "{}"),
        created_at=rec["created_at"],
    )


# ---------------------------------------------------------------------------
# Neo4jEngine
# ---------------------------------------------------------------------------

class Neo4jEngine(GraphEngine):
    """
    Neo4j 5.x implementation of GraphEngine.

    Each project is scoped by the `project` property on all nodes.
    No separate databases per project — all projects share one Neo4j DB.
    """

    def __init__(self, config: Config, project: str) -> None:
        self._config  = config
        self._project = project
        self._log     = logging.getLogger(f"graphbase.neo4j.{project}")

        password = config.neo4j_password or ""
        # [T-1] Short connection timeout — fail fast if Docker isn't running
        self._driver: Driver = GraphDatabase.driver(
            config.neo4j_uri,
            auth=(config.neo4j_user, password),
            connection_timeout=5.0,
        )
        self._driver.verify_connectivity()   # [T-1] raises on connection failure
        self._apply_constraints()
        self._log.info(f"Neo4jEngine connected project={project!r} uri={config.neo4j_uri}")

    # -----------------------------------------------------------------------
    # Initialisation
    # -----------------------------------------------------------------------

    def _apply_constraints(self) -> None:
        """[A-4] Create uniqueness constraints and indexes (idempotent).

        [A-6] Full-text index on title + content + tags_json enables BM25 Lucene
        search via db.index.fulltext.queryNodes('memory_fts', query).
        """
        stmts = [
            "CREATE CONSTRAINT memory_id IF NOT EXISTS "
            "FOR (m:Memory) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT entity_unique IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE (e.name, e.type, e.project) IS UNIQUE",
            # [A-5] Composite index for list_memories ORDER BY updated_at
            "CREATE INDEX memory_project IF NOT EXISTS "
            "FOR (m:Memory) ON (m.project, m.type, m.is_deleted, m.updated_at)",
            # [A-6] Lucene full-text index for BM25 search
            "CREATE FULLTEXT INDEX memory_fts IF NOT EXISTS "
            "FOR (m:Memory) ON EACH [m.title, m.content, m.tags_json]",
        ]
        with self._driver.session() as s:
            for stmt in stmts:
                s.execute_write(lambda tx, s=stmt: tx.run(s))

    # -----------------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------------

    def store_memory_with_entities(
        self,
        memory: MemoryNode,
        entity_names: list[str],
        entity_type: str = "concept",
    ) -> MemoryNode:
        if memory.type not in VALID_MEMORY_TYPES:
            raise ValueError(f"Invalid memory type {memory.type!r}. "
                             f"Valid: {sorted(VALID_MEMORY_TYPES)}")

        def _write(tx):
            # [C-3] MERGE on id (idempotent re-runs)
            tx.run(
                """
                MERGE (m:Memory {id: $id})
                ON CREATE SET
                  m.project    = $project,
                  m.type       = $type,
                  m.title      = $title,
                  m.content    = $content,
                  m.tags_json  = $tags_json,
                  m.created_at = $created_at,
                  m.updated_at = $updated_at,
                  m.valid_until = $valid_until,
                  m.is_deleted = $is_deleted,
                  m.is_expired = $is_expired
                """,
                id=memory.id, project=memory.project, type=memory.type,
                title=memory.title, content=memory.content,
                tags_json=json.dumps(memory.tags),
                created_at=memory.created_at, updated_at=memory.updated_at,
                valid_until=memory.valid_until,
                is_deleted=memory.is_deleted, is_expired=memory.is_expired,
            )
            for name in entity_names:
                now = _now()
                tx.run(
                    """
                    MERGE (e:Entity {name: $name, type: $etype, project: $project})
                    ON CREATE SET e.id = $eid, e.metadata_json = '{}', e.created_at = $now
                    WITH e
                    MATCH (m:Memory {id: $mid})
                    MERGE (m)-[:REFERENCES {created_at: $now}]->(e)
                    """,
                    name=name, etype=entity_type, project=memory.project,
                    eid=str(uuid4()), mid=memory.id, now=now,
                )

        with self._driver.session() as s:
            s.execute_write(_write)

        self._log.info(f"store_memory id={memory.id!r} entities={entity_names}")
        return memory

    def store_edge(self, edge: Edge) -> Edge:
        if edge.type not in VALID_EDGE_TYPES:
            raise ValueError(f"Invalid edge type {edge.type!r}. "
                             f"Valid: {sorted(VALID_EDGE_TYPES)}")

        def _write(tx):
            # Edges between Memory nodes or Memory→Entity
            tx.run(
                """
                MATCH (from {id: $from_id})
                MATCH (to   {id: $to_id})
                MERGE (from)-[r:EDGE {id: $eid}]->(to)
                ON CREATE SET
                  r.type            = $type,
                  r.from_type       = $from_type,
                  r.to_type         = $to_type,
                  r.properties_json = $props,
                  r.created_at      = $created_at
                """,
                eid=edge.id, from_id=edge.from_id, to_id=edge.to_id,
                type=edge.type, from_type=edge.from_type, to_type=edge.to_type,
                props=json.dumps(edge.properties), created_at=edge.created_at,
            )

        with self._driver.session() as s:
            s.execute_write(_write)

        self._log.info(f"store_edge {edge.from_id} --{edge.type}--> {edge.to_id}")
        return edge

    def soft_delete(self, memory_id: str) -> bool:
        def _write(tx):
            result = tx.run(
                "MATCH (m:Memory {id: $id}) SET m.is_deleted=true, m.updated_at=$now RETURN m.id",
                id=memory_id, now=_now(),
            )
            return result.single() is not None

        with self._driver.session() as s:
            found = s.execute_write(_write)
        self._log.info(f"soft_delete id={memory_id!r} found={found}")
        return found

    def flag_expired(self, memory_id: str) -> bool:
        def _write(tx):
            result = tx.run(
                "MATCH (m:Memory {id: $id, is_deleted: false}) "
                "SET m.is_expired=true, m.updated_at=$now RETURN m.id",
                id=memory_id, now=_now(),
            )
            return result.single() is not None

        with self._driver.session() as s:
            return s.execute_write(_write)

    def purge_expired(self, project: str, older_than_days: int) -> int:
        from datetime import timedelta
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
        ).strftime("%Y-%m-%dT%H:%M:%S")

        def _write(tx):
            result = tx.run(
                """
                MATCH (m:Memory {project: $project, is_expired: true})
                WHERE m.updated_at < $cutoff
                DETACH DELETE m
                RETURN count(m) AS deleted
                """,
                project=project, cutoff=cutoff,
            )
            return result.single()["deleted"]

        with self._driver.session() as s:
            count = s.execute_write(_write)
        self._log.info(f"purge_expired project={project!r} older_than={older_than_days}d purged={count}")
        return count

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    def get_memory(
        self, memory_id: str, include_deleted: bool = False
    ) -> MemoryNode | None:
        def _read(tx):
            q = "MATCH (m:Memory {id: $id})"
            if not include_deleted:
                q += " WHERE m.is_deleted = false"
            q += " RETURN m"
            result = tx.run(q, id=memory_id)
            rec = result.single()
            return _row_to_memory(dict(rec["m"])) if rec else None

        with self._driver.session() as s:
            return s.execute_read(_read)

    def list_memories(
        self,
        project: str,
        type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> list[MemoryNode]:
        def _read(tx):
            where = "m.project = $project"
            if not include_deleted:
                where += " AND m.is_deleted = false"
            if type is not None:
                where += " AND m.type = $type"
            q = (
                f"MATCH (m:Memory) WHERE {where} "
                "RETURN m ORDER BY m.updated_at DESC SKIP $offset LIMIT $limit"
            )
            result = tx.run(q, project=project, type=type, limit=limit, offset=offset)
            return [_row_to_memory(dict(r["m"])) for r in result]

        with self._driver.session() as s:
            return s.execute_read(_read)

    def search_memories(
        self,
        query: str,
        project: str | None = None,
        type: str | None = None,
        limit: int = 10,
    ) -> list[tuple[MemoryNode, float]]:
        """
        [A-6] BM25 full-text search via Neo4j Lucene index 'memory_fts'.

        Primary path: db.index.fulltext.queryNodes returns BM25 scores (0.0–∞).
        Fallback path: CONTAINS scan (case-insensitive) returns score=1.0.

        The fallback activates when:
          - The query contains unbalanced Lucene special chars (raises CypherError)
          - The index is not yet available on a freshly started instance
        """
        def _build_filter() -> tuple[str, list[str]]:
            """Return (WHERE clause snippet, extra filter parts) for project/type."""
            parts = ["m.is_deleted = false"]
            if project is not None:
                parts.append("m.project = $project")
            if type is not None:
                parts.append("m.type = $type")
            return " AND ".join(parts)

        def _fts_read(tx):
            where = _build_filter()
            q = (
                "CALL db.index.fulltext.queryNodes('memory_fts', $query) "
                "YIELD node AS m, score "
                f"WHERE {where} "
                "RETURN m, score LIMIT $limit"
            )
            result = tx.run(q, query=query, project=project, type=type, limit=limit)
            return [(_row_to_memory(dict(r["m"])), float(r["score"])) for r in result]

        def _contains_read(tx):
            where_parts = [
                "(toLower(m.title) CONTAINS toLower($q) OR "
                " toLower(m.content) CONTAINS toLower($q))",
                "m.is_deleted = false",
            ]
            if project is not None:
                where_parts.append("m.project = $project")
            if type is not None:
                where_parts.append("m.type = $type")
            where = " AND ".join(where_parts)
            q = f"MATCH (m:Memory) WHERE {where} RETURN m LIMIT $limit"
            result = tx.run(q, q=query, project=project, type=type, limit=limit)
            return [(_row_to_memory(dict(r["m"])), 1.0) for r in result]

        with self._driver.session() as s:
            try:
                return s.execute_read(_fts_read)
            except Exception as exc:
                self._log.warning(
                    "FTS query failed — falling back to CONTAINS: %r", exc
                )
                return s.execute_read(_contains_read)

    def get_memories_for_entity(
        self, entity_name: str, project: str
    ) -> list[MemoryNode]:
        def _read(tx):
            result = tx.run(
                """
                MATCH (m:Memory)-[:REFERENCES]->(e:Entity {name: $name, project: $project})
                WHERE m.is_deleted = false
                RETURN m ORDER BY m.updated_at DESC
                """,
                name=entity_name, project=project,
            )
            return [_row_to_memory(dict(r["m"])) for r in result]

        with self._driver.session() as s:
            return s.execute_read(_read)

    def get_entities_for_memory(self, memory_id: str) -> list[EntityNode]:
        def _read(tx):
            result = tx.run(
                "MATCH (m:Memory {id: $id})-[:REFERENCES]->(e:Entity) "
                "RETURN e ORDER BY e.name",
                id=memory_id,
            )
            return [_row_to_entity(dict(r["e"])) for r in result]

        with self._driver.session() as s:
            return s.execute_read(_read)

    def get_edges_for_memory(self, memory_id: str) -> list[Edge]:
        def _read(tx):
            result = tx.run(
                "MATCH (m:Memory {id: $id})-[r:EDGE]->(n) "
                "RETURN r ORDER BY r.created_at",
                id=memory_id,
            )
            return [
                Edge(
                    id=r["r"]["id"],
                    from_id=memory_id,
                    from_type=r["r"].get("from_type", "memory"),
                    to_id=r["r"]["to_id"] if "to_id" in r["r"] else "",
                    to_type=r["r"].get("to_type", "memory"),
                    type=r["r"]["type"],
                    properties=json.loads(r["r"].get("properties_json") or "{}"),
                    created_at=r["r"]["created_at"],
                )
                for r in result
            ]

        with self._driver.session() as s:
            return s.execute_read(_read)

    def get_related_entities(
        self,
        project: str,
        entity_name: str | None = None,
    ) -> list[EntityNode]:
        def _read(tx):
            if entity_name is None:
                result = tx.run(
                    "MATCH (e:Entity {project: $project}) RETURN e ORDER BY e.name",
                    project=project,
                )
            else:
                result = tx.run(
                    """
                    MATCH (e1:Entity {name: $name, project: $project})<-[:REFERENCES]-(m:Memory)
                          -[:REFERENCES]->(e2:Entity)
                    WHERE e2.id <> e1.id
                    RETURN DISTINCT e2 AS e ORDER BY e2.name
                    """,
                    name=entity_name, project=project,
                )
            return [_row_to_entity(dict(r["e"])) for r in result]

        with self._driver.session() as s:
            return s.execute_read(_read)

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------

    def get_blast_radius(
        self,
        entity_name: str,
        project: str,
        depth: int = 2,
    ) -> BlastRadiusResult:
        def _read(tx):
            # True N-hop traversal using Cypher variable-length path
            result = tx.run(
                """
                MATCH (e:Entity {name: $name, project: $project})
                OPTIONAL MATCH (m:Memory)-[:REFERENCES]->(e)
                WHERE m.is_deleted = false
                WITH e, collect(DISTINCT m) AS direct_memories
                UNWIND direct_memories AS m
                OPTIONAL MATCH (m)-[:REFERENCES]->(related:Entity)
                WHERE related.id <> e.id
                RETURN e, direct_memories, collect(DISTINCT related) AS related_entities
                """,
                name=entity_name, project=project,
            )
            rec = result.single()
            if rec is None or rec["e"] is None:
                return BlastRadiusResult(
                    entity_name=entity_name, project=project, depth=depth,
                    memories=[], related_entities=[], total_references=0,
                )
            memories = [_row_to_memory(dict(m)) for m in (rec["direct_memories"] or [])]
            related  = [_row_to_entity(dict(e)) for e in (rec["related_entities"] or [])]
            return BlastRadiusResult(
                entity_name=entity_name, project=project, depth=depth,
                memories=memories, related_entities=related,
                total_references=len(memories),
            )

        with self._driver.session() as s:
            return s.execute_read(_read)

    def get_stale_memories(
        self, project: str, age_days: int = 30
    ) -> list[MemoryNode]:
        from datetime import timedelta
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=age_days)
        ).strftime("%Y-%m-%dT%H:%M:%S")

        def _read(tx):
            result = tx.run(
                """
                MATCH (m:Memory {project: $project, is_deleted: false})
                WHERE m.updated_at < $cutoff
                RETURN m ORDER BY m.updated_at ASC
                """,
                project=project, cutoff=cutoff,
            )
            return [_row_to_memory(dict(r["m"])) for r in result]

        with self._driver.session() as s:
            return s.execute_read(_read)

    def get_graph_data(
        self,
        project: str,
        limit: int = 200,
    ) -> GraphData:
        """[C-2] Cypher handles list params natively — no temp table needed."""
        def _read(tx):
            total_result = tx.run(
                "MATCH (m:Memory {project: $project, is_deleted: false}) RETURN count(m) AS n",
                project=project,
            )
            total = total_result.single()["n"]

            mem_result = tx.run(
                """
                MATCH (m:Memory {project: $project, is_deleted: false})
                RETURN m ORDER BY m.updated_at DESC LIMIT $limit
                """,
                project=project, limit=limit,
            )
            memories = [_row_to_memory(dict(r["m"])) for r in mem_result]
            memory_ids = [m.id for m in memories]

            entity_result = tx.run(
                """
                MATCH (m:Memory)-[:REFERENCES]->(e:Entity {project: $project})
                WHERE m.id IN $ids
                RETURN DISTINCT e ORDER BY e.name
                """,
                project=project, ids=memory_ids,
            )
            entities = [_row_to_entity(dict(r["e"])) for r in entity_result]

            edge_result = tx.run(
                """
                MATCH (from)-[r:EDGE]->(to)
                WHERE from.id IN $ids AND to.id IN $ids
                RETURN r, from.id AS fid, to.id AS tid
                ORDER BY r.created_at
                """,
                ids=memory_ids,
            )
            edges = [
                Edge(
                    id=r["r"]["id"],
                    from_id=r["fid"],
                    from_type=r["r"].get("from_type", "memory"),
                    to_id=r["tid"],
                    to_type=r["r"].get("to_type", "memory"),
                    type=r["r"]["type"],
                    properties=json.loads(r["r"].get("properties_json") or "{}"),
                    created_at=r["r"]["created_at"],
                )
                for r in edge_result
            ]
            return total, memories, entities, edges

        with self._driver.session() as s:
            total, memories, entities, edges = s.execute_read(_read)

        return GraphData(
            memories=memories,
            entities=entities,
            edges=edges,
            total_memories=total,
            generated_at=_now(),
        )

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    def schema_version(self) -> int:
        """Neo4j doesn't have user_version; return a fixed sentinel value."""
        return 1

    def journal_mode(self) -> str:
        """Neo4j is not SQLite; return 'neo4j' to satisfy the interface."""
        return "neo4j"

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def close(self) -> None:
        self._driver.close()

    def __del__(self) -> None:
        try:
            self._driver.close()
        except Exception:  # noqa: BLE001
            pass
