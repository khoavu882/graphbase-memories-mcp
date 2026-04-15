"""
Graph node dataclasses — pure graph representation, not Pydantic.
Each node type has a from_record() classmethod for Neo4j Record deserialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any


def _dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(str(val))


def _date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val))


@dataclass
class ProjectNode:
    id: str
    name: str
    created_at: datetime
    last_hygiene_at: datetime | None = None
    workspace_id: str | None = None
    status: str = "idle"
    last_seen: datetime | None = None
    display_name: str | None = None
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_record(cls, r: dict) -> ProjectNode:
        return cls(
            id=r["id"],
            name=r["name"],
            created_at=_dt(r["created_at"]),
            last_hygiene_at=_dt(r.get("last_hygiene_at")),
            workspace_id=r.get("workspace_id"),
            status=r.get("status", "idle"),
            last_seen=_dt(r.get("last_seen")),
            display_name=r.get("display_name"),
            tags=list(r.get("tags") or []),
        )


@dataclass
class WorkspaceNode:
    id: str
    name: str
    created_at: datetime
    description: str | None = None

    @classmethod
    def from_record(cls, r: dict) -> WorkspaceNode:
        return cls(
            id=r["id"],
            name=r["name"],
            created_at=_dt(r["created_at"]),
            description=r.get("description"),
        )


@dataclass
class ImpactEventNode:
    id: str
    source_entity_id: str
    source_project_id: str
    change_description: str
    impact_type: str
    risk_level: str
    affected_count: int
    created_at: datetime

    @classmethod
    def from_record(cls, r: dict) -> ImpactEventNode:
        return cls(
            id=r["id"],
            source_entity_id=r["source_entity_id"],
            source_project_id=r["source_project_id"],
            change_description=r["change_description"],
            impact_type=r["impact_type"],
            risk_level=r["risk_level"],
            affected_count=int(r.get("affected_count", 0)),
            created_at=_dt(r["created_at"]),
        )


@dataclass
class GlobalScopeNode:
    id: str = "global"
    last_hygiene_at: datetime | None = None

    @classmethod
    def from_record(cls, r: dict) -> GlobalScopeNode:
        return cls(last_hygiene_at=_dt(r.get("last_hygiene_at")))


@dataclass
class FocusAreaNode:
    id: str
    name: str
    project_id: str
    description: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_record(cls, r: dict) -> FocusAreaNode:
        return cls(
            id=r["id"],
            name=r["name"],
            project_id=r["project_id"],
            description=r.get("description"),
            created_at=_dt(r.get("created_at")) or datetime.now(UTC),
        )


@dataclass
class SessionNode:
    id: str
    objective: str
    actions_taken: list[str]
    decisions_made: list[str]
    open_items: list[str]
    next_actions: list[str]
    save_scope: str
    status: str
    created_at: datetime

    @classmethod
    def from_record(cls, r: dict) -> SessionNode:
        return cls(
            id=r["id"],
            objective=r["objective"],
            actions_taken=list(r.get("actions_taken") or []),
            decisions_made=list(r.get("decisions_made") or []),
            open_items=list(r.get("open_items") or []),
            next_actions=list(r.get("next_actions") or []),
            save_scope=r["save_scope"],
            status=r["status"],
            created_at=_dt(r["created_at"]),
        )


@dataclass
class DecisionNode:
    id: str
    title: str
    rationale: str
    owner: str
    date: date
    scope: str
    confidence: float
    content_hash: str
    dedup_status: str
    created_at: datetime

    @classmethod
    def from_record(cls, r: dict) -> DecisionNode:
        return cls(
            id=r["id"],
            title=r["title"],
            rationale=r["rationale"],
            owner=r["owner"],
            date=_date(r["date"]),
            scope=r["scope"],
            confidence=float(r["confidence"]),
            content_hash=r.get("content_hash", ""),
            dedup_status=r.get("dedup_status", "new"),
            created_at=_dt(r["created_at"]),
        )


@dataclass
class PatternNode:
    id: str
    trigger: str
    repeatable_steps: list[str]
    exclusions: list[str]
    scope: str
    last_validated_at: datetime
    content_hash: str
    created_at: datetime

    @classmethod
    def from_record(cls, r: dict) -> PatternNode:
        return cls(
            id=r["id"],
            trigger=r["trigger"],
            repeatable_steps=list(r.get("repeatable_steps") or []),
            exclusions=list(r.get("exclusions") or []),
            scope=r["scope"],
            last_validated_at=_dt(r["last_validated_at"]),
            content_hash=r.get("content_hash", ""),
            created_at=_dt(r["created_at"]),
        )


@dataclass
class ContextNode:
    id: str
    content: str
    topic: str
    scope: str
    relevance_score: float
    created_at: datetime

    @classmethod
    def from_record(cls, r: dict) -> ContextNode:
        return cls(
            id=r["id"],
            content=r["content"],
            topic=r["topic"],
            scope=r["scope"],
            relevance_score=float(r.get("relevance_score", 1.0)),
            created_at=_dt(r["created_at"]),
        )


@dataclass
class EntityFactNode:
    id: str
    entity_name: str
    fact: str
    scope: str
    normalized_at: datetime | None
    created_at: datetime

    @classmethod
    def from_record(cls, r: dict) -> EntityFactNode:
        return cls(
            id=r["id"],
            entity_name=r["entity_name"],
            fact=r["fact"],
            scope=r["scope"],
            normalized_at=_dt(r.get("normalized_at")),
            created_at=_dt(r["created_at"]),
        )


@dataclass
class ServiceNode:
    """Topology node: registered service (dual-label :Project:Service)."""

    id: str
    name: str
    workspace_id: str
    display_name: str | None
    service_type: str | None
    bounded_context: str | None
    owner_team: str | None
    health_status: str | None
    env: str | None
    version: str | None
    sla: str | None
    docs_url: str | None
    tags: list[str]
    status: str
    created_at: datetime
    updated_at: datetime | None = None
    last_seen: datetime | None = None

    @classmethod
    def from_record(cls, r: dict) -> ServiceNode:
        return cls(
            id=r["id"],
            name=r["name"],
            workspace_id=r["workspace_id"],
            display_name=r.get("display_name"),
            service_type=r.get("service_type"),
            bounded_context=r.get("bounded_context"),
            owner_team=r.get("owner_team"),
            health_status=r.get("health_status"),
            env=r.get("env"),
            version=r.get("version"),
            sla=r.get("sla"),
            docs_url=r.get("docs_url"),
            tags=list(r.get("tags") or []),
            status=r.get("status", "active"),
            created_at=_dt(r["created_at"]),
            updated_at=_dt(r.get("updated_at")),
            last_seen=_dt(r.get("last_seen")),
        )


@dataclass
class DataSourceNode:
    """Topology node: external data store (DB, cache, blob storage)."""

    id: str
    source_type: str
    host: str | None
    workspace_id: str
    owner_team: str | None
    health_status: str | None
    version: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, r: dict) -> DataSourceNode:
        return cls(
            id=r["id"],
            source_type=r["source_type"],
            host=r.get("host"),
            workspace_id=r["workspace_id"],
            owner_team=r.get("owner_team"),
            health_status=r.get("health_status"),
            version=r.get("version"),
            tags=list(r.get("tags") or []),
            created_at=_dt(r["created_at"]),
            updated_at=_dt(r.get("updated_at")),
        )


@dataclass
class MessageQueueNode:
    """Topology node: async messaging channel (Kafka topic, RabbitMQ exchange)."""

    id: str
    queue_type: str
    topic_or_exchange: str | None
    workspace_id: str
    owner_team: str | None
    schema_version: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, r: dict) -> MessageQueueNode:
        return cls(
            id=r["id"],
            queue_type=r["queue_type"],
            topic_or_exchange=r.get("topic_or_exchange"),
            workspace_id=r["workspace_id"],
            owner_team=r.get("owner_team"),
            schema_version=r.get("schema_version"),
            tags=list(r.get("tags") or []),
            created_at=_dt(r["created_at"]),
            updated_at=_dt(r.get("updated_at")),
        )


@dataclass
class FeatureNode:
    """Topology node: user-facing product capability spanning multiple services."""

    id: str
    name: str
    workspace_id: str
    workflow_order: int | None
    owner_team: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, r: dict) -> FeatureNode:
        return cls(
            id=r["id"],
            name=r["name"],
            workspace_id=r["workspace_id"],
            workflow_order=int(r["workflow_order"])
            if r.get("workflow_order") is not None
            else None,
            owner_team=r.get("owner_team"),
            tags=list(r.get("tags") or []),
            created_at=_dt(r["created_at"]),
            updated_at=_dt(r.get("updated_at")),
        )


@dataclass
class BoundedContextNode:
    """Topology node: DDD bounded context grouping related services."""

    id: str
    name: str
    domain: str | None
    workspace_id: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_record(cls, r: dict) -> BoundedContextNode:
        return cls(
            id=r["id"],
            name=r["name"],
            domain=r.get("domain"),
            workspace_id=r["workspace_id"],
            tags=list(r.get("tags") or []),
            created_at=_dt(r["created_at"]),
            updated_at=_dt(r.get("updated_at")),
        )


@dataclass
class GovernanceTokenNode:
    id: str
    content_preview: str
    expires_at: datetime
    used: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_record(cls, r: dict) -> GovernanceTokenNode:
        return cls(
            id=r["id"],
            content_preview=r["content_preview"],
            expires_at=_dt(r["expires_at"]),
            used=bool(r.get("used", False)),
            created_at=_dt(r.get("created_at")) or datetime.now(UTC),
        )
