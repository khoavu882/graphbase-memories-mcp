"""
Pydantic V2 schemas for topology MCP tool inputs and results.

T4.2 | ADR-TOPO-001

SharedInfraNodeSchema uses a discriminated union on `node_type` so that
batch_upsert_shared_infrastructure can accept heterogeneous node lists in a
single tool call — see PRD §5 batch ingestion requirement.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from graphbase_memories.mcp.schemas.enums import (
    DataSourceType,
    DependencyDirection,
    MessageQueueType,
    ServiceHealthStatus,
    ServiceOwnership,
    ServiceType,
    TopologyLinkType,
)

# ── Service ──────────────────────────────────────────────────────────────────


class RegisterServiceInput(BaseModel):
    service_id: str = Field(..., description="Stable unique identifier for the service")
    name: str = Field(..., description="Canonical short name (slug)")
    workspace_id: str = Field(..., description="Workspace this service belongs to")
    display_name: str | None = Field(None, description="Human-readable label")
    service_type: ServiceType | None = Field(None, description="Service classification")
    bounded_context: str | None = Field(None, description="DDD bounded context name")
    owner_team: str | None = Field(None, description="Team responsible for this service")
    health_status: ServiceHealthStatus = Field(ServiceHealthStatus.unknown)
    env: str | None = Field(None, description="Deployment environment (prod, staging, etc.)")
    version: str | None = Field(None, description="Current deployed version")
    sla: str | None = Field(None, description="SLA tier or target (e.g. 99.9%)")
    docs_url: str | None = Field(None, description="Link to service documentation")
    tags: list[str] = Field(default_factory=list)


class ServiceResult(BaseModel):
    service_id: str
    name: str
    workspace_id: str
    display_name: str | None
    service_type: str | None
    bounded_context: str | None
    health_status: str
    status: str
    tags: list[str]


# ── Relationship inputs ───────────────────────────────────────────────────────


class LinkServiceDependencyInput(BaseModel):
    from_service_id: str
    to_service_id: str
    rel_type: TopologyLinkType = Field(
        ...,
        description="CALLS_DOWNSTREAM (caller→callee) or CALLS_UPSTREAM (callee→caller)",
    )
    protocol: str | None = Field(None, description="Transport protocol (REST, gRPC, kafka, etc.)")
    timeout_ms: int | None = Field(None, description="Call timeout in milliseconds", ge=1)
    criticality: Literal["high", "medium", "low"] | None = Field(
        None, description="Business criticality of this dependency"
    )
    metadata: dict[str, str] | None = Field(None, description="Arbitrary string key/value metadata")
    dry_run: bool = Field(
        False, description="If true, validates endpoint nodes exist without writing"
    )


class LinkServiceDataSourceInput(BaseModel):
    service_id: str
    source_id: str
    rel_type: TopologyLinkType = Field(..., description="READS_FROM, WRITES_TO, or READS_WRITES")
    access_pattern: str | None = Field(
        None, description="Access pattern (e.g. cache-aside, read-heavy, write-heavy)"
    )
    metadata: dict[str, str] | None = Field(None, description="Arbitrary string key/value metadata")
    dry_run: bool = Field(
        False, description="If true, validates endpoint nodes exist without writing"
    )


class LinkServiceMQInput(BaseModel):
    service_id: str
    queue_id: str
    rel_type: TopologyLinkType = Field(..., description="PUBLISHES_TO or SUBSCRIBES_TO")
    event_type: str | None = Field(
        None, description="Event/message type name published or consumed"
    )
    metadata: dict[str, str] | None = Field(None, description="Arbitrary string key/value metadata")
    dry_run: bool = Field(
        False, description="If true, validates endpoint nodes exist without writing"
    )


class LinkFeatureServiceInput(BaseModel):
    feature_id: str
    service_id: str
    step_order: int = Field(..., description="Position in the feature workflow (1-based)")
    role: str = Field(..., description="Role of this service in the feature (e.g. orchestrator)")
    dry_run: bool = Field(
        False, description="If true, validates endpoint nodes exist without writing"
    )


class LinkServiceContextInput(BaseModel):
    service_id: str
    context_id: str
    ownership: ServiceOwnership = Field(ServiceOwnership.owner)
    dry_run: bool = Field(
        False, description="If true, validates endpoint nodes exist without writing"
    )


class LinkTopologyNodesInput(BaseModel):
    """Unified link input for link_topology_nodes — replaces 5 specialized link tools."""

    from_id: str = Field(..., description="ID of the source topology node")
    to_id: str = Field(..., description="ID of the target topology node")
    rel_type: TopologyLinkType = Field(..., description="Relationship type (validated against node label pair)")
    workspace_id: str = Field(..., description="Workspace both nodes belong to")
    # INVOLVES-specific
    step_order: int | None = Field(None, description="Step position for INVOLVES edges (1-based)")
    role: str | None = Field(None, description="Service role for INVOLVES edges (e.g. orchestrator)")
    # MEMBER_OF_CONTEXT-specific
    ownership: ServiceOwnership | None = Field(None, description="Ownership type for MEMBER_OF_CONTEXT edges")
    # Service dependency-specific
    protocol: str | None = Field(None, description="Transport protocol (REST, gRPC, kafka, etc.)")
    timeout_ms: int | None = Field(None, ge=1, description="Call timeout in milliseconds")
    criticality: Literal["high", "medium", "low"] | None = Field(None, description="Business criticality")
    # DataSource access-specific
    access_pattern: str | None = Field(None, description="Access pattern (e.g. cache-aside, read-heavy)")
    # MessageQueue-specific
    event_type: str | None = Field(None, description="Event/message type name published or consumed")
    metadata: dict[str, str] | None = Field(None, description="Arbitrary string key/value metadata")
    dry_run: bool = Field(False, description="If true, validates nodes exist without writing")


class TopologyLinkResult(BaseModel):
    from_id: str
    to_id: str
    rel_type: str
    status: Literal[
        "linked",
        "dry_run_ok",
        "dry_run_node_missing",
        "node_not_found",
        "invalid_rel_type",
    ] = "linked"
    dry_run: bool = False
    error: str | None = None  # populated on node_not_found / invalid_rel_type


# ── Traversal inputs / results ────────────────────────────────────────────────


class GetServiceDependenciesInput(BaseModel):
    service_id: str
    direction: DependencyDirection = Field(DependencyDirection.downstream)
    depth: int = Field(2, ge=1, le=6, description="Max traversal hops (1-6)")
    limit: int = Field(50, ge=1, le=200)


class ServiceDependencyItem(BaseModel):
    service_id: str
    name: str
    service_type: str | None
    health_status: str | None
    bounded_context: str | None
    depth: int


class ServiceDependencyResult(BaseModel):
    service_id: str
    direction: str
    dependencies: list[ServiceDependencyItem]


class GetFeatureWorkflowInput(BaseModel):
    feature_id: str


class FeatureWorkflowStep(BaseModel):
    service_id: str
    name: str
    service_type: str | None
    health_status: str | None
    bounded_context: str | None
    step_order: int
    role: str


class FeatureWorkflowResult(BaseModel):
    feature_id: str
    steps: list[FeatureWorkflowStep]


# ── Batch infra ───────────────────────────────────────────────────────────────


class DataSourceItem(BaseModel):
    node_type: Literal["datasource"] = "datasource"
    source_id: str
    source_type: DataSourceType
    host: str | None = None
    owner_team: str | None = None
    health_status: ServiceHealthStatus = ServiceHealthStatus.unknown
    version: str | None = None
    tags: list[str] = Field(default_factory=list)


class MessageQueueItem(BaseModel):
    node_type: Literal["messagequeue"] = "messagequeue"
    queue_id: str
    queue_type: MessageQueueType
    topic_or_exchange: str | None = None
    owner_team: str | None = None
    schema_version: str | None = None
    tags: list[str] = Field(default_factory=list)


class FeatureItem(BaseModel):
    node_type: Literal["feature"] = "feature"
    feature_id: str
    name: str
    workflow_order: int = 0
    owner_team: str | None = None
    tags: list[str] = Field(default_factory=list)


class BoundedContextItem(BaseModel):
    node_type: Literal["boundedcontext"] = "boundedcontext"
    context_id: str
    name: str
    domain: str | None = None
    tags: list[str] = Field(default_factory=list)


SharedInfraNodeSchema = Annotated[
    DataSourceItem | MessageQueueItem | FeatureItem | BoundedContextItem,
    Field(discriminator="node_type"),
]


class BatchUpsertInfraInput(BaseModel):
    workspace_id: str = Field(..., description="Workspace all nodes belong to")
    governance_token: str | None = Field(
        None,
        description=(
            "Required when registering more than 1 node. "
            "Optional for single-node registration. "
            "Obtain via request_global_write_approval()."
        ),
    )
    nodes: list[SharedInfraNodeSchema] = Field(
        ..., min_length=1, description="Heterogeneous list of infra nodes to upsert"
    )

    @model_validator(mode="after")
    def _token_required_for_multi(self) -> BatchUpsertInfraInput:
        if len(self.nodes) > 1 and not self.governance_token:
            raise ValueError(
                "governance_token required for multi-node batch. "
                "Call request_global_write_approval() first."
            )
        return self


class BatchInfraResult(BaseModel):
    workspace_id: str
    upserted: int
    failed: int
    errors: list[str] = Field(default_factory=list)
