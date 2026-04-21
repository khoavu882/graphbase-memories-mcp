"""Domain enums — shared across engines and adapters."""

from enum import StrEnum


class ScopeState(StrEnum):
    resolved = "resolved"
    uncertain = "uncertain"
    unresolved = "unresolved"


class MemoryScope(StrEnum):
    global_ = "global"
    project = "project"
    focus = "focus"


class SaveStatus(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    saved = "saved"
    partial = "partial"
    pending_retry = "pending_retry"
    failed = "failed"
    blocked_scope = "blocked_scope"
    duplicate_skip = "duplicate_skip"


class RetrievalStatus(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    succeeded = "succeeded"
    empty = "empty"
    timed_out = "timed_out"
    failed = "failed"
    conflicted = "conflicted"


class DedupOutcome(StrEnum):
    new = "new"
    duplicate_skip = "duplicate_skip"
    supersede = "supersede"
    manual_review = "manual_review"


class CrossServiceLinkType(StrEnum):
    DEPENDS_ON = "DEPENDS_ON"
    SHARES_CONCEPT = "SHARES_CONCEPT"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    EXTENDS = "EXTENDS"


class FreshnessLevel(StrEnum):
    current = "current"
    recent = "recent"
    stale = "stale"


# ── Topology enums ──────────────────────────────────────────────────────────


class ServiceType(StrEnum):
    api = "api"
    worker = "worker"
    gateway = "gateway"
    frontend = "frontend"
    batch = "batch"
    ml = "ml"
    other = "other"


class ServiceHealthStatus(StrEnum):
    healthy = "healthy"
    degraded = "degraded"
    down = "down"
    unknown = "unknown"


class DataSourceType(StrEnum):
    postgresql = "postgresql"
    mysql = "mysql"
    mongodb = "mongodb"
    redis = "redis"
    elasticsearch = "elasticsearch"
    s3 = "s3"
    other = "other"


class MessageQueueType(StrEnum):
    kafka = "kafka"
    rabbitmq = "rabbitmq"
    sqs = "sqs"
    pubsub = "pubsub"
    other = "other"


class TopologyLinkType(StrEnum):
    CALLS_DOWNSTREAM = "CALLS_DOWNSTREAM"
    CALLS_UPSTREAM = "CALLS_UPSTREAM"
    READS_FROM = "READS_FROM"
    WRITES_TO = "WRITES_TO"
    READS_WRITES = "READS_WRITES"
    PUBLISHES_TO = "PUBLISHES_TO"
    SUBSCRIBES_TO = "SUBSCRIBES_TO"
    INVOLVES = "INVOLVES"
    MEMBER_OF_CONTEXT = "MEMBER_OF_CONTEXT"


class DependencyDirection(StrEnum):
    downstream = "downstream"
    upstream = "upstream"
    both = "both"


class ServiceOwnership(StrEnum):
    owner = "owner"
    contributor = "contributor"
    consumer = "consumer"
