"""Graph topology overview route — nodes + edges for the devtools canvas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from neo4j import AsyncDriver

from graphbase_memories.config import settings
from graphbase_memories.devtools.utils import staleness

router = APIRouter(prefix="/graph", tags=["graph"])

# Labels included in the per-label summary count strip (Q5).
_SUMMARY_LABELS = [
    "Project",
    "Workspace",
    "Session",
    "Decision",
    "Pattern",
    "Context",
    "EntityFact",
    "ImpactEvent",
]

# Relationship types fetched as graph edges (no CALL {} UNION — use WHERE IN instead).
_EDGE_TYPES = ["CROSS_SERVICE_LINK", "AFFECTS"]


def _get_driver() -> AsyncDriver:
    from graphbase_memories.devtools.server import _get_driver as _gd

    return _gd()


@router.get("/overview")
async def graph_overview(
    max_nodes: Annotated[int, Query(ge=1, le=1000)] = 200,
    include_stale: Annotated[bool, Query()] = True,
) -> dict:
    """Return nodes + edges + summary for the graph canvas.

    Nodes are Workspace and Project only (collapsed view).
    Child nodes (Session, Decision, etc.) appear as badge counts on Project nodes.
    Edges: MEMBER_OF (structural hierarchy) + CROSS_SERVICE_LINK / AFFECTS (signal).
    """
    now = datetime.now(UTC)

    async with _get_driver().session(database=settings.neo4j_database) as session:
        # ── Q1: Workspace nodes ────────────────────────────────────────────────
        ws_result = await session.run(
            "MATCH (w:Workspace) RETURN w.id AS id, w.name AS name LIMIT $max_nodes",
            max_nodes=max_nodes,
        )
        workspace_rows = [dict(r) async for r in ws_result]

        # ── Q2: Project nodes with child badge counts ──────────────────────────
        proj_result = await session.run(
            """
            MATCH (p:Project)
            WITH p ORDER BY p.last_seen DESC LIMIT $max_nodes
            OPTIONAL MATCH (s:Session)-[:BELONGS_TO]->(p)
            OPTIONAL MATCH (d:Decision)-[:BELONGS_TO]->(p)
            OPTIONAL MATCH (pat:Pattern)-[:BELONGS_TO]->(p)
            OPTIONAL MATCH (c:Context)-[:BELONGS_TO]->(p)
            OPTIONAL MATCH (e:EntityFact)-[:BELONGS_TO]->(p)
            RETURN p {.*} AS project,
                   count(DISTINCT s)   AS sessions,
                   count(DISTINCT d)   AS decisions,
                   count(DISTINCT pat) AS patterns,
                   count(DISTINCT c)   AS contexts,
                   count(DISTINCT e)   AS entities
            """,
            max_nodes=max_nodes,
        )
        project_rows = []
        async for r in proj_result:
            project_rows.append(
                {
                    "project": dict(r["project"]),
                    "sessions": r["sessions"],
                    "decisions": r["decisions"],
                    "patterns": r["patterns"],
                    "contexts": r["contexts"],
                    "entities": r["entities"],
                }
            )

        # ── Q3: MEMBER_OF edges (Project → Workspace structural hierarchy) ─────
        member_result = await session.run(
            """
            MATCH (p:Project)-[:MEMBER_OF]->(w:Workspace)
            RETURN p.id AS source, w.id AS target, "MEMBER_OF" AS type
            """
        )
        member_edges = [dict(r) async for r in member_result]

        # ── Q4: Signal edges — no CALL {} UNION (unreliable on Neo4j 5) ────────
        signal_result = await session.run(
            """
            MATCH (src)-[r]->(tgt)
            WHERE type(r) IN $edge_types
              AND src.id IS NOT NULL AND tgt.id IS NOT NULL
            RETURN src.id AS source, tgt.id AS target, type(r) AS type
            LIMIT 500
            """,
            edge_types=_EDGE_TYPES,
        )
        signal_edges = [dict(r) async for r in signal_result]

        # ── Q5: Per-label summary counts (Python loop — no UNION) ──────────────
        label_counts: dict[str, int] = {}
        for label in _SUMMARY_LABELS:
            # NOTE: never use $query as a param name — neo4j driver collision.
            cnt_result = await session.run(
                f"MATCH (n:{label}) RETURN count(n) AS c"
            )
            rec = await cnt_result.single()
            label_counts[label] = rec["c"] if rec else 0

        # ── Q6: Edge type distribution ─────────────────────────────────────────
        edge_dist_result = await session.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c"
        )
        edge_counts: dict[str, int] = {}
        async for r in edge_dist_result:
            edge_counts[r["t"]] = r["c"]

        # ── Q7: Total node count (uncapped) ────────────────────────────────────
        total_result = await session.run("MATCH (n) RETURN count(n) AS total")
        total_rec = await total_result.single()
        total_nodes_in_graph = total_rec["total"] if total_rec else 0

    # ── Build node list ────────────────────────────────────────────────────────

    # Workspace nodes
    workspace_nodes = [
        {
            "id": row["id"],
            "label": "Workspace",
            "display": row["name"] or row["id"],
            "is_stale": False,
            "staleness_days": None,
            "badge_counts": None,
        }
        for row in workspace_rows
    ]

    # Project nodes — apply staleness and optional stale filter
    project_nodes = []
    for row in project_rows:
        p = row["project"]
        staleness_days, is_stale = staleness(p.get("last_seen"), now)
        if not include_stale and is_stale:
            continue
        project_nodes.append(
            {
                "id": p["id"],
                "label": "Project",
                "display": p.get("display_name") or p.get("name") or p["id"],
                "is_stale": is_stale,
                "staleness_days": staleness_days,
                "badge_counts": {
                    "Session": row["sessions"],
                    "Decision": row["decisions"],
                    "Pattern": row["patterns"],
                    "Context": row["contexts"],
                    "EntityFact": row["entities"],
                },
            }
        )

    # When stale projects are filtered, also drop Workspaces with no visible Projects.
    if not include_stale:
        visible_project_ids = {n["id"] for n in project_nodes}
        # Collect which workspace IDs have at least one visible Project via MEMBER_OF
        workspaces_with_visible = {
            e["target"] for e in member_edges if e["source"] in visible_project_ids
        }
        workspace_nodes = [
            n for n in workspace_nodes if n["id"] in workspaces_with_visible
        ]

    all_nodes = workspace_nodes + project_nodes

    # ── Build edge list ────────────────────────────────────────────────────────
    # Only include edges whose both endpoints are in the visible node set.
    visible_ids = {n["id"] for n in all_nodes}
    all_edges = [
        e
        for e in (member_edges + signal_edges)
        if e["source"] in visible_ids and e["target"] in visible_ids
    ]

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "summary": {
            "counts": label_counts,
            "edge_counts": edge_counts,
            "total_nodes_in_graph": total_nodes_in_graph,
            "capped_at": max_nodes,
            "generated_at": now.isoformat(),
        },
    }
