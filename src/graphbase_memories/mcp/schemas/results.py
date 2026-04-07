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
