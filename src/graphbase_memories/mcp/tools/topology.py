"""
Topology MCP tools — register and link service topology nodes.

T5.1 | ADR-TOPO-001

Provides 5 tools:
  - Node registration: register_service
  - Link operations: link_topology_nodes (unified — replaces 5 specialized link tools)
  - Batch ingestion: batch_upsert_shared_infrastructure
  - Read/traversal: get_service_dependencies, get_feature_workflow

All write tools require workspace_id to be a registered :Workspace node.
batch_upsert_shared_infrastructure requires a governance token only when
registering more than 1 node — single-node registration is token-free.
"""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import topology_write as topo_engine
from graphbase_memories.mcp.schemas.topology import (
    BatchInfraResult,
    BatchUpsertInfraInput,
    FeatureWorkflowResult,
    GetFeatureWorkflowInput,
    GetServiceDependenciesInput,
    LinkTopologyNodesInput,
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

    workspace_id must match an existing :Workspace node; call register_federated_service()
    or create the workspace via the federation engine first.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.register_service(inp, driver, settings.neo4j_database)


# ── Link operations ───────────────────────────────────────────────────────────


@mcp.tool()
async def link_topology_nodes(
    ctx: Context,
    inp: LinkTopologyNodesInput,
) -> TopologyLinkResult:
    """
    Create a typed relationship between any two topology nodes.

    The engine validates that rel_type is compatible with the from/to node types.
    Invalid combinations return status="invalid_rel_type" with allowed values listed.
    Missing nodes return status="node_not_found" (no exception raised).

    rel_type compatibility:
      Service → Service:        CALLS_DOWNSTREAM, CALLS_UPSTREAM
      Service → DataSource:     READS_FROM, WRITES_TO, READS_WRITES
      Service → MessageQueue:   PUBLISHES_TO, SUBSCRIBES_TO
      Feature → Service:        INVOLVES (use step_order + role)
      Service → BoundedContext: MEMBER_OF_CONTEXT (use ownership)

    All nodes must be registered before linking. Duplicate links are silently merged (MERGE).
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.link_topology_nodes(inp, driver, settings.neo4j_database)


# ── Batch ingestion ───────────────────────────────────────────────────────────


@mcp.tool()
async def batch_upsert_shared_infrastructure(
    ctx: Context, inp: BatchUpsertInfraInput
) -> BatchInfraResult:
    """
    Upsert multiple shared infrastructure nodes (DataSource, MessageQueue,
    Feature, BoundedContext) in a single operation.

    Single-node registration requires NO governance token.
    Multi-node (N>1) requires a governance token (obtain via request_global_write_approval).
    ONE token authorizes the full batch — this is a weaker guarantee than per-node tokens,
    accepted to handle high-cardinality infrastructure (e.g. 50+ Kafka topics).
    See ADR-TOPO-001 §Governance.

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
    in the feature flow (set via link_topology_nodes with rel_type=INVOLVES).

    No governance gate — read-only operation.
    """
    driver = ctx.lifespan_context["driver"]
    return await topo_engine.get_feature_workflow(inp, driver, settings.neo4j_database)
