"""
GraphEngine ABC — the contract all storage backends must satisfy.

Dataclasses defined here are the exchange types for the entire tool layer.
The tool layer never imports from sqlite_engine or neo4j_engine directly.

Design decisions:
  - store_memory_with_entities() is the ONLY write entry point for the tool
    layer. [R8] The 3-step (store_memory + store_entity + link) is internal.
  - BlastRadiusResult is a typed dataclass. [R1] Not a raw dict.
  - include_deleted=False on read methods. [R3]
  - get_related_entities() required for get_context() YAML rendering.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Node / Edge dataclasses (shared exchange types)
# ---------------------------------------------------------------------------


@dataclass
class MemoryNode:
    id: str
    project: str
    type: str           # session | decision | pattern | context | entity_fact
    title: str
    content: str
    tags: list[str]
    created_at: str     # ISO-8601
    updated_at: str     # ISO-8601
    valid_until: str | None
    is_deleted: bool
    is_expired: bool = False   # [Q4] flag-only decay — never auto-deleted


@dataclass
class EntityNode:
    id: str
    name: str
    type: str           # service | file | feature | concept | table | topic
    project: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str | None = None   # None on pre-v2 rows; set by upsert_entity


@dataclass
class Edge:
    id: str
    from_id: str
    from_type: str      # [B1] 'memory' | 'entity' — no FK, discriminator only
    to_id: str
    to_type: str        # [B1] 'memory' | 'entity'
    type: str           # SUPERSEDES | RELATES_TO | LEARNED_DURING | DEPENDS_ON | IMPLEMENTS
    properties: dict[str, Any]
    created_at: str


@dataclass
class BlastRadiusResult:    # [R1] typed return — replaces raw dict
    entity_name: str
    project: str
    depth: int
    memories: list[MemoryNode]
    related_entities: list[EntityNode]
    total_references: int


@dataclass
class GraphData:
    """Bulk graph snapshot for the CTL Graph View and graph_view MCP tool."""
    memories: list[MemoryNode]
    entities: list[EntityNode]
    edges: list[Edge]
    total_memories: int                         # non-deleted count (may exceed len(memories) if limit applied)
    generated_at: str                           # ISO-8601 UTC timestamp
    memory_entity_links: list[tuple[str, str]] = field(default_factory=list)
    # [(memory_id, entity_id), ...] — pre-fetched join for O(1) lookups in graph_view.
    # Avoids N+1 queries when building the memory→entity link list. [P0-1]


# ---------------------------------------------------------------------------
# GraphEngine ABC
# ---------------------------------------------------------------------------

VALID_MEMORY_TYPES = frozenset(
    {"session", "decision", "pattern", "context", "entity_fact"}
)
VALID_ENTITY_TYPES = frozenset(
    {"service", "file", "feature", "concept", "table", "topic"}
)
VALID_EDGE_TYPES = frozenset(
    {"SUPERSEDES", "RELATES_TO", "LEARNED_DURING", "DEPENDS_ON", "IMPLEMENTS"}
)


class GraphEngine(ABC):
    """
    Abstract interface for graph-backed memory storage.

    Backends: SQLiteEngine (v1, zero deps) | Neo4jEngine (v2, local Docker).
    Swap via GRAPHBASE_BACKEND env var — tool layer is unchanged.
    """

    # -----------------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------------

    @abstractmethod
    def store_memory_with_entities(
        self,
        memory: MemoryNode,
        entity_names: list[str],
        entity_type: str = "concept",
    ) -> MemoryNode:
        """
        [R8] Single high-level write method for the tool layer.

        Atomically: stores the MemoryNode, upserts each EntityNode by name,
        and creates memory_entities links. The caller never manages the
        3-step sequence directly.
        """
        ...

    @abstractmethod
    def store_edge(self, edge: Edge) -> Edge:
        """Store a directed edge between any two nodes (Memory or Entity)."""
        ...

    @abstractmethod
    def soft_delete(self, memory_id: str) -> bool:
        """Set is_deleted=1. Memory remains readable with include_deleted=True."""
        ...

    @abstractmethod
    def flag_expired(self, memory_id: str) -> bool:
        """[Q4] Set is_expired=1. Does NOT delete. Returns True if found."""
        ...

    @abstractmethod
    def purge_expired(self, project: str, older_than_days: int) -> int:
        """
        [Q4] Permanently DELETE memories where is_expired=1 AND
        updated_at is older than older_than_days. Returns count purged.
        Irreversible — caller should call get_stale_memories() first.
        """
        ...

    @abstractmethod
    def upsert_entity(
        self,
        name: str,
        type: str,
        project: str,
        metadata: dict[str, Any],
    ) -> EntityNode:
        """
        Create or update an entity by (name, type, project) key.

        Full metadata replacement — not partial merge. The caller owns the
        complete metadata dict. Sets updated_at = now() on both create and update.

        Intentional exception to append-only design [Q5]: EntityNode.metadata
        represents current real-world state (service dependencies, databases),
        not a historical record. Prior metadata values are NOT preserved.

        Raises ValueError if type is not in VALID_ENTITY_TYPES.
        """
        ...

    @abstractmethod
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
        Create a directed entity→entity edge.

        Idempotent: (from_id, to_id, edge_type) is unique among entity edges.
        If the edge already exists, returns the existing Edge without inserting
        a duplicate.

        Raises ValueError if either entity does not exist in the project.
        Raises ValueError if edge_type is not DEPENDS_ON or IMPLEMENTS.
        Does NOT auto-create missing entities — use upsert_entity() first.
        """
        ...

    @abstractmethod
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
        Delete the entity→entity edge matching (from_id, to_id, edge_type).

        Hard-delete — not soft-delete. Returns True if the edge was found and
        deleted, False if no matching edge existed.
        """
        ...

    @abstractmethod
    def find_edge(
        self,
        from_id: str,
        to_id: str,
        edge_type: str,
    ) -> Edge | None:
        """
        Look up a single directed edge by (from_id, to_id, edge_type).

        Returns the matching Edge if found, None if no edge exists.
        O(log n) via idx_rel_lookup — does NOT load all edges for from_id.

        Unlike get_edges_for_memory(), this method is cross-type:
        it matches any edge regardless of from_type/to_type.
        Used exclusively for idempotency checks in relate_memories.
        """
        ...

    @abstractmethod
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
        """
        Create a directed entity→entity edge using pre-resolved entity UUIDs.

        Identical semantics to link_entities() — same idempotency, same
        edge_type validation, same return type.

        Use when the caller already holds entity IDs to avoid redundant
        SELECT per call. Does NOT validate entity existence — the caller
        is responsible for ensuring both IDs are valid.

        Raises ValueError if edge_type is not DEPENDS_ON or IMPLEMENTS.
        """
        ...

    @contextlib.contextmanager
    def batch_write(self):
        """
        No-op default implementation. Subclasses override for commit batching.

        The default yields immediately — callers get per-call commit semantics
        (correct but not optimised). Neo4jEngine inherits this default since
        Neo4j transactions have different semantics.
        """
        yield

    # -----------------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------------

    @abstractmethod
    def get_memory(
        self,
        memory_id: str,
        include_deleted: bool = False,  # [R3]
    ) -> MemoryNode | None:
        ...

    @abstractmethod
    def list_memories(
        self,
        project: str,
        type: str | None = None,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,  # [R3]
    ) -> list[MemoryNode]:
        ...

    @abstractmethod
    def search_memories(
        self,
        query: str,
        project: str | None = None,
        type: str | None = None,
        limit: int = 10,
    ) -> list[tuple[MemoryNode, float]]:
        """
        Full-text search. Returns (node, score) pairs, best match first.
        Excludes soft-deleted memories regardless of include_deleted.
        """
        ...

    @abstractmethod
    def get_memories_for_entity(
        self,
        entity_name: str,
        project: str,
    ) -> list[MemoryNode]:
        """Return all non-deleted memories that reference entity_name."""
        ...

    @abstractmethod
    def get_entities_for_memory(
        self,
        memory_id: str,
    ) -> list[EntityNode]:
        """Return all entities linked to a specific memory."""
        ...

    @abstractmethod
    def get_edges_for_memory(
        self,
        memory_id: str,
    ) -> list[Edge]:
        """Return outgoing edges from a specific memory node."""
        ...

    @abstractmethod
    def get_related_entities(
        self,
        project: str,
        entity_name: str | None = None,
    ) -> list[EntityNode]:
        """
        Return entities for a project, optionally co-occurring with entity_name
        (i.e. sharing at least one memory reference).
        """
        ...

    @abstractmethod
    def get_entity(
        self,
        name: str,
        type: str,
        project: str,
    ) -> EntityNode | None:
        """
        Direct entity lookup by (name, type, project).

        Returns None if not found — callers must treat None as "no prior history"
        and use a hard-coded type constant (not a variable) to avoid ambiguity
        between "wrong type" and "entity does not exist".
        """
        ...

    # -----------------------------------------------------------------------
    # Analysis
    # -----------------------------------------------------------------------

    @abstractmethod
    def get_blast_radius(
        self,
        entity_name: str,
        project: str,
        depth: int = 2,
    ) -> BlastRadiusResult:  # [R1] typed return
        ...

    @abstractmethod
    def get_stale_memories(
        self,
        project: str,
        age_days: int = 30,
    ) -> list[MemoryNode]:
        """Return non-deleted memories not updated in age_days days."""
        ...

    @abstractmethod
    def get_graph_data(
        self,
        project: str,
        limit: int = 200,
    ) -> GraphData:
        """
        Return a bulk graph snapshot for the project.

        Fetches up to `limit` non-deleted memories (newest first), all entities
        for those memories, and all edges where both endpoints are in the result
        set. Used by the CTL Graph View tab and the graph_view MCP tool.

        Implementations must avoid SQLITE_MAX_VARIABLE_NUMBER (999) when
        fetching edges for many IDs — use a temp table or equivalent.
        """
        ...

    # -----------------------------------------------------------------------
    # Introspection (for tests and CLI)
    # -----------------------------------------------------------------------

    @abstractmethod
    def schema_version(self) -> int:
        """Return the current PRAGMA user_version. [B3]"""
        ...

    @abstractmethod
    def journal_mode(self) -> str:
        """Return the current journal mode (should be 'wal'). [R7]"""
        ...

    def _backdate(self, memory_id: str, days: int) -> None:  # noqa: B027
        """
        Test helper: set updated_at to (now - days).
        Not abstract — only SQLiteEngine implements, ignored by Neo4jEngine.
        """