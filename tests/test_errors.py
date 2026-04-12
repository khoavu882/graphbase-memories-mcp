"""Tests for MCPError structured error schema (Phase 1-B)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from graphbase_memories.mcp.schemas.errors import ErrorCode, MCPError

# ── Schema unit tests ────────────────────────────────────────────────────────


def test_mcp_error_serializes_to_json():
    err = MCPError(
        code=ErrorCode.ENTITY_NOT_FOUND,
        message="Entity 'abc' not found.",
        context={"entity_id": "abc"},
        next_step="Create the entity first.",
    )
    data = err.model_dump()
    assert data["error"] is True
    assert data["code"] == "ENTITY_NOT_FOUND"
    assert data["message"] == "Entity 'abc' not found."
    assert data["context"] == {"entity_id": "abc"}
    assert data["next_step"] == "Create the entity first."


def test_error_code_is_str_enum():
    assert isinstance(ErrorCode.ENTITY_NOT_FOUND, str)
    assert ErrorCode.ENTITY_NOT_FOUND == "ENTITY_NOT_FOUND"
    assert ErrorCode.SCOPE_VIOLATION == "SCOPE_VIOLATION"


def test_mcp_error_defaults():
    err = MCPError(code=ErrorCode.INTERNAL_ERROR, message="Unexpected failure.")
    assert err.error is True
    assert err.context == {}
    assert err.next_step is None


def test_all_error_codes_defined():
    codes = {e.value for e in ErrorCode}
    assert codes == {
        "ENTITY_NOT_FOUND",
        "CONFLICT_DETECTED",
        "SCOPE_VIOLATION",
        "WRITE_NOT_APPROVED",
        "FEDERATION_UNAVAILABLE",
        "GRAPH_UNHEALTHY",
        "FTS_UNAVAILABLE",
        "INTERNAL_ERROR",
    }


def test_mcp_error_distinguishable_from_save_result():
    """MCPError.error=True is the discriminant — success results never set this field."""
    err = MCPError(code=ErrorCode.SCOPE_VIOLATION, message="blocked")
    data = err.model_dump()
    assert data["error"] is True


# ── Integration test ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entity_not_found_returns_mcp_error(driver):
    """propagate_impact returns MCPError when entity_id doesn't exist in the graph."""
    from graphbase_memories.mcp.tools.impact import propagate_impact

    ctx = SimpleNamespace(lifespan_context={"driver": driver})
    result = await propagate_impact(
        ctx,
        entity_id="nonexistent-entity-id-phase1b",
        change_description="test change for phase 1-B",
    )
    assert isinstance(result, MCPError)
    assert result.code == ErrorCode.ENTITY_NOT_FOUND
    assert "nonexistent-entity-id-phase1b" in result.message
    assert result.next_step is not None
