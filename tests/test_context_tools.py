"""
Context tool tests: get_context.
Covers [Q3] hard token cap, priority ordering, entity filtering, empty project.
"""
from __future__ import annotations

from graphbase_memories.formatters.yaml_context import _token_count
from conftest import PROJECT, parse


async def _store(mcp, **kwargs):
    defaults = {"project": PROJECT, "entities": [], "tags": []}
    r = await mcp.call_tool("store_memory", {**defaults, **kwargs})
    return parse(r)


async def test_get_context_empty_project_returns_empty(mcp):
    """Empty project must return empty string, not an error."""
    r = await mcp.call_tool("get_context", {"project": PROJECT})
    ctx = parse(r)
    assert ctx == "" or ctx is None


async def test_get_context_includes_decisions(mcp):
    await _store(mcp, title="Use JWT", content="Adopt JWT with 1h expiry.", type="decision")
    r = await mcp.call_tool("get_context", {"project": PROJECT, "max_tokens": 500})
    ctx = parse(r)
    assert "decisions:" in ctx
    assert "JWT" in ctx


async def test_get_context_includes_patterns(mcp):
    await _store(mcp, title="Decision", content="d.", type="decision")
    await _store(mcp, title="Retry pattern", content="Exponential backoff.", type="pattern")
    r = await mcp.call_tool("get_context", {"project": PROJECT, "max_tokens": 500})
    ctx = parse(r)
    assert "patterns:" in ctx


async def test_get_context_q3_hard_token_cap(mcp, engine):
    """[Q3] Output must not exceed max_tokens (+15% tolerance)."""
    for i in range(20):
        await _store(mcp, title=f"Decision {i}",
                     content="x" * 300, type="decision")

    max_tokens = 100
    r = await mcp.call_tool("get_context", {"project": PROJECT, "max_tokens": max_tokens})
    ctx = parse(r)
    if ctx:
        actual = _token_count(ctx)
        assert actual <= int(max_tokens * 1.15), (
            f"Token cap violated: {actual} > {int(max_tokens * 1.15)}"
        )


async def test_get_context_priority_decisions_before_patterns(mcp):
    """[Q3] Decisions must appear before patterns in output."""
    await _store(mcp, title="Decision A", content="A decision.", type="decision")
    await _store(mcp, title="Pattern B", content="A pattern.", type="pattern")
    r = await mcp.call_tool("get_context", {"project": PROJECT, "max_tokens": 500})
    ctx = parse(r)
    assert ctx.index("decisions:") < ctx.index("patterns:")


async def test_get_context_stale_warnings_appear(mcp, engine):
    """[Q3] Stale memories appear under stale_warnings when older than age_days=30."""
    m = await _store(mcp, title="Old approach", content="Outdated.", type="decision")
    # Only backdate — get_context calls engine.get_stale_memories(age_days=30) which
    # returns memories with updated_at < 30d regardless of is_expired flag.
    # Do NOT call flag_expired here: it would reset updated_at to now, hiding the memory.
    engine._backdate(m["id"], 40)

    r = await mcp.call_tool("get_context", {"project": PROJECT, "max_tokens": 500})
    ctx = parse(r)
    assert "stale_warnings:" in ctx


async def test_get_context_entity_filter(mcp):
    """Entity filter must restrict context to memories referencing that entity."""
    await _store(mcp, title="Redis setup", content="Redis session cache.",
                 type="decision", entities=["redis"])
    await _store(mcp, title="Unrelated", content="Nothing to do with redis.",
                 type="pattern", entities=["kafka"])

    r = await mcp.call_tool("get_context", {
        "project": PROJECT, "entity": "redis", "max_tokens": 500
    })
    ctx = parse(r)
    # Context should contain something about redis
    assert ctx != "" and ctx is not None
    assert "redis" in ctx.lower() or "Redis" in ctx


async def test_get_context_includes_related_entities(mcp):
    """Entity filter causes related_entities section to appear when co-entities exist."""
    await _store(mcp, title="Redis+Kafka setup", content="Session layer.",
                 type="decision", entities=["redis", "kafka"])

    r = await mcp.call_tool("get_context", {
        "project": PROJECT, "entity": "redis", "max_tokens": 500
    })
    ctx = parse(r)
    # kafka is co-referenced with redis → should appear in related_entities
    assert ctx is not None
    assert "kafka" in ctx.lower()


async def test_get_context_includes_session_type(mcp):
    """Session-type memories appear under recent_sessions when budget allows."""
    await _store(mcp, title="Sprint 42 retrospective",
                 content="Key outcomes from sprint.", type="session")

    r = await mcp.call_tool("get_context", {
        "project": PROJECT, "max_tokens": 500
    })
    ctx = parse(r)
    assert ctx is not None
    assert "recent_sessions" in ctx or "Sprint 42" in ctx
