"""Graph topology overview route — nodes + edges for the devtools canvas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from graphbase_memories.config import settings
from graphbase_memories.devtools.deps import DriverDep
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
    # Topology node types (T5.3)
    "Service",
    "DataSource",
    "MessageQueue",
    "Feature",
    "BoundedContext",
]

# Relationship types fetched as signal/cross-service edges
# (no CALL {} UNION — use WHERE IN instead).
_EDGE_TYPES = ["CROSS_SERVICE_LINK", "AFFECTS"]

# Entity topology relationship types shown in expanded view.
# Includes legacy EntityFact-based types (BELONGS_TO, PRODUCES, etc.) for backward
# compatibility AND new first-class topology types added in T5.3.
_TOPOLOGY_EDGE_TYPES = [
    "BELONGS_TO",  # artifact → Project (legacy EntityFact ownership)
    "PRODUCES",  # legacy EntityFact Kafka producer
    "CONSUMES",  # legacy EntityFact Kafka consumer
    "READS",  # legacy EntityFact read
    "WRITES",  # legacy EntityFact write
    "INVOLVES",  # Feature→Service (new) and EntityFact→EntityFact (legacy)
    "CONFLICTS_WITH",
    "MERGES_INTO",
    # New first-class topology relationship types
    "CALLS_DOWNSTREAM",
    "CALLS_UPSTREAM",
    "READS_FROM",
    "WRITES_TO",
    "PUBLISHES_TO",
    "SUBSCRIBES_TO",
    "MEMBER_OF_CONTEXT",  # Service → BoundedContext (avoids collision with BELONGS_TO)
    "PART_OF",  # DataSource/MessageQueue/Feature → Workspace
    "HAS_FEATURE",  # Workspace ← Feature
]


@router.get("/overview")
async def graph_overview(
    driver: DriverDep,
    max_nodes: Annotated[int, Query(ge=1, le=1000)] = 200,
    include_stale: Annotated[bool, Query()] = True,
    workspace_id: Annotated[str | None, Query()] = None,
    topology: Annotated[bool, Query()] = False,
) -> dict:
    """Return nodes + edges + summary for the graph canvas.

    Collapsed view (topology=false, default):
      Nodes are Workspace and Project only.
      Child nodes (Session, Decision, etc.) appear as badge counts on Project nodes.
      Edges: MEMBER_OF (structural hierarchy) + CROSS_SERVICE_LINK / AFFECTS (signal).

    Topology view (topology=true):
      Nodes include EntityFact nodes (services, topics, features, data stores).
      Edges include BELONGS_TO, PRODUCES, CONSUMES, READS, WRITES, INVOLVES, etc.
      Use this to see the force-directed service dependency graph.
    """
    now = datetime.now(UTC)

    async with driver.session(database=settings.neo4j_database) as session:
        # ── Q1: Workspace nodes ────────────────────────────────────────────────
        if workspace_id:
            ws_result = await session.run(
                "MATCH (w:Workspace) WHERE w.id = $workspace_id RETURN w.id AS id, w.name AS name",
                workspace_id=workspace_id,
            )
        else:
            ws_result = await session.run(
                "MATCH (w:Workspace) RETURN w.id AS id, w.name AS name LIMIT $max_nodes",
                max_nodes=max_nodes,
            )
        workspace_rows = [dict(r) async for r in ws_result]

        # ── Q2: Project nodes with child badge counts ──────────────────────────
        if workspace_id:
            proj_result = await session.run(
                """
                MATCH (p:Project)-[:MEMBER_OF]->(w:Workspace {id: $workspace_id})
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
                workspace_id=workspace_id,
                max_nodes=max_nodes,
            )
        else:
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

        # ── Q4b: Topology view — EntityFact nodes and dependency edges ───────────
        entity_nodes: list[dict] = []
        topo_service_nodes: list[dict] = []
        topology_edges: list[dict] = []
        if topology:
            # Scope entity nodes to workspace if provided.
            # Follows BELONGS_TO → Project → MEMBER_OF → Workspace chain.
            # Falls back to p.workspace_id property for register_service-created projects.
            # Topology entity cap is intentionally higher than max_nodes (the project-node cap).
            # Edge visibility requires BOTH endpoints to be in visible_ids — loading only
            # max_nodes (200) entities would silently filter out most topology edges.
            topo_node_cap = 5000
            if workspace_id:
                ent_result = await session.run(
                    """
                    MATCH (e:EntityFact)-[:BELONGS_TO]->(p:Project)
                    WHERE (
                      p.workspace_id = $workspace_id
                      OR p.id = $workspace_id
                      OR EXISTS { MATCH (p)-[:MEMBER_OF]->(w:Workspace {id: $workspace_id}) }
                    )
                    RETURN e.id AS id, e.entity_name AS name, e.fact AS fact,
                           e.scope AS scope
                    LIMIT $topo_cap
                    """,
                    workspace_id=workspace_id,
                    topo_cap=topo_node_cap,
                )
            else:
                ent_result = await session.run(
                    """
                    MATCH (e:EntityFact)
                    RETURN e.id AS id, e.entity_name AS name, e.fact AS fact,
                           e.scope AS scope
                    LIMIT $topo_cap
                    """,
                    topo_cap=topo_node_cap,
                )
            entity_nodes = [dict(r) async for r in ent_result]

            # ── Q4c: First-class topology nodes (Service, DataSource, MessageQueue,
            # Feature, BoundedContext). These are NOT EntityFact — they are separate
            # node types created by the topology tools. Scoped to workspace_id if given.
            if workspace_id:
                topo_node_result = await session.run(
                    """
                    MATCH (n)
                    WHERE (n:DataSource OR n:MessageQueue OR n:Feature OR n:BoundedContext)
                      AND n.workspace_id = $workspace_id
                    RETURN n.id AS id, n.name AS name,
                           labels(n) AS node_labels,
                           n.service_type AS service_type,
                           n.source_type AS source_type,
                           n.queue_type AS queue_type,
                           n.health_status AS health_status,
                           n.bounded_context AS bounded_context,
                           n.domain AS domain
                    LIMIT $topo_cap
                    """,
                    workspace_id=workspace_id,
                    topo_cap=topo_node_cap,
                )
            else:
                topo_node_result = await session.run(
                    """
                    MATCH (n)
                    WHERE n:DataSource OR n:MessageQueue OR n:Feature OR n:BoundedContext
                    RETURN n.id AS id, n.name AS name,
                           labels(n) AS node_labels,
                           n.service_type AS service_type,
                           n.source_type AS source_type,
                           n.queue_type AS queue_type,
                           n.health_status AS health_status,
                           n.bounded_context AS bounded_context,
                           n.domain AS domain
                    LIMIT $topo_cap
                    """,
                    topo_cap=topo_node_cap,
                )
            topo_service_nodes = [dict(r) async for r in topo_node_result]

            # Topology edges — scope to the loaded entity IDs so the query planner can
            # use node index lookups rather than scanning all EntityFact pairs.
            loaded_entity_ids = [e["id"] for e in entity_nodes if e.get("id")]
            topo_result = await session.run(
                """
                MATCH (src:EntityFact)-[r]->(tgt:EntityFact)
                WHERE type(r) IN $topo_types
                  AND src.id IN $entity_ids AND tgt.id IN $entity_ids
                RETURN src.id AS source, tgt.id AS target, type(r) AS type
                LIMIT 5000
                """,
                topo_types=_TOPOLOGY_EDGE_TYPES,
                entity_ids=loaded_entity_ids,
            )
            topology_edges = [dict(r) async for r in topo_result]

            # ── Q4d: Edges from first-class topology nodes (Service, DataSource, etc.)
            # Uses workspace-scoped node IDs to bound the edge scan.
            topo_node_ids = [n["id"] for n in topo_service_nodes if n.get("id")]
            # Also include Service nodes already captured as project_rows (dual-label).
            service_ids_from_projects = [
                row["project"]["id"]
                for row in project_rows
                if "Service" in (row["project"].get("_labels") or [])
            ]
            all_topo_ids = list(set(loaded_entity_ids + topo_node_ids + service_ids_from_projects))
            if all_topo_ids:
                topo_edge_result = await session.run(
                    """
                    MATCH (src)-[r]->(tgt)
                    WHERE type(r) IN $topo_types
                      AND src.id IN $ids AND tgt.id IS NOT NULL
                    RETURN src.id AS source, tgt.id AS target, type(r) AS type
                    LIMIT 5000
                    """,
                    topo_types=_TOPOLOGY_EDGE_TYPES,
                    ids=all_topo_ids,
                )
                topology_edges += [dict(r) async for r in topo_edge_result]

        # ── Q5: Per-label summary counts — single UNION ALL (1 RTT, was 13) ─────
        counts_query = "\nUNION ALL\n".join(
            f'MATCH (n:{lbl}) RETURN "{lbl}" AS lbl, count(n) AS cnt' for lbl in _SUMMARY_LABELS
        )
        counts_result = await session.run(counts_query)
        label_counts: dict[str, int] = {}
        async for r in counts_result:
            label_counts[r["lbl"]] = r["cnt"]
        for lbl in _SUMMARY_LABELS:
            label_counts.setdefault(lbl, 0)

        # ── Q6: Edge type distribution ─────────────────────────────────────────
        edge_dist_result = await session.run("MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c")
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
        workspace_nodes = [n for n in workspace_nodes if n["id"] in workspaces_with_visible]

    # Deduplicate by id — a node may carry multiple Neo4j labels (e.g. :Workspace:Project).
    # Workspace takes precedence since workspace_nodes is listed first.
    seen_ids: set[str] = set()
    all_nodes = []
    for n in workspace_nodes + project_nodes:
        if n["id"] not in seen_ids:
            seen_ids.add(n["id"])
            all_nodes.append(n)

    # In topology mode, add EntityFact nodes (deduplicated against Project/Workspace ids).
    if topology:
        for ent in entity_nodes:
            if ent["id"] and ent["id"] not in seen_ids:
                seen_ids.add(ent["id"])
                # Derive display category from entity_name prefix convention:
                # bc-* → BoundedContext, svc-* → Service, topic-* → Topic,
                # store-* → DataStore, ext-* → External, feature-* → Feature
                name = ent.get("name", "")
                prefix = name.split("-")[0] if "-" in name else ""
                category_map = {
                    "bc": "BoundedContext",
                    "svc": "Service",
                    "topic": "Topic",
                    "store": "DataStore",
                    "ext": "External",
                    "feature": "Feature",
                }
                category = category_map.get(prefix, "EntityFact")
                all_nodes.append(
                    {
                        "id": ent["id"],
                        "label": "EntityFact",
                        "category": category,
                        "display": name,
                        "fact": (ent.get("fact") or "")[:120],
                        "scope": ent.get("scope", ""),
                        "is_stale": False,
                        "staleness_days": None,
                        "badge_counts": None,
                    }
                )

        # Add first-class topology nodes (DataSource, MessageQueue, Feature, BoundedContext).
        # Service nodes appear as :Project:Service — they are already in project_nodes
        # and dedup via seen_ids. These pure infrastructure nodes need separate handling.
        label_priority = ["DataSource", "MessageQueue", "Feature", "BoundedContext"]
        for tnode in topo_service_nodes:
            if not tnode.get("id") or tnode["id"] in seen_ids:
                continue
            seen_ids.add(tnode["id"])
            node_labels = tnode.get("node_labels") or []
            # Pick most specific label using priority order
            label = next((lbl for lbl in label_priority if lbl in node_labels), "Topology")
            meta: dict = {}
            if label == "DataSource":
                meta["source_type"] = tnode.get("source_type")
            elif label == "MessageQueue":
                meta["queue_type"] = tnode.get("queue_type")
            elif label == "BoundedContext":
                meta["domain"] = tnode.get("domain")
            all_nodes.append(
                {
                    "id": tnode["id"],
                    "label": label,
                    "display": tnode.get("name") or tnode["id"],
                    "health_status": tnode.get("health_status"),
                    "is_stale": False,
                    "staleness_days": None,
                    "badge_counts": None,
                    **meta,
                }
            )

    # ── Build edge list ────────────────────────────────────────────────────────
    # Only include edges whose both endpoints are in the visible node set.
    visible_ids = {n["id"] for n in all_nodes}
    base_edges = member_edges + signal_edges
    if topology:
        base_edges = base_edges + topology_edges
    all_edges = [
        e for e in base_edges if e.get("source") in visible_ids and e.get("target") in visible_ids
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
            "topology_mode": topology,
        },
    }
