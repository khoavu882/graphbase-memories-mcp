"""
Read tool tests: get_memory, list_memories, search_memories, delete_memory.
Covers [R3] include_deleted, FTS5 ranking, soft-delete behaviour.
"""
from __future__ import annotations

import pytest
from conftest import PROJECT, parse


async def _store(mcp, **kwargs):
    defaults = {"project": PROJECT, "entities": [], "tags": []}
    r = await mcp.call_tool("store_memory", {**defaults, **kwargs})
    return parse(r)


# ---------------------------------------------------------------------------
# get_memory
# ---------------------------------------------------------------------------

async def test_get_memory_returns_full_dict(mcp):
    m = await _store(mcp, title="T1", content="C1", type="decision",
                     entities=["redis"], tags=["db"])
    r = await mcp.call_tool("get_memory", {"project": PROJECT, "memory_id": m["id"]})
    result = parse(r)
    assert result["id"] == m["id"]
    assert result["title"] == "T1"
    assert "entities" in result
    assert any(e["name"] == "redis" for e in result["entities"])


async def test_get_memory_missing_returns_none(mcp):
    r = await mcp.call_tool("get_memory", {"project": PROJECT, "memory_id": "no-such-id"})
    assert parse(r) is None


async def test_get_memory_r3_excludes_deleted_by_default(mcp):
    """[R3] Soft-deleted memory must not be returned without include_deleted=True."""
    m = await _store(mcp, title="Gone", content="old", type="session")
    await mcp.call_tool("delete_memory", {"project": PROJECT, "memory_id": m["id"]})

    r = await mcp.call_tool("get_memory", {"project": PROJECT, "memory_id": m["id"]})
    assert parse(r) is None


async def test_get_memory_r3_include_deleted_returns_it(mcp):
    """[R3] include_deleted=True must return soft-deleted memory."""
    m = await _store(mcp, title="Gone", content="old", type="session")
    await mcp.call_tool("delete_memory", {"project": PROJECT, "memory_id": m["id"]})

    r = await mcp.call_tool("get_memory", {
        "project": PROJECT, "memory_id": m["id"], "include_deleted": True
    })
    result = parse(r)
    assert result is not None
    assert result["is_deleted"] is True


async def test_get_memory_includes_edges(mcp):
    """get_memory must include outgoing edges."""
    m_old = await _store(mcp, title="Old", content="old", type="decision")
    m_new = await _store(mcp, title="New", content="new", type="decision")
    await mcp.call_tool("relate_memories", {
        "project": PROJECT,
        "from_id": m_new["id"],
        "to_id": m_old["id"],
        "relationship": "SUPERSEDES",
    })
    r = await mcp.call_tool("get_memory", {"project": PROJECT, "memory_id": m_new["id"]})
    result = parse(r)
    edge_types = [e["type"] for e in result["edges"]]
    assert "SUPERSEDES" in edge_types


# ---------------------------------------------------------------------------
# list_memories
# ---------------------------------------------------------------------------

async def test_list_memories_newest_first(mcp, engine):
    r1 = await _store(mcp, title="First", content="c", type="session")
    r2 = await _store(mcp, title="Second", content="c", type="session")
    # Backdate "First" so "Second" is definitively newer (same-second ambiguity)
    engine._backdate(r1["id"], 1)
    r = await mcp.call_tool("list_memories", {"project": PROJECT})
    items = parse(r)
    assert len(items) >= 2
    assert items[0]["title"] == "Second"


async def test_list_memories_type_filter(mcp):
    await _store(mcp, title="D1", content="c", type="decision")
    await _store(mcp, title="P1", content="c", type="pattern")
    r = await mcp.call_tool("list_memories", {"project": PROJECT, "type": "decision"})
    items = parse(r)
    assert all(i["type"] == "decision" for i in items)


async def test_list_memories_excludes_deleted_by_default(mcp):
    """[R3] list_memories must not return soft-deleted memories."""
    m = await _store(mcp, title="Gone", content="c", type="session")
    await mcp.call_tool("delete_memory", {"project": PROJECT, "memory_id": m["id"]})
    r = await mcp.call_tool("list_memories", {"project": PROJECT})
    ids = [i["id"] for i in parse(r)]
    assert m["id"] not in ids


async def test_list_memories_include_deleted(mcp):
    """[R3] include_deleted=True must include soft-deleted memories."""
    m = await _store(mcp, title="Gone", content="c", type="session")
    await mcp.call_tool("delete_memory", {"project": PROJECT, "memory_id": m["id"]})
    r = await mcp.call_tool("list_memories", {"project": PROJECT, "include_deleted": True})
    ids = [i["id"] for i in parse(r)]
    assert m["id"] in ids


async def test_list_memories_pagination(mcp):
    for i in range(5):
        await _store(mcp, title=f"M{i}", content="c", type="session")
    r_page1 = await mcp.call_tool("list_memories", {"project": PROJECT, "limit": 3, "offset": 0})
    r_page2 = await mcp.call_tool("list_memories", {"project": PROJECT, "limit": 3, "offset": 3})
    ids1 = {i["id"] for i in parse(r_page1)}
    ids2 = {i["id"] for i in parse(r_page2)}
    assert ids1.isdisjoint(ids2), "Pages must not overlap"


# ---------------------------------------------------------------------------
# search_memories
# ---------------------------------------------------------------------------

async def test_search_memories_ranks_best_match_first(mcp):
    await _store(mcp, title="Redis caching", content="Redis is the session cache.", type="pattern")
    await _store(mcp, title="Auth design", content="Unrelated auth content.", type="decision")
    r = await mcp.call_tool("search_memories", {"query": "Redis", "project": PROJECT})
    results = parse(r)
    assert len(results) >= 1
    assert "redis" in results[0]["title"].lower() or "redis" in results[0]["snippet"].lower()


async def test_search_memories_excludes_deleted(mcp):
    m = await _store(mcp, title="Deleted result", content="This should not appear.", type="session")
    await mcp.call_tool("delete_memory", {"project": PROJECT, "memory_id": m["id"]})
    r = await mcp.call_tool("search_memories", {"query": "deleted result", "project": PROJECT})
    ids = [res["id"] for res in parse(r)]
    assert m["id"] not in ids


async def test_search_memories_empty_query_returns_empty(mcp):
    r = await mcp.call_tool("search_memories", {"query": "", "project": PROJECT})
    assert parse(r) == []


# ---------------------------------------------------------------------------
# delete_memory
# ---------------------------------------------------------------------------

async def test_delete_memory_soft_delete(mcp):
    m = await _store(mcp, title="To delete", content="bye", type="session")
    r = await mcp.call_tool("delete_memory", {"project": PROJECT, "memory_id": m["id"]})
    result = parse(r)
    assert result["deleted"] is True
    assert result["permanent"] is False
    assert result["memory_id"] == m["id"]


async def test_delete_memory_unknown_id(mcp):
    """Deleting unknown id should return deleted=False."""
    r = await mcp.call_tool("delete_memory", {"project": PROJECT, "memory_id": "no-such"})
    result = parse(r)
    assert result["deleted"] is False


async def test_search_snippet_has_ellipsis_for_long_content(mcp):
    """Snippets for long content must include leading/trailing ellipsis characters."""
    # 500-char content with match near the middle — forces both start > 0 and end < len
    prefix = "x" * 200
    suffix = "y" * 200
    await _store(mcp, title="Long doc", content=f"{prefix} targetterm {suffix}", type="pattern")
    r = await mcp.call_tool("search_memories", {"query": "targetterm", "project": PROJECT})
    results = parse(r)
    assert len(results) >= 1
    snippet = results[0]["snippet"]
    assert "…" in snippet  # both prefix and suffix cause ellipsis


async def test_search_memories_cross_project_no_project_arg(mcp, engine):
    """search_memories with no project searches across all loaded engines."""
    await _store(mcp, title="Cross-proj memory", content="Unique term xqzk99.", type="decision")
    # No project filter — should still find the memory from the loaded engine
    r = await mcp.call_tool("search_memories", {"query": "xqzk99"})
    results = parse(r)
    titles = [res["title"] for res in results]
    assert "Cross-proj memory" in titles
