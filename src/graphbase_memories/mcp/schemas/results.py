"""Result schemas for all MCP tool responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from graphbase_memories.mcp.schemas.enums import (
    AnalysisMode,
    DedupOutcome,
    RetrievalStatus,
    SaveStatus,
    ScopeState,
)


class SaveResult(BaseModel):
    status: SaveStatus
    artifact_id: str | None = None
    dedup_outcome: DedupOutcome | None = None
    message: str | None = None


class BatchSaveResult(BaseModel):
    session: SaveResult
    decisions: list[SaveResult] = []
    patterns: list[SaveResult] = []
    overall: SaveStatus  # partial if any sub-result failed


class ContextBundle(BaseModel):
    """M-4: hygiene_due surfaces overdue hygiene passively during retrieval."""

    items: list[dict]
    retrieval_status: RetrievalStatus
    scope_state: ScopeState
    conflicts_found: bool = False
    hygiene_due: bool = False
    truncated_scopes: list[str] = []  # scopes where result count hit the configured limit
    next_step: str | None = None


class SaveStatusSummary(BaseModel):
    """S-4: typed replacement for raw dict get_pending_saves."""

    status: SaveStatus
    count: int
    oldest_pending_at: datetime | None = None
    artifact_ids: list[str] = []


class AnalysisResult(BaseModel):
    """M-1: actionable routing result with suggested_steps."""

    mode: AnalysisMode
    rationale: str
    suggested_steps: list[str]


class HygieneReport(BaseModel):
    project_id: str | None
    scope: str
    duplicates_found: int
    outdated_decisions: int
    obsolete_patterns: int
    entity_drift_count: int
    unresolved_saves: int
    candidate_ids: dict[str, list[str]]  # category → [node_ids]
    checked_at: datetime


class ServiceInfo(BaseModel):
    service_id: str
    display_name: str | None = None
    workspace_id: str | None = None
    status: str
    last_seen: datetime | None = None
    tags: list[str] = []


class ServiceListResult(BaseModel):
    services: list[ServiceInfo]
    workspace_id: str
    retrieval_status: RetrievalStatus


class ServiceRegistrationResult(BaseModel):
    service_info: ServiceInfo
    workspace_created: bool
    status: SaveStatus


class CrossServiceItem(BaseModel):
    node_id: str
    node_type: str  # "EntityFact" | "Decision" | "Pattern"
    source_project: str
    score: float
    summary: str  # entity_name+fact for EntityFact, title for Decision


class CrossServiceBundle(BaseModel):
    items: list[CrossServiceItem]
    total_count: int
    queried_projects: list[str]
    retrieval_status: RetrievalStatus


class AffectedServiceItem(BaseModel):
    project_id: str
    depth: int
    risk_level: str
    entity_count: int


class ImpactReport(BaseModel):
    source_entity_id: str
    change_description: str
    impact_type: str
    overall_risk: str
    affected_services: list[AffectedServiceItem]
    impact_event_id: str
    created_at: datetime


class WorkspaceServiceHealth(BaseModel):
    service_id: str
    entity_count: int
    decision_count: int
    pattern_count: int
    conflict_count: int
    staleness_days: float | None
    hygiene_status: str  # "clean" | "needs_hygiene" | "critical"


class WorkspaceHealthReport(BaseModel):
    workspace_id: str
    service_count: int
    services: list[WorkspaceServiceHealth]
    total_conflicts: int
    checked_at: datetime


class ConflictRecord(BaseModel):
    source_id: str
    source_project: str
    source_summary: str
    target_id: str
    target_project: str
    target_summary: str
    link_rationale: str | None = None
    link_confidence: float | None = None
