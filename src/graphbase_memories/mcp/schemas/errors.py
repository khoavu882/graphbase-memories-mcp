"""Structured error schema for MCP tool responses (Phase 1-B).

MCPError is a discriminated error type returned instead of raising exceptions.
The `error: bool = True` field lets agents distinguish errors from success
results without inspecting status strings.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ErrorCode(StrEnum):
    ENTITY_NOT_FOUND = "ENTITY_NOT_FOUND"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    WRITE_NOT_APPROVED = "WRITE_NOT_APPROVED"
    FEDERATION_UNAVAILABLE = "FEDERATION_UNAVAILABLE"
    GRAPH_UNHEALTHY = "GRAPH_UNHEALTHY"
    FTS_UNAVAILABLE = "FTS_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class MCPError(BaseModel):
    error: bool = True
    code: ErrorCode
    message: str
    context: dict = {}
    next_step: str | None = None
