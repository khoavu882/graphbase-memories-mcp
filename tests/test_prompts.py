"""Tests for MCP prompts layer (Phase 3-D)."""

from __future__ import annotations

from types import SimpleNamespace


def _text(msg) -> str:
    """Extract plain text from a FastMCP Message regardless of content wrapper type."""
    content = msg.content
    # FastMCP wraps content in TextContent(type, text); plain str is also accepted.
    return content.text if hasattr(content, "text") else str(content)


async def test_memory_review_prompt_structure():
    """memory_review returns a single user message with expected keywords."""
    from graphbase_memories.mcp.prompts import memory_review

    ctx = SimpleNamespace(lifespan_context={})
    messages = await memory_review(ctx, project_id="proj-test", scope="project")

    assert isinstance(messages, list)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.role == "user"
    text = _text(msg)
    assert "proj-test" in text
    assert "retrieve_context" in text
    assert "memory_freshness" in text
    assert "run_hygiene" in text


async def test_impact_before_edit_prompt_structure():
    """impact_before_edit returns a user message embedding entity_id and proposed_change."""
    from graphbase_memories.mcp.prompts import impact_before_edit

    ctx = SimpleNamespace(lifespan_context={})
    messages = await impact_before_edit(
        ctx,
        entity_id="ent-abc-123",
        proposed_change="rename authentication provider",
    )

    assert isinstance(messages, list)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.role == "user"
    text = _text(msg)
    assert "ent-abc-123" in text
    assert "rename authentication provider" in text
    assert "route_analysis" in text
    assert "governance_token" in text
    assert "propagate_impact_event" in text


async def test_federated_sync_prompt_structure():
    """federated_sync returns a user message with service and workspace context."""
    from graphbase_memories.mcp.prompts import federated_sync

    ctx = SimpleNamespace(lifespan_context={})
    messages = await federated_sync(
        ctx,
        source_service_id="svc-api-gateway",
        workspace_id="wks-platform",
    )

    assert isinstance(messages, list)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.role == "user"
    text = _text(msg)
    assert "svc-api-gateway" in text
    assert "wks-platform" in text
    assert "graphbase://services" in text
    assert "link_cross_service_entities" in text
    assert "detect_workspace_conflicts" in text


async def test_memory_review_default_scope():
    """memory_review uses 'project' as default scope when omitted."""
    from graphbase_memories.mcp.prompts import memory_review

    ctx = SimpleNamespace(lifespan_context={})
    messages = await memory_review(ctx, project_id="proj-default")
    assert "project" in _text(messages[0])
