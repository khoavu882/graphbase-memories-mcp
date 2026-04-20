"""
Integration: devtools graph stats and memory search routes against live Neo4j.
"""

from __future__ import annotations

from conftest import TEST_DB
from httpx import ASGITransport, AsyncClient


async def test_graph_stats_returns_node_counts(driver):
    """GET /graph/stats returns node_counts dict with known labels."""
    from graphbase_memories.devtools.routes.health import graph_stats

    result = await graph_stats(driver)

    assert "node_counts" in result
    assert "relationship_counts" in result
    assert "checked_at" in result

    expected_labels = {"Project", "Session", "Decision", "Pattern", "Context", "EntityFact"}
    for label in expected_labels:
        assert label in result["node_counts"], f"Missing label: {label}"


async def test_graph_stats_counts_are_non_negative(driver):
    """All node and relationship counts are non-negative integers."""
    from graphbase_memories.devtools.routes.health import graph_stats

    result = await graph_stats(driver)

    for label, cnt in result["node_counts"].items():
        assert isinstance(cnt, int) and cnt >= 0, f"{label} count invalid: {cnt}"

    for rtype, cnt in result["relationship_counts"].items():
        assert isinstance(cnt, int) and cnt >= 0, f"{rtype} count invalid: {cnt}"


async def test_graph_stats_project_count_increases(driver, fresh_project):
    """After creating a project, Project count is at least 1."""
    from graphbase_memories.devtools.routes.health import graph_stats

    result = await graph_stats(driver)
    assert result["node_counts"]["Project"] >= 1


async def test_memory_search_returns_list(driver):
    """POST /memory/search with a query returns an items/total payload."""
    from graphbase_memories.devtools.routes.memory import MemorySearchRequest, search_memory

    body = MemorySearchRequest(query="test", limit=10)
    result = await search_memory(body, driver)

    assert isinstance(result, dict)
    assert "items" in result
    assert "total" in result


async def test_memory_search_with_label_filter(driver, fresh_project):
    """POST /memory/search with label=Session filters correctly."""
    from graphbase_memories.devtools.routes.memory import MemorySearchRequest, search_memory

    # Create a session node to search for
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            CREATE (s:Session {
                id: 'test-search-session-001',
                title: 'searchable test session',
                summary: 'unique search phrase xqzwk',
                created_at: datetime()
            })
            """,
        )

    try:
        body = MemorySearchRequest(query="unique search phrase xqzwk", label="Session", limit=5)
        result = await search_memory(body, driver)
        assert isinstance(result, dict)
        assert "items" in result
        # If found, verify it's a Session
        if result["items"]:
            assert all(r.get("_label") == "Session" for r in result["items"])
    finally:
        async with driver.session(database=TEST_DB) as session:
            await session.run("MATCH (s:Session {id: 'test-search-session-001'}) DETACH DELETE s")


async def test_memory_list_returns_nodes(driver, fresh_project):
    """GET /memory returns an items/total payload of memory nodes."""
    from graphbase_memories.devtools.routes.memory import list_memory

    result = await list_memory(driver, project_id=None, label=None, limit=10)
    assert isinstance(result, dict)
    assert "items" in result
    assert "total" in result


async def test_memory_pagination(driver, fresh_project):
    """GET /memory supports offset, limit, sort_by, sort_order, and total count."""
    from graphbase_memories.devtools.routes.memory import list_memory

    node_ids = [
        "test-memory-pagination-alpha",
        "test-memory-pagination-beta",
        "test-memory-pagination-gamma",
    ]
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            UNWIND $rows AS row
            CREATE (d:Decision {
                id: row.id,
                title: row.title,
                summary: row.title,
                created_at: datetime()
            })
            WITH d, row
            MATCH (p:Project {id: $pid})
            MERGE (d)-[:BELONGS_TO]->(p)
            """,
            rows=[
                {"id": node_ids[0], "title": "alpha"},
                {"id": node_ids[1], "title": "beta"},
                {"id": node_ids[2], "title": "gamma"},
            ],
            pid=fresh_project,
        )

    try:
        result = await list_memory(
            driver,
            project_id=fresh_project,
            label="Decision",
            limit=2,
            offset=1,
            sort_by="title",
            sort_order="asc",
        )
        assert result["total"] >= 3
        titles = [item["title"] for item in result["items"] if item["id"] in node_ids]
        assert titles == ["beta", "gamma"]
    finally:
        async with driver.session(database=TEST_DB) as session:
            await session.run(
                "MATCH (d:Decision) WHERE d.id IN $ids DETACH DELETE d",
                ids=node_ids,
            )


async def test_memory_timeline_format_groups_by_day(driver, fresh_project):
    """GET /memory?format=timeline returns day-grouped buckets."""
    from graphbase_memories.devtools.routes.memory import list_memory

    node_ids = [
        "test-memory-timeline-001",
        "test-memory-timeline-002",
        "test-memory-timeline-003",
    ]
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            UNWIND $rows AS row
            CREATE (d:Decision {
                id: row.id,
                title: row.title,
                summary: row.title,
                created_at: datetime(row.created_at)
            })
            WITH d, row
            MATCH (p:Project {id: $pid})
            MERGE (d)-[:BELONGS_TO]->(p)
            """,
            rows=[
                {
                    "id": node_ids[0],
                    "title": "timeline newest",
                    "created_at": "2026-04-20T10:15:00Z",
                },
                {
                    "id": node_ids[1],
                    "title": "timeline same day",
                    "created_at": "2026-04-20T08:00:00Z",
                },
                {
                    "id": node_ids[2],
                    "title": "timeline previous day",
                    "created_at": "2026-04-19T12:30:00Z",
                },
            ],
            pid=fresh_project,
        )

    try:
        result = await list_memory(
            driver,
            project_id=fresh_project,
            label="Decision",
            limit=10,
            sort_by="created_at",
            sort_order="desc",
            format="timeline",
        )
        assert result["format"] == "timeline"
        assert result["total"] >= 3
        assert [group["date"] for group in result["groups"][:2]] == ["2026-04-20", "2026-04-19"]
        assert result["groups"][0]["count"] >= 2
        assert [item["id"] for item in result["groups"][0]["items"][:2]] == node_ids[:2]
        assert result["groups"][1]["items"][0]["id"] == node_ids[2]
    finally:
        async with driver.session(database=TEST_DB) as session:
            await session.run(
                "MATCH (d:Decision) WHERE d.id IN $ids DETACH DELETE d",
                ids=node_ids,
            )


async def test_memory_node_not_found_raises_404(driver):
    """GET /memory/{node_id} for a nonexistent ID raises 404."""
    from fastapi import HTTPException

    from graphbase_memories.devtools.routes.memory import get_node

    try:
        await get_node("nonexistent-node-id-zzzz", driver)
        raise AssertionError("Should have raised HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 404


async def test_patch_memory_node(driver, fresh_project):
    """PATCH /memory/{node_id} updates allowed fields when token is valid."""
    from graphbase_memories.devtools.deps import set_devtools_token
    from graphbase_memories.devtools.server import app

    node_id = "test-memory-patch-node"
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            CREATE (d:Decision {
                id: $id,
                title: 'before',
                summary: 'before summary',
                created_at: datetime()
            })
            WITH d
            MATCH (p:Project {id: $pid})
            MERGE (d)-[:BELONGS_TO]->(p)
            """,
            id=node_id,
            pid=fresh_project,
        )

    app.state.driver = driver
    set_devtools_token("test-devtools-token")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            f"/memory/{node_id}",
            json={"title": "after", "summary": "after summary"},
            headers={"X-Devtools-Token": "test-devtools-token"},
        )

    try:
        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "after"
        assert payload["summary"] == "after summary"
    finally:
        async with driver.session(database=TEST_DB) as session:
            await session.run("MATCH (d:Decision {id: $id}) DETACH DELETE d", id=node_id)


async def test_delete_memory_node(driver, fresh_project):
    """DELETE /memory/{node_id}?confirm=true removes the node when token is valid."""
    from graphbase_memories.devtools.deps import set_devtools_token
    from graphbase_memories.devtools.server import app

    node_id = "test-memory-delete-node"
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            CREATE (d:Decision {
                id: $id,
                title: 'delete me',
                created_at: datetime()
            })
            WITH d
            MATCH (p:Project {id: $pid})
            MERGE (d)-[:BELONGS_TO]->(p)
            """,
            id=node_id,
            pid=fresh_project,
        )

    app.state.driver = driver
    set_devtools_token("test-devtools-token")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.delete(
            f"/memory/{node_id}",
            params={"confirm": "true"},
            headers={"X-Devtools-Token": "test-devtools-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": node_id}

    async with driver.session(database=TEST_DB) as session:
        result = await session.run(
            "MATCH (d:Decision {id: $id}) RETURN count(d) AS cnt", id=node_id
        )
        record = await result.single()
        assert record["cnt"] == 0


async def test_write_requires_token(driver, fresh_project):
    """PATCH and DELETE reject requests without the startup token."""
    from graphbase_memories.devtools.deps import set_devtools_token
    from graphbase_memories.devtools.server import app

    node_id = "test-memory-token-node"
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            CREATE (d:Decision {
                id: $id,
                title: 'guarded',
                created_at: datetime()
            })
            WITH d
            MATCH (p:Project {id: $pid})
            MERGE (d)-[:BELONGS_TO]->(p)
            """,
            id=node_id,
            pid=fresh_project,
        )

    app.state.driver = driver
    set_devtools_token("expected-token")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        patch_response = await client.patch(
            f"/memory/{node_id}",
            json={"title": "blocked"},
        )
        delete_response = await client.delete(
            f"/memory/{node_id}",
            params={"confirm": "true"},
        )

    try:
        assert patch_response.status_code == 403
        assert delete_response.status_code == 403
    finally:
        async with driver.session(database=TEST_DB) as session:
            await session.run("MATCH (d:Decision {id: $id}) DETACH DELETE d", id=node_id)
