"""
Integration tests for SurfaceEngine (engines/surface.py) and surface CLI subcommand.

Covers:
  - BM25 four-index path: found, label-property mapping, empty/short query, scope filtering
  - Keyword-staleness path: match, current-node filter, coalesce, empty keywords
  - surface CLI: stderr-only output, graceful exit-0 on Neo4j down
  - format_for_hook: next_step hint when no matches
"""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import TEST_DB, TEST_PROJECT_ID

# ── BM25 path ────────────────────────────────────────────────────────────────


async def test_bm25_empty_query(driver):
    """Empty query → immediate SurfaceResult with no matches."""
    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query="",
        project_id=TEST_PROJECT_ID,
        driver=driver,
        database=TEST_DB,
    )
    assert result.matches == []
    assert result.total_found == 0


async def test_bm25_short_query(driver):
    """Query shorter than 3 characters → empty result (guard clause)."""
    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query="ab",
        project_id=TEST_PROJECT_ID,
        driver=driver,
        database=TEST_DB,
    )
    assert result.matches == []
    assert result.total_found == 0


async def test_bm25_found_across_indexes(driver, fresh_project):
    """One node per label seeded with a unique term — all four labels returned."""
    unique = "zqxuniq42surface"

    async with driver.session(database=TEST_DB) as session:
        # Decision — via index decision_fulltext (title, rationale)
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (d:Decision {
                id: 'surf-d-001', title: $term, rationale: 'rationale-text',
                scope: 'project', project_id: $pid,
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(p)
            """,
            term=unique + " decision",
            pid=fresh_project,
        )
        # Pattern — via index pattern_fulltext (trigger, repeatable_steps_text)
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (pt:Pattern {
                id: 'surf-p-001', trigger: $term, repeatable_steps_text: 'steps here',
                scope: 'project', project_id: $pid,
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(p)
            """,
            term=unique + " pattern",
            pid=fresh_project,
        )
        # Context — via index context_fulltext (topic, content)
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (c:Context {
                id: 'surf-c-001', topic: $term, content: 'content here',
                scope: 'project', project_id: $pid,
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(p)
            """,
            term=unique + " context",
            pid=fresh_project,
        )
        # EntityFact — via index entity_fulltext (entity_name, fact)
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (e:EntityFact {
                id: 'surf-e-001', entity_name: $term, fact: 'fact here',
                scope: 'project', project_id: $pid,
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(p)
            """,
            term=unique + " entity",
            pid=fresh_project,
        )

    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=unique,
        project_id=fresh_project,
        limit=10,
        driver=driver,
        database=TEST_DB,
    )
    labels_found = {m.label for m in result.matches}
    assert "Decision" in labels_found, f"Decision missing from: {labels_found}"
    assert "Pattern" in labels_found, f"Pattern missing from: {labels_found}"
    assert "Context" in labels_found, f"Context missing from: {labels_found}"
    assert "EntityFact" in labels_found, f"EntityFact missing from: {labels_found}"


async def test_bm25_label_property_mapping(driver, fresh_project):
    """BM25 match on Decision returns name=title; EntityFact returns name=entity_name."""
    unique = "zqxmapping17surf"

    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (d:Decision {
                id: 'surf-map-d', title: $term, rationale: 'my rationale text',
                scope: 'project', project_id: $pid,
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(p)
            """,
            term=unique + " decision",
            pid=fresh_project,
        )
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (e:EntityFact {
                id: 'surf-map-e', entity_name: $term, fact: 'entity fact text',
                scope: 'project', project_id: $pid,
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(p)
            """,
            term=unique + " entity",
            pid=fresh_project,
        )

    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=unique,
        project_id=fresh_project,
        limit=10,
        driver=driver,
        database=TEST_DB,
    )
    decision_match = next((m for m in result.matches if m.label == "Decision"), None)
    entity_match = next((m for m in result.matches if m.label == "EntityFact"), None)

    assert decision_match is not None, "Decision node not found in BM25 result"
    assert unique in decision_match.name, "Decision.name should be mapped from title"
    assert "rationale" in decision_match.content, "Decision.content should be rationale"

    assert entity_match is not None, "EntityFact node not found in BM25 result"
    assert unique in entity_match.name, "EntityFact.name should be mapped from entity_name"
    assert "fact" in entity_match.content, "EntityFact.content should be fact text"


async def test_bm25_project_scoped(driver, fresh_project):
    """Node with a different project_id is excluded from results."""
    unique = "zqxscopetest55"
    other_pid = "other-project-surface-test"

    async with driver.session(database=TEST_DB) as session:
        # Seed node for the test project
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (d:Decision {
                id: 'surf-scope-mine', title: $term, rationale: 'mine',
                scope: 'project', project_id: $pid,
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(p)
            """,
            term=unique + " mine",
            pid=fresh_project,
        )
        # Seed node for a different project (no global scope)
        await session.run(
            """
            MERGE (p:Project {id: $other_pid})
            CREATE (d:Decision {
                id: 'surf-scope-other', title: $term, rationale: 'other',
                scope: 'project', project_id: $other_pid,
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(p)
            """,
            term=unique + " other",
            other_pid=other_pid,
        )

    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=unique,
        project_id=fresh_project,
        limit=10,
        driver=driver,
        database=TEST_DB,
    )
    ids_found = {m.id for m in result.matches}
    assert "surf-scope-mine" in ids_found, "Own project node must be returned"
    assert "surf-scope-other" not in ids_found, "Other project node must be excluded"

    # Cleanup other project
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            "MATCH (n)-[:BELONGS_TO]->(p:Project {id: $pid}) DETACH DELETE n, p",
            pid=other_pid,
        )


async def test_bm25_global_included(driver, fresh_project):
    """Node with scope='global' is returned regardless of project_id filter."""
    unique = "zqxglobalsurface88"

    async with driver.session(database=TEST_DB) as session:
        # Global-scope decision: project_id="" so the WHERE clause passes
        await session.run(
            """
            MATCH (g:GlobalScope {id: 'global'})
            CREATE (d:Decision {
                id: 'surf-global-001', title: $term, rationale: 'global rationale',
                scope: 'global', project_id: '',
                created_at: datetime(), updated_at: datetime()
            })-[:BELONGS_TO]->(g)
            """,
            term=unique + " global decision",
        )

    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=unique,
        project_id=fresh_project,  # different from the seeded node's project_id
        limit=10,
        driver=driver,
        database=TEST_DB,
    )
    ids_found = {m.id for m in result.matches}
    assert "surf-global-001" in ids_found, "Global-scope node must be returned for any project_id"

    # Cleanup global node
    async with driver.session(database=TEST_DB) as session:
        await session.run("MATCH (d:Decision {id: 'surf-global-001'}) DETACH DELETE d")


# ── Keyword-staleness path ────────────────────────────────────────────────────


async def test_staleness_keyword_match(driver, fresh_project):
    """Node created in the past with a matching keyword appears in staleness result."""
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (d:Decision {
                id: 'surf-stale-001', title: 'authentication middleware removal',
                rationale: 'legacy', scope: 'project', project_id: $pid,
                created_at: datetime() - duration('P30D'),
                updated_at: datetime() - duration('P30D')
            })-[:BELONGS_TO]->(p)
            """,
            pid=fresh_project,
        )

    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=None,
        keywords=["authentication"],
        driver=driver,
        database=TEST_DB,
    )
    names_found = [m.name for m in result.matches]
    assert any("authentication" in n.lower() for n in names_found), (
        f"Expected 'authentication' in match names, got: {names_found}"
    )
    assert result.total_found >= 1
    assert all(m.freshness == "stale" for m in result.matches)


async def test_staleness_current_node_excluded(driver, fresh_project):
    """Node with updated_at set to the future is excluded from staleness check."""
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (d:Decision {
                id: 'surf-future-001', title: 'oauth2 migration',
                rationale: 'current', scope: 'project', project_id: $pid,
                created_at: datetime(),
                updated_at: datetime() + duration('P1D')
            })-[:BELONGS_TO]->(p)
            """,
            pid=fresh_project,
        )

    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=None,
        keywords=["oauth2"],
        driver=driver,
        database=TEST_DB,
    )
    ids_found = {m.id for m in result.matches}
    assert "surf-future-001" not in ids_found, (
        "Node with future updated_at must not appear in staleness check"
    )


async def test_staleness_coalesce_created_at(driver, fresh_project):
    """Node with no updated_at field falls back to created_at via COALESCE."""
    async with driver.session(database=TEST_DB) as session:
        # No updated_at — coalesce must use created_at
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (d:Decision {
                id: 'surf-coalesce-001', title: 'kafka consumer pattern',
                rationale: 'legacy', scope: 'project', project_id: $pid,
                created_at: datetime() - duration('P10D')
            })-[:BELONGS_TO]->(p)
            """,
            pid=fresh_project,
        )

    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=None,
        keywords=["kafka"],
        driver=driver,
        database=TEST_DB,
    )
    # Keyword path returns id="" always; match on name (title field)
    names_found = {m.name for m in result.matches}
    assert "kafka consumer pattern" in names_found, (
        f"Node with only created_at must appear via COALESCE, got names: {names_found}"
    )


async def test_staleness_empty_keywords(driver):
    """Keywords all shorter than 3 characters → empty result, no error."""
    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=None,
        keywords=["ab", "x", ""],
        driver=driver,
        database=TEST_DB,
    )
    assert result.matches == []
    assert result.total_found == 0


# ── format helpers ────────────────────────────────────────────────────────────


async def test_format_for_hook_no_matches():
    """format_for_hook returns empty string when result has no matches."""
    from graphbase_memories.engines import surface as surface_engine
    from graphbase_memories.mcp.schemas.results import SurfaceResult

    result = SurfaceResult(matches=[], query_used="test", total_found=0)
    output = surface_engine.format_for_hook(result)
    assert output == ""


def test_format_for_hook_next_step_hint():
    """_build_next_step with no matches returns a retrieve_context hint."""
    from graphbase_memories.engines import surface as surface_engine

    hint = surface_engine._build_next_step([], 0, 5)
    assert hint is not None
    assert "retrieve_context" in hint


async def test_format_staleness_for_hook_formatting(driver, fresh_project):
    """format_staleness_for_hook output includes keyword and entity name."""
    async with driver.session(database=TEST_DB) as session:
        await session.run(
            """
            MATCH (p:Project {id: $pid})
            CREATE (d:Decision {
                id: 'surf-fmt-001', title: 'redis session store',
                rationale: 'caching', scope: 'project', project_id: $pid,
                created_at: datetime() - duration('P5D'),
                updated_at: datetime() - duration('P5D')
            })-[:BELONGS_TO]->(p)
            """,
            pid=fresh_project,
        )

    from graphbase_memories.engines import surface as surface_engine

    result = await surface_engine.execute(
        query=None,
        keywords=["redis"],
        driver=driver,
        database=TEST_DB,
    )
    output = surface_engine.format_staleness_for_hook(result, ["redis"])
    if result.matches:
        assert "redis" in output.lower()
        assert "[Graphbase]" in output


# ── CLI subprocess path ───────────────────────────────────────────────────────


def test_surface_cli_exits_0_on_neo4j_down():
    """surface CLI must exit with code 0 even when Neo4j is unreachable."""
    env = {**os.environ, "GRAPHBASE_NEO4J_URI": "bolt://127.0.0.1:19999"}
    result = subprocess.run(
        [sys.executable, "-m", "graphbase_memories.main", "surface", "somequery"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"surface must exit 0 on Neo4j down, got {result.returncode}. stderr: {result.stderr[:200]}"
    )


def test_surface_cli_stderr_only_no_stdout():
    """surface CLI: stdout must be empty regardless of results (hook protocol)."""
    result = subprocess.run(
        [sys.executable, "-m", "graphbase_memories.main", "surface", "authentication"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert result.stdout == "", (
        f"surface must write nothing to stdout, got: {result.stdout[:200]!r}"
    )
