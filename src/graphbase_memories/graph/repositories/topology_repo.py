"""
Topology repository — CRUD and traversal for Service, DataSource, MessageQueue,
Feature, and BoundedContext nodes, plus all topology relationship types.

T3.1 | ADR-TOPO-001

Dynamic link queries (link_service_dependency, link_service_datasource,
link_service_mq) use f-string interpolation AFTER whitelist validation against
TOPOLOGY_LINK_TYPES — same injection-safe pattern as entity_repo.link_entities().

Read-back pattern: upsert writes via session.run() then immediately re-reads the
stored node properties, because the RETURN clause in MERGE queries may reflect
pre-SET property values in some Neo4j driver versions.
"""

from __future__ import annotations

import re

from neo4j import AsyncDriver

from graphbase_memories.graph.driver import TOPOLOGY_Q_QUERIES, TOPOLOGY_QUERIES
from graphbase_memories.graph.models import (
    BoundedContextNode,
    DataSourceNode,
    FeatureNode,
    MessageQueueNode,
    ServiceNode,
)

# Whitelisted relationship types for topology dynamic link queries.
# f-string interpolation only happens AFTER membership check — injection safe.
TOPOLOGY_LINK_TYPES: frozenset[str] = frozenset(
    [
        "CALLS_DOWNSTREAM",
        "CALLS_UPSTREAM",
        "READS_FROM",
        "WRITES_TO",
        "PUBLISHES_TO",
        "SUBSCRIBES_TO",
    ]
)

# Maps direction string → named query block in topology_queries.cypher.
# Three separate blocks exist because Neo4j does not support parameterized
# relationship types in variable-length path expressions (ADR-TOPO-001 Risk 1).
_DEP_QUERY_MAP: dict[str, str] = {
    "downstream": "GET_SERVICE_DEPENDENCIES_DOWNSTREAM",
    "upstream": "GET_SERVICE_DEPENDENCIES_UPSTREAM",
    "both": "GET_SERVICE_DEPENDENCIES_BOTH",
}


def _query(name: str) -> str:
    """Extract a named block from topology.cypher (CRUD queries)."""
    pattern = rf"//\s*==\s*{re.escape(name)}\s*==\s*\n(.*?)(?=\n//\s*==|\Z)"
    m = re.search(pattern, TOPOLOGY_QUERIES, re.DOTALL)
    if not m:
        raise KeyError(f"Query block '{name}' not found in topology.cypher")
    return m.group(1).strip().rstrip(";")


def _tq(name: str) -> str:
    """Extract a named block from topology_queries.cypher (traversal queries)."""
    pattern = rf"//\s*==\s*{re.escape(name)}\s*==\s*\n(.*?)(?=\n//\s*==|\Z)"
    m = re.search(pattern, TOPOLOGY_Q_QUERIES, re.DOTALL)
    if not m:
        raise KeyError(f"Query block '{name}' not found in topology_queries.cypher")
    return m.group(1).strip().rstrip(";")


# ── Upsert operations ────────────────────────────────────────────────────────


async def upsert_service(
    driver: AsyncDriver,
    database: str,
    *,
    service_id: str,
    name: str,
    workspace_id: str,
    display_name: str | None = None,
    service_type: str | None = None,
    bounded_context: str | None = None,
    owner_team: str | None = None,
    health_status: str = "unknown",
    env: str | None = None,
    version: str | None = None,
    sla: str | None = None,
    docs_url: str | None = None,
    tags: list[str] | None = None,
) -> ServiceNode:
    """Upsert a :Project:Service node. Creates :Project if absent (scope_engine compat)."""
    async with driver.session(database=database) as session:
        await session.run(
            _query("UPSERT_SERVICE_TOPOLOGY"),
            service_id=service_id,
            name=name,
            workspace_id=workspace_id,
            display_name=display_name or name,
            service_type=service_type or "other",
            bounded_context=bounded_context or "",
            owner_team=owner_team or "",
            health_status=health_status,
            env=env or "",
            version=version or "",
            sla=sla or "",
            docs_url=docs_url or "",
            tags=tags or [],
        )
        result = await session.run(
            "MATCH (n:Service {id: $sid}) RETURN properties(n) AS p",
            sid=service_id,
        )
        record = await result.single()

    return ServiceNode.from_record(record["p"])


async def upsert_datasource(
    driver: AsyncDriver,
    database: str,
    *,
    source_id: str,
    source_type: str,
    host: str | None = None,
    workspace_id: str,
    owner_team: str | None = None,
    health_status: str = "unknown",
    version: str | None = None,
    tags: list[str] | None = None,
) -> DataSourceNode:
    async with driver.session(database=database) as session:
        await session.run(
            _query("UPSERT_DATASOURCE"),
            source_id=source_id,
            source_type=source_type,
            host=host or "",
            workspace_id=workspace_id,
            owner_team=owner_team or "",
            health_status=health_status,
            version=version or "",
            tags=tags or [],
        )
        result = await session.run(
            "MATCH (ds:DataSource {id: $sid}) RETURN properties(ds) AS p",
            sid=source_id,
        )
        record = await result.single()

    return DataSourceNode.from_record(record["p"])


async def upsert_message_queue(
    driver: AsyncDriver,
    database: str,
    *,
    queue_id: str,
    queue_type: str,
    topic_or_exchange: str | None = None,
    workspace_id: str,
    owner_team: str | None = None,
    schema_version: str | None = None,
    tags: list[str] | None = None,
) -> MessageQueueNode:
    async with driver.session(database=database) as session:
        await session.run(
            _query("UPSERT_MESSAGE_QUEUE"),
            queue_id=queue_id,
            queue_type=queue_type,
            topic_or_exchange=topic_or_exchange or "",
            workspace_id=workspace_id,
            owner_team=owner_team or "",
            schema_version=schema_version or "",
            tags=tags or [],
        )
        result = await session.run(
            "MATCH (mq:MessageQueue {id: $qid}) RETURN properties(mq) AS p",
            qid=queue_id,
        )
        record = await result.single()

    return MessageQueueNode.from_record(record["p"])


async def upsert_feature(
    driver: AsyncDriver,
    database: str,
    *,
    feature_id: str,
    name: str,
    workspace_id: str,
    workflow_order: int = 0,
    owner_team: str | None = None,
    tags: list[str] | None = None,
) -> FeatureNode:
    async with driver.session(database=database) as session:
        await session.run(
            _query("UPSERT_FEATURE"),
            feature_id=feature_id,
            name=name,
            workspace_id=workspace_id,
            workflow_order=workflow_order,
            owner_team=owner_team or "",
            tags=tags or [],
        )
        result = await session.run(
            "MATCH (f:Feature {id: $fid}) RETURN properties(f) AS p",
            fid=feature_id,
        )
        record = await result.single()

    return FeatureNode.from_record(record["p"])


async def upsert_bounded_context(
    driver: AsyncDriver,
    database: str,
    *,
    context_id: str,
    name: str,
    domain: str | None = None,
    workspace_id: str,
    tags: list[str] | None = None,
) -> BoundedContextNode:
    async with driver.session(database=database) as session:
        await session.run(
            _query("UPSERT_BOUNDED_CONTEXT"),
            context_id=context_id,
            name=name,
            domain=domain or "",
            workspace_id=workspace_id,
            tags=tags or [],
        )
        result = await session.run(
            "MATCH (bc:BoundedContext {id: $bid}) RETURN properties(bc) AS p",
            bid=context_id,
        )
        record = await result.single()

    return BoundedContextNode.from_record(record["p"])


# ── Relationship operations ──────────────────────────────────────────────────


async def link_service_dependency(
    driver: AsyncDriver,
    database: str,
    from_id: str,
    to_id: str,
    rel_type: str,
) -> dict:
    """MERGE a CALLS_DOWNSTREAM or CALLS_UPSTREAM edge between two services."""
    if rel_type not in TOPOLOGY_LINK_TYPES:
        raise ValueError(f"rel_type {rel_type!r} not in TOPOLOGY_LINK_TYPES whitelist")
    cypher = (
        f"MATCH (a:Service {{id: $from_id}})\n"
        f"MATCH (b:Service {{id: $to_id}})\n"
        f"MERGE (a)-[r:{rel_type}]->(b)\n"
        f"SET r.updated_at = datetime()\n"
        f"RETURN a.id AS from_id, b.id AS to_id, '{rel_type}' AS rel_type"
    )
    async with driver.session(database=database) as session:
        result = await session.run(cypher, from_id=from_id, to_id=to_id)
        record = await result.single()
    return dict(record) if record else {}


async def link_service_datasource(
    driver: AsyncDriver,
    database: str,
    service_id: str,
    source_id: str,
    rel_type: str,
) -> dict:
    """MERGE a READS_FROM or WRITES_TO edge from Service to DataSource."""
    if rel_type not in TOPOLOGY_LINK_TYPES:
        raise ValueError(f"rel_type {rel_type!r} not in TOPOLOGY_LINK_TYPES whitelist")
    cypher = (
        f"MATCH (s:Service {{id: $service_id}})\n"
        f"MATCH (ds:DataSource {{id: $source_id}})\n"
        f"MERGE (s)-[r:{rel_type}]->(ds)\n"
        f"SET r.updated_at = datetime()\n"
        f"RETURN s.id AS service_id, ds.id AS source_id, '{rel_type}' AS rel_type"
    )
    async with driver.session(database=database) as session:
        result = await session.run(cypher, service_id=service_id, source_id=source_id)
        record = await result.single()
    return dict(record) if record else {}


async def link_service_mq(
    driver: AsyncDriver,
    database: str,
    service_id: str,
    queue_id: str,
    rel_type: str,
) -> dict:
    """MERGE a PUBLISHES_TO or SUBSCRIBES_TO edge from Service to MessageQueue."""
    if rel_type not in TOPOLOGY_LINK_TYPES:
        raise ValueError(f"rel_type {rel_type!r} not in TOPOLOGY_LINK_TYPES whitelist")
    cypher = (
        f"MATCH (s:Service {{id: $service_id}})\n"
        f"MATCH (mq:MessageQueue {{id: $queue_id}})\n"
        f"MERGE (s)-[r:{rel_type}]->(mq)\n"
        f"SET r.updated_at = datetime()\n"
        f"RETURN s.id AS service_id, mq.id AS queue_id, '{rel_type}' AS rel_type"
    )
    async with driver.session(database=database) as session:
        result = await session.run(cypher, service_id=service_id, queue_id=queue_id)
        record = await result.single()
    return dict(record) if record else {}


async def link_feature_service(
    driver: AsyncDriver,
    database: str,
    feature_id: str,
    service_id: str,
    step_order: int,
    role: str,
) -> dict:
    """MERGE INVOLVES relationship from Feature to Service, setting step_order and role."""
    async with driver.session(database=database) as session:
        result = await session.run(
            _query("LINK_FEATURE_SERVICE"),
            feature_id=feature_id,
            service_id=service_id,
            step_order=step_order,
            role=role,
        )
        record = await result.single()
    return dict(record) if record else {}


async def link_service_context(
    driver: AsyncDriver,
    database: str,
    service_id: str,
    context_id: str,
    ownership: str,
) -> dict:
    """MERGE MEMBER_OF_CONTEXT relationship from Service to BoundedContext."""
    async with driver.session(database=database) as session:
        result = await session.run(
            _query("LINK_SERVICE_CONTEXT"),
            service_id=service_id,
            context_id=context_id,
            ownership=ownership,
        )
        record = await result.single()
    return dict(record) if record else {}


# ── Traversal queries ────────────────────────────────────────────────────────


async def get_service_dependencies(
    driver: AsyncDriver,
    database: str,
    service_id: str,
    direction: str = "downstream",
    depth: int = 2,
    limit: int = 50,
) -> list[dict]:
    """
    Traverse service dependency graph up to `depth` hops.
    direction: "downstream" | "upstream" | "both"
    depth clamped to 1-6 before execution.
    """
    if direction not in _DEP_QUERY_MAP:
        raise ValueError(f"direction {direction!r} must be one of {sorted(_DEP_QUERY_MAP)}")
    depth = max(1, min(6, depth))
    # Neo4j does not support parameterized bounds in variable-length path expressions
    # (ADR-TOPO-001 Risk 1). depth is an integer already clamped to 1-6 — safe to
    # interpolate directly into the Cypher string rather than passing as a parameter.
    cypher = _tq(_DEP_QUERY_MAP[direction]).replace("$depth", str(depth))
    async with driver.session(database=database) as session:
        result = await session.run(cypher, service_id=service_id, limit=limit)
        records = await result.data()
    return records


async def get_feature_workflow(
    driver: AsyncDriver,
    database: str,
    feature_id: str,
) -> list[dict]:
    """Return all services involved in a feature, ordered by workflow step."""
    async with driver.session(database=database) as session:
        result = await session.run(_tq("GET_FEATURE_WORKFLOW"), feature_id=feature_id)
        records = await result.data()
    return records
