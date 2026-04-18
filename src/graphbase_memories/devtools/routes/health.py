"""Graph health routes — node/relationship counts, workspace health, conflict detection."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from graphbase_memories.config import settings
from graphbase_memories.devtools.deps import DriverDep
from graphbase_memories.engines import impact as impact_engine

router = APIRouter(tags=["health"])

_NODE_LABELS = [
    "Project",
    "Session",
    "Decision",
    "Pattern",
    "Context",
    "EntityFact",
    "Workspace",
    "ImpactEvent",
]
_REL_TYPES = [
    "BELONGS_TO",
    "MEMBER_OF",
    "CROSS_SERVICE_LINK",
    "IMPACT_OF",
    "PRODUCES",
    "CONSUMES",
    "READS",
    "WRITES",
    "INVOLVES",
    "CONFLICTS_WITH",
    "MERGES_INTO",
]


@router.get("/graph/stats")
async def graph_stats(driver: DriverDep):
    """Return node counts by label and relationship counts by type."""
    now = datetime.now(UTC)

    # Build two UNION ALL queries instead of N individual round-trips (was 19).
    # Note: when a label/rel-type has zero matches, Neo4j returns no row for that
    # subquery (MATCH with a grouped RETURN emits nothing on empty input). We
    # pre-initialize both dicts so zero-count entries are always present.
    node_union = "\nUNION ALL\n".join(
        f"MATCH (n:{lbl}) RETURN '{lbl}' AS name, count(n) AS cnt" for lbl in _NODE_LABELS
    )
    rel_union = "\nUNION ALL\n".join(
        f"MATCH ()-[r:{rt}]->() RETURN '{rt}' AS name, count(r) AS cnt" for rt in _REL_TYPES
    )

    node_counts: dict[str, int] = {lbl: 0 for lbl in _NODE_LABELS}
    rel_counts: dict[str, int] = {rt: 0 for rt in _REL_TYPES}

    async with driver.session(database=settings.neo4j_database) as session:
        node_result = await session.run(node_union)
        async for rec in node_result:
            node_counts[rec["name"]] = rec["cnt"]

        rel_result = await session.run(rel_union)
        async for rec in rel_result:
            rel_counts[rec["name"]] = rec["cnt"]

    return {
        "node_counts": node_counts,
        "relationship_counts": rel_counts,
        "checked_at": now.isoformat(),
    }


@router.get("/graph/stats/workspace/{workspace_id}")
async def workspace_health(workspace_id: str, driver: DriverDep):
    """Return health metrics for all services in a workspace."""
    try:
        report = await impact_engine.graph_health(workspace_id, driver, settings.neo4j_database)
        return report.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/graph/conflicts/{workspace_id}")
async def workspace_conflicts(workspace_id: str, driver: DriverDep, limit: int = 100):
    """Return CONTRADICTS cross-service links in a workspace.

    Deprecated: conflict_records are now included in GET /graph/stats/workspace/{workspace_id}.
    This endpoint remains for backwards compatibility.
    """
    try:
        conflicts = await impact_engine.detect_conflicts(
            workspace_id, limit, driver, settings.neo4j_database
        )
        return [c.model_dump() for c in conflicts]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/graph/repair/orphaned-entities/{workspace_id}")
async def repair_orphaned_entities(workspace_id: str, driver: DriverDep):
    """
    Repair EntityFact nodes that are not linked to any Project.

    This happens when upsert_entity_with_deps is called with a workspace_id
    instead of a project/service_id. The MATCH (proj:Project {id: workspace_id})
    fails silently, leaving entities unlinked.

    This repair finds orphaned EntityFact nodes and links them to any Project
    in the given workspace.
    """
    async with driver.session(database=settings.neo4j_database) as session:
        # Count orphaned entities first
        count_result = await session.run(
            """
            MATCH (e:EntityFact)
            WHERE NOT EXISTS { MATCH (e)-[:BELONGS_TO]->(:Project) }
            RETURN count(e) AS orphaned
            """
        )
        count_rec = await count_result.single()
        orphaned_count = count_rec["orphaned"] if count_rec else 0

        if orphaned_count == 0:
            return {"repaired": 0, "message": "No orphaned entities found."}

        # Find any active project in this workspace to link to
        proj_result = await session.run(
            """
            MATCH (p:Project)-[:MEMBER_OF]->(w:Workspace {id: $workspace_id})
            RETURN p.id AS project_id LIMIT 1
            """,
            workspace_id=workspace_id.lower(),
        )
        proj_rec = await proj_result.single()
        if not proj_rec:
            raise HTTPException(
                status_code=404,
                detail=f"No projects found in workspace '{workspace_id}'. "
                "Run register_service first.",
            )
        target_project_id = proj_rec["project_id"]

        # Link all orphaned entities to the found project
        repair_result = await session.run(
            """
            MATCH (e:EntityFact)
            WHERE NOT EXISTS { MATCH (e)-[:BELONGS_TO]->(:Project) }
            MATCH (p:Project {id: $project_id})
            MERGE (e)-[:BELONGS_TO]->(p)
            RETURN count(e) AS repaired
            """,
            project_id=target_project_id,
        )
        repair_rec = await repair_result.single()
        repaired = repair_rec["repaired"] if repair_rec else 0

    return {
        "repaired": repaired,
        "linked_to_project": target_project_id,
        "workspace_id": workspace_id,
        "message": f"Linked {repaired} orphaned EntityFact nodes to project '{target_project_id}'.",
    }
