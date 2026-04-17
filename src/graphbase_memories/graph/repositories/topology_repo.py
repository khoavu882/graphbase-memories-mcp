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

import json
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
        "READS_WRITES",
        "PUBLISHES_TO",
        "SUBSCRIBES_TO",
        "INVOLVES",
        "MEMBER_OF_CONTEXT",
    ]
)

# Whitelisted node labels for _dry_run_check f-string interpolation.
# Mirrors the TOPOLOGY_LINK_TYPES pattern — injection safe.
_ALLOWED_NODE_LABELS: frozenset[str] = frozenset(
    ["Service", "DataSource", "MessageQueue", "Feature", "BoundedContext"]
)

# Topology node labels — used by link_topology_nodes to identify node type.
_TOPOLOGY_LABELS: frozenset[str] = frozenset(
    {"Service", "DataSource", "MessageQueue", "Feature", "BoundedContext"}
)

# Allowed relationship types per (from_label, to_label) pair.
# Static matrix — prevents invalid cross-node-type edges at validation time.
_LINK_COMPATIBILITY: dict[tuple[str, str], frozenset[str]] = {
    ("Service", "Service"): frozenset({"CALLS_DOWNSTREAM", "CALLS_UPSTREAM"}),
    ("Service", "DataSource"): frozenset({"READS_FROM", "WRITES_TO", "READS_WRITES"}),
    ("Service", "MessageQueue"): frozenset({"PUBLISHES_TO", "SUBSCRIBES_TO"}),
    ("Feature", "Service"): frozenset({"INVOLVES"}),
    ("Service", "BoundedContext"): frozenset({"MEMBER_OF_CONTEXT"}),
}

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


async def _dry_run_check(
    driver: AsyncDriver,
    database: str,
    label_a: str,
    id_a: str,
    label_b: str,
    id_b: str,
) -> dict:
    """MATCH both endpoint nodes. Raise ValueError if either is missing.

    Used by link_* functions when dry_run=True — validates without writing.
    label_a and label_b must be members of _ALLOWED_NODE_LABELS (injection guard).
    """
    for label in (label_a, label_b):
        if label not in _ALLOWED_NODE_LABELS:
            raise ValueError(f"Node label {label!r} not in _ALLOWED_NODE_LABELS whitelist")
    cypher = (
        f"OPTIONAL MATCH (a:{label_a} {{id: $id_a}})\n"
        f"OPTIONAL MATCH (b:{label_b} {{id: $id_b}})\n"
        f"RETURN a IS NOT NULL AS a_exists, b IS NOT NULL AS b_exists"
    )
    async with driver.session(database=database) as session:
        result = await session.run(cypher, id_a=id_a, id_b=id_b)
        record = await result.single()
    if not record or not record["a_exists"]:
        raise ValueError(f"dry_run: {label_a} node '{id_a}' not found")
    if not record["b_exists"]:
        raise ValueError(f"dry_run: {label_b} node '{id_b}' not found")
    return {"dry_run": True, "status": "dry_run_ok", "from_id": id_a, "to_id": id_b}


async def link_service_dependency(
    driver: AsyncDriver,
    database: str,
    from_id: str,
    to_id: str,
    rel_type: str,
    protocol: str | None = None,
    timeout_ms: int | None = None,
    criticality: str | None = None,
    metadata: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """MERGE a CALLS_DOWNSTREAM or CALLS_UPSTREAM edge between two services.

    Optional edge properties (protocol, timeout_ms, criticality) are written only
    when provided; omitting them on a re-link preserves existing values (CASE WHEN pattern).
    """
    if rel_type not in TOPOLOGY_LINK_TYPES:
        raise ValueError(f"rel_type {rel_type!r} not in TOPOLOGY_LINK_TYPES whitelist")
    if dry_run:
        return await _dry_run_check(driver, database, "Service", from_id, "Service", to_id)
    cypher = (
        f"MATCH (a:Service {{id: $from_id}})\n"
        f"MATCH (b:Service {{id: $to_id}})\n"
        f"MERGE (a)-[r:{rel_type}]->(b)\n"
        f"SET r.updated_at  = datetime(),\n"
        f"    r.protocol    = CASE WHEN $protocol IS NOT NULL THEN $protocol ELSE r.protocol END,\n"
        f"    r.timeout_ms  = CASE WHEN $timeout_ms IS NOT NULL THEN $timeout_ms ELSE r.timeout_ms END,\n"
        f"    r.criticality = CASE WHEN $criticality IS NOT NULL THEN $criticality ELSE r.criticality END,\n"
        f"    r.metadata    = CASE WHEN $metadata IS NOT NULL THEN $metadata ELSE r.metadata END\n"
        f"RETURN a.id AS from_id, b.id AS to_id, '{rel_type}' AS rel_type"
    )
    async with driver.session(database=database) as session:
        result = await session.run(
            cypher,
            from_id=from_id,
            to_id=to_id,
            protocol=protocol,
            timeout_ms=timeout_ms,
            criticality=criticality,
            metadata=json.dumps(metadata) if metadata is not None else None,
        )
        record = await result.single()
    if record is None:
        raise ValueError(
            f"link_service_dependency: MATCH found no nodes — verify from={from_id!r}, to={to_id!r} exist"
        )
    return dict(record)


async def link_service_datasource(
    driver: AsyncDriver,
    database: str,
    service_id: str,
    source_id: str,
    rel_type: str,
    access_pattern: str | None = None,
    metadata: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """MERGE a READS_FROM, WRITES_TO, or READS_WRITES edge from Service to DataSource.

    access_pattern is written only when provided; omitting it preserves the existing value.
    """
    if rel_type not in TOPOLOGY_LINK_TYPES:
        raise ValueError(f"rel_type {rel_type!r} not in TOPOLOGY_LINK_TYPES whitelist")
    if dry_run:
        return await _dry_run_check(
            driver, database, "Service", service_id, "DataSource", source_id
        )
    cypher = (
        f"MATCH (s:Service {{id: $service_id}})\n"
        f"MATCH (ds:DataSource {{id: $source_id}})\n"
        f"MERGE (s)-[r:{rel_type}]->(ds)\n"
        f"SET r.updated_at     = datetime(),\n"
        f"    r.access_pattern = CASE WHEN $access_pattern IS NOT NULL "
        f"THEN $access_pattern ELSE r.access_pattern END,\n"
        f"    r.metadata       = CASE WHEN $metadata IS NOT NULL THEN $metadata ELSE r.metadata END\n"
        f"RETURN s.id AS service_id, ds.id AS source_id, '{rel_type}' AS rel_type"
    )
    async with driver.session(database=database) as session:
        result = await session.run(
            cypher,
            service_id=service_id,
            source_id=source_id,
            access_pattern=access_pattern,
            metadata=json.dumps(metadata) if metadata is not None else None,
        )
        record = await result.single()
    if record is None:
        raise ValueError(
            f"link_service_datasource: MATCH found no nodes — verify service={service_id!r}, source={source_id!r} exist"
        )
    return dict(record)


async def link_service_mq(
    driver: AsyncDriver,
    database: str,
    service_id: str,
    queue_id: str,
    rel_type: str,
    event_type: str | None = None,
    metadata: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """MERGE a PUBLISHES_TO or SUBSCRIBES_TO edge from Service to MessageQueue.

    event_type is written only when provided; omitting it preserves the existing value.
    """
    if rel_type not in TOPOLOGY_LINK_TYPES:
        raise ValueError(f"rel_type {rel_type!r} not in TOPOLOGY_LINK_TYPES whitelist")
    if dry_run:
        return await _dry_run_check(
            driver, database, "Service", service_id, "MessageQueue", queue_id
        )
    cypher = (
        f"MATCH (s:Service {{id: $service_id}})\n"
        f"MATCH (mq:MessageQueue {{id: $queue_id}})\n"
        f"MERGE (s)-[r:{rel_type}]->(mq)\n"
        f"SET r.updated_at = datetime(),\n"
        f"    r.event_type = CASE WHEN $event_type IS NOT NULL THEN $event_type ELSE r.event_type END,\n"
        f"    r.metadata   = CASE WHEN $metadata IS NOT NULL THEN $metadata ELSE r.metadata END\n"
        f"RETURN s.id AS service_id, mq.id AS queue_id, '{rel_type}' AS rel_type"
    )
    async with driver.session(database=database) as session:
        result = await session.run(
            cypher,
            service_id=service_id,
            queue_id=queue_id,
            event_type=event_type,
            metadata=json.dumps(metadata) if metadata is not None else None,
        )
        record = await result.single()
    if record is None:
        raise ValueError(
            f"link_service_mq: MATCH found no nodes — verify service={service_id!r}, queue={queue_id!r} exist"
        )
    return dict(record)


async def link_feature_service(
    driver: AsyncDriver,
    database: str,
    feature_id: str,
    service_id: str,
    step_order: int,
    role: str,
    dry_run: bool = False,
) -> dict:
    """MERGE INVOLVES relationship from Feature to Service, setting step_order and role."""
    if dry_run:
        return await _dry_run_check(driver, database, "Feature", feature_id, "Service", service_id)
    async with driver.session(database=database) as session:
        result = await session.run(
            _query("LINK_FEATURE_SERVICE"),
            feature_id=feature_id,
            service_id=service_id,
            step_order=step_order,
            role=role,
        )
        record = await result.single()
    if record is None:
        raise ValueError(
            f"link_feature_service: MATCH found no nodes — verify feature={feature_id!r}, service={service_id!r} exist"
        )
    return dict(record)


async def link_service_context(
    driver: AsyncDriver,
    database: str,
    service_id: str,
    context_id: str,
    ownership: str,
    dry_run: bool = False,
) -> dict:
    """MERGE MEMBER_OF_CONTEXT relationship from Service to BoundedContext."""
    if dry_run:
        return await _dry_run_check(
            driver, database, "Service", service_id, "BoundedContext", context_id
        )
    async with driver.session(database=database) as session:
        result = await session.run(
            _query("LINK_SERVICE_CONTEXT"),
            service_id=service_id,
            context_id=context_id,
            ownership=ownership,
        )
        record = await result.single()
    if record is None:
        raise ValueError(
            f"link_service_context: MATCH found no nodes — verify service={service_id!r}, context={context_id!r} exist"
        )
    return dict(record)


async def link_topology_nodes(
    from_id: str,
    to_id: str,
    rel_type: str,
    driver: AsyncDriver,
    database: str,
    step_order: int | None = None,
    role: str | None = None,
    ownership: str | None = None,
    protocol: str | None = None,
    timeout_ms: int | None = None,
    criticality: str | None = None,
    access_pattern: str | None = None,
    event_type: str | None = None,
    metadata: dict | None = None,
    dry_run: bool = False,
) -> dict:
    """Unified topology link dispatch — validates node types and rel_type compatibility.

    Returns a dict with keys: from_id, to_id, rel_type, status, dry_run, error.
    status values: "linked" | "dry_run_ok" | "dry_run_node_missing" | "node_not_found" | "invalid_rel_type"
    Does NOT raise on validation failures — returns status dict instead.
    """
    # ── 1. Resolve node labels in a single round-trip ──────────────────────
    async with driver.session(database=database) as session:
        result = await session.run(
            "OPTIONAL MATCH (a {id: $from_id}) "
            "OPTIONAL MATCH (b {id: $to_id}) "
            "RETURN labels(a) AS from_labels, labels(b) AS to_labels",
            from_id=from_id,
            to_id=to_id,
        )
        record = await result.single()

    from_raw = set(record["from_labels"] or []) if record and record["from_labels"] else set()
    to_raw = set(record["to_labels"] or []) if record and record["to_labels"] else set()
    from_topo = from_raw & _TOPOLOGY_LABELS
    to_topo = to_raw & _TOPOLOGY_LABELS

    # ── 2. Node existence check ────────────────────────────────────────────
    from_label = next(iter(from_topo), None)
    to_label = next(iter(to_topo), None)
    if from_label is None or to_label is None:
        missing = []
        if from_label is None:
            missing.append(f"from_id={from_id!r}")
        if to_label is None:
            missing.append(f"to_id={to_id!r}")
        return {
            "from_id": from_id,
            "to_id": to_id,
            "rel_type": rel_type,
            "status": "node_not_found",
            "dry_run": dry_run,
            "error": f"Topology node(s) not found: {', '.join(missing)}",
        }

    # ── 3. Compatibility validation ────────────────────────────────────────
    allowed = _LINK_COMPATIBILITY.get((from_label, to_label), frozenset())
    if rel_type not in allowed:
        return {
            "from_id": from_id,
            "to_id": to_id,
            "rel_type": rel_type,
            "status": "invalid_rel_type",
            "dry_run": dry_run,
            "error": (
                f"{rel_type!r} is not valid for {from_label}→{to_label}. "
                f"Allowed: {', '.join(sorted(allowed))}"
            ),
        }

    # ── 4. Dispatch to existing private link functions ─────────────────────
    pair = (from_label, to_label)
    if pair == ("Service", "Service"):
        return await link_service_dependency(
            driver=driver,
            database=database,
            from_id=from_id,
            to_id=to_id,
            rel_type=rel_type,
            protocol=protocol,
            timeout_ms=timeout_ms,
            criticality=criticality,
            metadata=metadata,
            dry_run=dry_run,
        )
    if pair == ("Service", "DataSource"):
        return await link_service_datasource(
            driver=driver,
            database=database,
            service_id=from_id,
            source_id=to_id,
            rel_type=rel_type,
            access_pattern=access_pattern,
            metadata=metadata,
            dry_run=dry_run,
        )
    if pair == ("Service", "MessageQueue"):
        return await link_service_mq(
            driver=driver,
            database=database,
            service_id=from_id,
            queue_id=to_id,
            rel_type=rel_type,
            event_type=event_type,
            metadata=metadata,
            dry_run=dry_run,
        )
    if pair == ("Feature", "Service"):
        return await link_feature_service(
            driver=driver,
            database=database,
            feature_id=from_id,
            service_id=to_id,
            step_order=step_order if step_order is not None else 1,
            role=role or "participant",
            dry_run=dry_run,
        )
    # ("Service", "BoundedContext")
    return await link_service_context(
        driver=driver,
        database=database,
        service_id=from_id,
        context_id=to_id,
        ownership=ownership or "owner",
        dry_run=dry_run,
    )


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
