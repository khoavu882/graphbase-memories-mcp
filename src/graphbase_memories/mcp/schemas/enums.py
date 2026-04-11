"""Shared enums for all MCP tool schemas."""

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


class AnalysisMode(StrEnum):
    sequential = "sequential"
    debate = "debate"
    socratic = "socratic"


class CrossServiceLinkType(StrEnum):
    DEPENDS_ON = "DEPENDS_ON"
    SHARES_CONCEPT = "SHARES_CONCEPT"
    CONTRADICTS = "CONTRADICTS"
    SUPERSEDES = "SUPERSEDES"
    EXTENDS = "EXTENDS"
