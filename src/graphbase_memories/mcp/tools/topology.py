"""
Topology MCP tools — register and link service topology nodes.

T5.1 | ADR-TOPO-001

Provides 13 tools covering:
  - Node registration: register_service, register_datasource, register_message_queue,
    register_feature, register_bounded_context
  - Link operations: link_service_dependency, link_service_datasource,
    link_service_mq, link_feature_service, link_service_context
  - Batch ingestion: batch_upsert_shared_infrastructure
  - Read/traversal: get_service_dependencies, get_feature_workflow

All write tools require workspace_id to be a registered :Workspace node.
batch_upsert_shared_infrastructure additionally requires a governance token
(one token authorizes the full batch — see ADR-TOPO-001).
"""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import topology_write as topo_engine
from graphbase_memories.mcp.schemas.topology import (
    BatchInfraResult,
    BatchUpsertInfraInput,
    BoundedContextResult,
    DataSourceResult,
    FeatureResult,
    FeatureWorkflowResult,
    GetFeatureWorkflowInput,
    GetServiceDependenciesInput,
    LinkFeatureServiceInput,
    LinkServiceContextInput,
    LinkServiceDataSourceInput,
    LinkServiceDependencyInput,
    LinkServiceMQInput,
    MessageQueueResult,
    RegisterBoundedContextInput,
    RegisterDataSourceInput,
    RegisterFeatureInput,
    RegisterMessageQueueInput,
    RegisterServiceInput,
    ServiceDependencyResult,
    ServiceResult,
    TopologyLinkResult,
)
from graphbase_memories.mcp.server import mcp

# ── Node registration ─────────────────────────────────────────────────────────


@mcp.tool()
async def register_service(ctx: Context, inp: RegisterServiceInput) -> ServiceResult:
    """
    Register or update a service node in the topology graph.

    Creates a dual-label :Project:Service node so the service is also queryable
    as a memory scope anchor (scope_engine resolves :Project by id).
    Safe to call repeatedly — uses MERGE (idempotent).

    workspace_id must match an existing :Workspace node; call register_project()
    or create the workspace via the federation engine first.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.register_service(inp, driver, settings.neo4j_database)


@mcp.tool()
async def register_datasource(ctx: Context, inp: RegisterDataSourceInput) -> DataSourceResult:
    """
    Register or update a shared data source node (database, cache, blob storage).

    Creates a :DataSource node linked to the specified workspace via PART_OF.
    Safe to call repeatedly — uses MERGE (idempotent).

    source_type values: postgresql, mysql, mongodb, redis, elasticsearch, s3, other.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.register_datasource(inp, driver, settings.neo4j_database)


@mcp.tool()
async def register_message_queue(
    ctx: Context, inp: RegisterMessageQueueInput
) -> MessageQueueResult:
    """
    Register or update an async messaging channel (Kafka topic, RabbitMQ exchange, SQS queue).

    Creates a :MessageQueue node linked to the specified workspace via PART_OF.
    Safe to call repeatedly — uses MERGE (idempotent).

    queue_type values: kafka, rabbitmq, sqs, pubsub, other.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.register_message_queue(inp, driver, settings.neo4j_database)


@mcp.tool()
async def register_feature(ctx: Context, inp: RegisterFeatureInput) -> FeatureResult:
    """
    Register or update a user-facing product feature that spans multiple services.

    Creates a :Feature node linked to the workspace via HAS_FEATURE.
    Services participate in a feature via link_feature_service() with an ordered
    step_order to reconstruct the workflow sequence.

    Safe to call repeatedly — uses MERGE (idempotent).
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.register_feature(inp, driver, settings.neo4j_database)


@mcp.tool()
async def register_bounded_context(
    ctx: Context, inp: RegisterBoundedContextInput
) -> BoundedContextResult:
    """
    Register or update a DDD bounded context that groups related services.

    Creates a :BoundedContext node linked to the workspace via PART_OF.
    Services are associated with a bounded context via link_service_context().

    Safe to call repeatedly — uses MERGE (idempotent).
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.register_bounded_context(inp, driver, settings.neo4j_database)


# ── Link operations ───────────────────────────────────────────────────────────


@mcp.tool()
async def link_service_dependency(
    ctx: Context,
    inp: LinkServiceDependencyInput,
    workspace_id: str,
) -> TopologyLinkResult:
    """
    Create a dependency edge between two services.

    rel_type:
      CALLS_DOWNSTREAM — from_service calls to_service (caller → callee)
      CALLS_UPSTREAM   — from_service calls to_service in reverse direction

    Both services must already be registered via register_service().
    Duplicate links are silently merged (MERGE is idempotent).
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.link_service_dependency(
        inp, workspace_id, driver, settings.neo4j_database
    )


@mcp.tool()
async def link_service_datasource(
    ctx: Context,
    inp: LinkServiceDataSourceInput,
    workspace_id: str,
) -> TopologyLinkResult:
    """
    Link a service to a data source it reads from or writes to.

    rel_type: READS_FROM, WRITES_TO, or READS_WRITES.
    Both nodes must already be registered.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.link_service_datasource(
        inp, workspace_id, driver, settings.neo4j_database
    )


@mcp.tool()
async def link_service_mq(
    ctx: Context,
    inp: LinkServiceMQInput,
    workspace_id: str,
) -> TopologyLinkResult:
    """
    Link a service to a message queue it publishes to or subscribes from.

    rel_type: PUBLISHES_TO or SUBSCRIBES_TO.
    Both nodes must already be registered.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.link_service_mq(inp, workspace_id, driver, settings.neo4j_database)


@mcp.tool()
async def link_feature_service(
    ctx: Context,
    inp: LinkFeatureServiceInput,
    workspace_id: str,
) -> TopologyLinkResult:
    """
    Associate a service with a feature workflow step via an INVOLVES edge.

    step_order defines the sequence position (1-based). Calling get_feature_workflow()
    returns all services ordered by step_order to reconstruct the full flow.
    role describes this service's responsibility in the feature (e.g. "orchestrator",
    "data-provider", "notification-sender").

    Both feature and service must already be registered.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.link_feature_service(
        inp, workspace_id, driver, settings.neo4j_database
    )


@mcp.tool()
async def link_service_context(
    ctx: Context,
    inp: LinkServiceContextInput,
    workspace_id: str,
) -> TopologyLinkResult:
    """
    Associate a service with a bounded context via MEMBER_OF_CONTEXT.

    ownership: owner (primary team), contributor, or consumer.
    Both service and bounded_context must already be registered.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.link_service_context(
        inp, workspace_id, driver, settings.neo4j_database
    )


# ── Batch ingestion ───────────────────────────────────────────────────────────


@mcp.tool()
async def batch_upsert_shared_infrastructure(
    ctx: Context, inp: BatchUpsertInfraInput
) -> BatchInfraResult:
    """
    Upsert multiple shared infrastructure nodes (DataSource, MessageQueue,
    Feature, BoundedContext) in a single authorized operation.

    Requires a governance token (obtain via request_global_write_approval).
    ONE token authorizes the full batch — this is a weaker guarantee than
    per-node tokens, accepted to handle high-cardinality infrastructure
    (e.g. 50+ Kafka topics). See ADR-TOPO-001 §Governance.

    Service nodes are NOT supported in batch — use register_service() per service
    to ensure proper :Project dual-label creation for scope resolution.

    Returns upserted count, failed count, and per-item error messages.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.batch_upsert_shared_infrastructure(
        inp, driver, settings.neo4j_database
    )


# ── Read / traversal ──────────────────────────────────────────────────────────


@mcp.tool()
async def get_service_dependencies(
    ctx: Context, inp: GetServiceDependenciesInput
) -> ServiceDependencyResult:
    """
    Traverse the service dependency graph from a starting service.

    direction:
      downstream — services that this service calls (default)
      upstream   — services that call this service
      both       — undirected traversal (both CALLS_DOWNSTREAM and CALLS_UPSTREAM)

    depth: max hops (1-6, default 2). Higher values may return large result sets.
    limit: max nodes returned (1-200, default 50).

    Returns each reachable service with its hop depth from the origin.
    No governance gate — read-only operation.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.get_service_dependencies(inp, driver, settings.neo4j_database)


@mcp.tool()
async def get_feature_workflow(ctx: Context, inp: GetFeatureWorkflowInput) -> FeatureWorkflowResult:
    """
    Return all services involved in a feature, ordered by workflow step.

    Each step includes service metadata and the role that service plays
    in the feature flow (set via link_feature_service).

    No governance gate — read-only operation.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.get_feature_workflow(inp, driver, settings.neo4j_database)
