"""Artifact input schemas — SessionSchema, DecisionSchema, PatternSchema, ContextSchema, EntityFactSchema."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from graphbase_memories.mcp.schemas.enums import MemoryScope


class SessionSchema(BaseModel):
    objective: str
    actions_taken: list[str]
    decisions_made: list[str]
    open_items: list[str]
    next_actions: list[str]
    save_scope: MemoryScope


class DecisionSchema(BaseModel):
    title: str
    rationale: str
    owner: str
    date: date
    scope: MemoryScope
    supersedes: str | None = None  # id of older Decision node
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PatternSchema(BaseModel):
    trigger: str
    repeatable_steps: list[str]
    exclusions: list[str] = Field(default_factory=list)
    scope: MemoryScope
    last_validated_at: datetime


class ContextSchema(BaseModel):
    content: str
    topic: str
    scope: MemoryScope
    relevance_score: float = Field(default=1.0, ge=0.0, le=1.0)


class EntityFactSchema(BaseModel):
    entity_name: str
    fact: str
    scope: MemoryScope


class EntityRelation(BaseModel):
    """M-2: typed relationship for upsert_entity_with_deps."""

    entity_id: str
    relationship_type: Literal["BELONGS_TO", "CONFLICTS_WITH", "PRODUCED", "MERGES_INTO"]
    properties: dict[str, Any] = Field(default_factory=dict)
