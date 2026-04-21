"""
TopologyWriteEngine — workspace scope gate and governance gate for topology writes.

T4.1 | ADR-TOPO-001

All mutating functions check validate_workspace() before touching the graph.
validate_workspace() returns ScopeState.unresolved (not uncertain) for a missing
workspace — there is no auto-creation path, so callers must register the workspace
via the federation engine first.

batch_upsert_shared_infrastructure consumes ONE governance token for N nodes
(accepted weaker guarantee, documented in ADR-TOPO-001 §Governance).

Read queries (get_service_dependencies, get_feature_workflow) bypass scope and
governance gates — they are always allowed.

Retries: 1 attempt on ServiceUnavailable, same policy as write.py FR-52.
"""

from __future__ import annotations

import asyncio
import logging

from neo4j import AsyncDriver
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from graphbase_memories.config import settings
from graphbase_memories.domain.enums import ScopeState
from graphbase_memories.engines import scope as scope_engine
from graphbase_memories.graph.repositories import token_repo, topology_repo
from graphbase_memories.graph.repositories.topology_repo import LinkEdgeProps
from graphbase_memories.mcp.schemas.topology import (
    BatchInfraResult,
    BatchUpsertInfraInput,
    BoundedContextItem,
    DataSourceItem,
    FeatureItem,
    FeatureWorkflowResult,
    FeatureWorkflowStep,
    GetFeatureWorkflowInput,
    GetServiceDependenciesInput,
    LinkFeatureServiceInput,
    LinkServiceContextInput,
    LinkServiceDataSourceInput,
    LinkServiceDependencyInput,
    LinkServiceMQInput,
    LinkTopologyNodesInput,
    MessageQueueItem,
    RegisterServiceInput,
    ServiceDependencyItem,
    ServiceDependencyResult,
    ServiceResult,
    TopologyLinkResult,
)

logger = logging.getLogger(__name__)


# ── Scope gate ───────────────────────────────────────────────────────────────


async def _require_workspace(workspace_id: str, driver: AsyncDriver, database: str) -> None:
    """Raise ValueError if the workspace does not exist in the graph."""
    state = await scope_engine.validate_workspace(workspace_id, driver, database)
    if state == ScopeState.unresolved:
        raise ValueError(
            f"Workspace '{workspace_id}' not found. "
            "Register the workspace first via register_project() or the federation engine."
        )


# ── Retry wrapper ────────────────────────────────────────────────────────────


async def _with_retry(fn, **kwargs):
    """1 retry on ServiceUnavailable — mirrors FR-52 from write.py."""
    for attempt in range(settings.write_max_retries + 1):
        try:
            return await fn(**kwargs)
        except ServiceUnavailable:
            if attempt < settings.write_max_retries:
                await asyncio.sleep(0.5)
                continue
            raise
        except Neo4jError:
            logger.exception("Topology write failed (attempt %d)", attempt + 1)
            raise


# ── Service ──────────────────────────────────────────────────────────────────


async def register_service(
    inp: RegisterServiceInput,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> ServiceResult:
    await _require_workspace(inp.workspace_id, driver, database)
    node = await _with_retry(
        topology_repo.upsert_service,
        driver=driver,
        database=database,
        service_id=inp.service_id,
        name=inp.name,
        workspace_id=inp.workspace_id,
        display_name=inp.display_name,
        service_type=inp.service_type.value if inp.service_type else None,
        bounded_context=inp.bounded_context,
        owner_team=inp.owner_team,
        health_status=inp.health_status.value,
        env=inp.env,
        version=inp.version,
        sla=inp.sla,
        docs_url=inp.docs_url,
        tags=inp.tags,
    )
    return ServiceResult(
        service_id=node.id,
        name=node.name,
        workspace_id=node.workspace_id,
        display_name=node.display_name,
        service_type=node.service_type,
        bounded_context=node.bounded_context,
        health_status=node.health_status or "unknown",
        status=node.status,
        tags=node.tags,
    )


# ── Relationship operations ───────────────────────────────────────────────────


async def link_service_dependency(
    inp: LinkServiceDependencyInput,
    workspace_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> TopologyLinkResult:
    await _require_workspace(workspace_id, driver, database)
    try:
        record = await _with_retry(
            topology_repo.link_service_dependency,
            driver=driver,
            database=database,
            from_id=inp.from_service_id,
            to_id=inp.to_service_id,
            rel_type=inp.rel_type.value,
            protocol=inp.protocol,
            timeout_ms=inp.timeout_ms,
            criticality=inp.criticality,
            metadata=inp.metadata,
            dry_run=inp.dry_run,
        )
    except ValueError:
        if inp.dry_run:
            return TopologyLinkResult(
                from_id=inp.from_service_id,
                to_id=inp.to_service_id,
                rel_type=inp.rel_type.value,
                status="dry_run_node_missing",
                dry_run=True,
            )
        raise
    return TopologyLinkResult(
        from_id=record.get("from_id", inp.from_service_id),
        to_id=record.get("to_id", inp.to_service_id),
        rel_type=record.get("rel_type", inp.rel_type.value),
        status=record.get("status", "linked"),
        dry_run=inp.dry_run,
    )


async def link_service_datasource(
    inp: LinkServiceDataSourceInput,
    workspace_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> TopologyLinkResult:
    await _require_workspace(workspace_id, driver, database)
    try:
        record = await _with_retry(
            topology_repo.link_service_datasource,
            driver=driver,
            database=database,
            service_id=inp.service_id,
            source_id=inp.source_id,
            rel_type=inp.rel_type.value,
            access_pattern=inp.access_pattern,
            metadata=inp.metadata,
            dry_run=inp.dry_run,
        )
    except ValueError:
        if inp.dry_run:
            return TopologyLinkResult(
                from_id=inp.service_id,
                to_id=inp.source_id,
                rel_type=inp.rel_type.value,
                status="dry_run_node_missing",
                dry_run=True,
            )
        raise
    return TopologyLinkResult(
        from_id=record.get("service_id", inp.service_id),
        to_id=record.get("source_id", inp.source_id),
        rel_type=record.get("rel_type", inp.rel_type.value),
        status=record.get("status", "linked"),
        dry_run=inp.dry_run,
    )


async def link_service_mq(
    inp: LinkServiceMQInput,
    workspace_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> TopologyLinkResult:
    await _require_workspace(workspace_id, driver, database)
    try:
        record = await _with_retry(
            topology_repo.link_service_mq,
            driver=driver,
            database=database,
            service_id=inp.service_id,
            queue_id=inp.queue_id,
            rel_type=inp.rel_type.value,
            event_type=inp.event_type,
            metadata=inp.metadata,
            dry_run=inp.dry_run,
        )
    except ValueError:
        if inp.dry_run:
            return TopologyLinkResult(
                from_id=inp.service_id,
                to_id=inp.queue_id,
                rel_type=inp.rel_type.value,
                status="dry_run_node_missing",
                dry_run=True,
            )
        raise
    return TopologyLinkResult(
        from_id=record.get("service_id", inp.service_id),
        to_id=record.get("queue_id", inp.queue_id),
        rel_type=record.get("rel_type", inp.rel_type.value),
        status=record.get("status", "linked"),
        dry_run=inp.dry_run,
    )


async def link_feature_service(
    inp: LinkFeatureServiceInput,
    workspace_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> TopologyLinkResult:
    await _require_workspace(workspace_id, driver, database)
    try:
        record = await _with_retry(
            topology_repo.link_feature_service,
            driver=driver,
            database=database,
            feature_id=inp.feature_id,
            service_id=inp.service_id,
            step_order=inp.step_order,
            role=inp.role,
            dry_run=inp.dry_run,
        )
    except ValueError:
        if inp.dry_run:
            return TopologyLinkResult(
                from_id=inp.feature_id,
                to_id=inp.service_id,
                rel_type="INVOLVES",
                status="dry_run_node_missing",
                dry_run=True,
            )
        raise
    return TopologyLinkResult(
        from_id=record.get("feature_id", inp.feature_id),
        to_id=record.get("service_id", inp.service_id),
        rel_type="INVOLVES",
        status=record.get("status", "linked"),
        dry_run=inp.dry_run,
    )


async def link_service_context(
    inp: LinkServiceContextInput,
    workspace_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> TopologyLinkResult:
    await _require_workspace(workspace_id, driver, database)
    try:
        record = await _with_retry(
            topology_repo.link_service_context,
            driver=driver,
            database=database,
            service_id=inp.service_id,
            context_id=inp.context_id,
            ownership=inp.ownership.value,
            dry_run=inp.dry_run,
        )
    except ValueError:
        if inp.dry_run:
            return TopologyLinkResult(
                from_id=inp.service_id,
                to_id=inp.context_id,
                rel_type="MEMBER_OF_CONTEXT",
                status="dry_run_node_missing",
                dry_run=True,
            )
        raise
    return TopologyLinkResult(
        from_id=record.get("service_id", inp.service_id),
        to_id=record.get("context_id", inp.context_id),
        rel_type="MEMBER_OF_CONTEXT",
        status=record.get("status", "linked"),
        dry_run=inp.dry_run,
    )


# ── Batch infra ───────────────────────────────────────────────────────────────


async def link_topology_nodes(
    inp: LinkTopologyNodesInput,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> TopologyLinkResult:
    """Dispatch unified topology link to the correct repo function via label-based validation.

    Returns TopologyLinkResult directly — error statuses (node_not_found, invalid_rel_type)
    are encoded in .status + .error fields rather than raised as exceptions.
    """
    record = await topology_repo.link_topology_nodes(
        from_id=inp.from_id,
        to_id=inp.to_id,
        rel_type=inp.rel_type.value,
        driver=driver,
        database=database,
        edge_props=LinkEdgeProps(
            step_order=inp.step_order,
            role=inp.role,
            ownership=inp.ownership.value if inp.ownership else None,
            protocol=inp.protocol,
            timeout_ms=inp.timeout_ms,
            criticality=inp.criticality,
            access_pattern=inp.access_pattern,
            event_type=inp.event_type,
            metadata=inp.metadata or {},
        ),
        dry_run=inp.dry_run,
    )
    return TopologyLinkResult(
        from_id=record.get("from_id", inp.from_id),
        to_id=record.get("to_id", inp.to_id),
        rel_type=record.get("rel_type", inp.rel_type.value),
        status=record.get("status", "linked"),
        dry_run=record.get("dry_run", inp.dry_run),
        error=record.get("error"),
    )


async def batch_upsert_shared_infrastructure(
    inp: BatchUpsertInfraInput,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> BatchInfraResult:
    """
    Upsert N heterogeneous infrastructure nodes in a single authorized batch.
    Single-node registration requires no governance token.
    Multi-node (N>1) requires a governance token (ADR-TOPO-001 §Governance).
    """
    await _require_workspace(inp.workspace_id, driver, database)

    if inp.governance_token is not None:
        valid = await token_repo.validate_and_consume(inp.governance_token, driver, database)
        if not valid:
            raise ValueError(
                "Governance token is invalid, expired, or already used. "
                "Call request_global_write_approval() to obtain a fresh token."
            )

    upserted = 0
    errors: list[str] = []

    for item in inp.nodes:
        try:
            if isinstance(item, DataSourceItem):
                await topology_repo.upsert_datasource(
                    driver=driver,
                    database=database,
                    source_id=item.source_id,
                    source_type=item.source_type.value,
                    host=item.host,
                    workspace_id=inp.workspace_id,
                    owner_team=item.owner_team,
                    health_status=item.health_status.value,
                    version=item.version,
                    tags=item.tags,
                )
            elif isinstance(item, MessageQueueItem):
                await topology_repo.upsert_message_queue(
                    driver=driver,
                    database=database,
                    queue_id=item.queue_id,
                    queue_type=item.queue_type.value,
                    topic_or_exchange=item.topic_or_exchange,
                    workspace_id=inp.workspace_id,
                    owner_team=item.owner_team,
                    schema_version=item.schema_version,
                    tags=item.tags,
                )
            elif isinstance(item, FeatureItem):
                await topology_repo.upsert_feature(
                    driver=driver,
                    database=database,
                    feature_id=item.feature_id,
                    name=item.name,
                    workspace_id=inp.workspace_id,
                    workflow_order=item.workflow_order,
                    owner_team=item.owner_team,
                    tags=item.tags,
                )
            elif isinstance(item, BoundedContextItem):
                await topology_repo.upsert_bounded_context(
                    driver=driver,
                    database=database,
                    context_id=item.context_id,
                    name=item.name,
                    domain=item.domain,
                    workspace_id=inp.workspace_id,
                    tags=item.tags,
                )
            upserted += 1
        except (Neo4jError, KeyError, ValueError) as exc:
            logger.exception("Batch upsert failed for item %s", getattr(item, "node_type", "?"))
            errors.append(str(exc))

    return BatchInfraResult(
        workspace_id=inp.workspace_id,
        upserted=upserted,
        failed=len(errors),
        errors=errors,
    )


# ── Read queries (no scope/governance gate) ───────────────────────────────────


async def get_service_dependencies(
    inp: GetServiceDependenciesInput,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> ServiceDependencyResult:
    rows = await topology_repo.get_service_dependencies(
        driver=driver,
        database=database,
        service_id=inp.service_id,
        direction=inp.direction.value,
        depth=inp.depth,
        limit=inp.limit,
    )
    deps = [
        ServiceDependencyItem(
            service_id=r.get("service_id", ""),
            name=r.get("name", ""),
            service_type=r.get("service_type") or None,
            health_status=r.get("health_status") or None,
            bounded_context=r.get("bounded_context") or None,
            depth=int(r.get("depth", 0)),
        )
        for r in rows
    ]
    return ServiceDependencyResult(
        service_id=inp.service_id,
        direction=inp.direction.value,
        dependencies=deps,
    )


async def get_feature_workflow(
    inp: GetFeatureWorkflowInput,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> FeatureWorkflowResult:
    rows = await topology_repo.get_feature_workflow(
        driver=driver,
        database=database,
        feature_id=inp.feature_id,
    )
    steps = [
        FeatureWorkflowStep(
            service_id=r.get("service_id", ""),
            name=r.get("name", ""),
            service_type=r.get("service_type") or None,
            health_status=r.get("health_status") or None,
            bounded_context=r.get("bounded_context") or None,
            step_order=int(r.get("step_order", 0)),
            role=r.get("role", ""),
        )
        for r in rows
    ]
    return FeatureWorkflowResult(feature_id=inp.feature_id, steps=steps)
