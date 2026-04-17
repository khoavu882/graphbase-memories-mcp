"""
ImpactEngine — BFS-based cross-service impact propagation, health reporting, and conflict detection.

AD-4: BFS executed in Python (not Cypher APOC) to guarantee ordered depth grouping.
B-3:  fetch_batch_neighbors issues 1 Cypher round-trip per depth level (batch query).
      N sequential calls per frontier is explicitly avoided.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from neo4j import AsyncDriver

from graphbase_memories.graph.repositories import federation_repo, impact_repo
from graphbase_memories.mcp.schemas.errors import ErrorCode, MCPError
from graphbase_memories.mcp.schemas.results import (
    AffectedServiceItem,
    ConflictRecord,
    ImpactReport,
    WorkspaceHealthReport,
    WorkspaceServiceHealth,
)

RISK_BY_DEPTH: dict[int, str] = {1: "HIGH", 2: "MEDIUM", 3: "LOW"}
RISK_ORDER: dict[str, int] = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _max_risk(a: str, b: str) -> str:
    return a if RISK_ORDER.get(a, 0) >= RISK_ORDER.get(b, 0) else b


async def propagate_impact(
    entity_id: str,
    change_description: str,
    impact_type: str,
    max_depth: int,
    driver: AsyncDriver,
    database: str,
) -> ImpactReport | MCPError:
    # ── Pre-check — entity existence (moved from tool layer) ─────────────
    async with driver.session(database=database) as session:
        result = await session.run(
            "MATCH (n {id: $id}) RETURN count(n) AS cnt LIMIT 1",
            id=entity_id,
        )
        record = await result.single()
        if not record or record["cnt"] == 0:
            return MCPError(
                code=ErrorCode.ENTITY_NOT_FOUND,
                message=f"Entity '{entity_id}' not found in the graph.",
                context={"entity_id": entity_id},
                next_step="Call upsert_entity_with_deps() to create the entity first.",
            )

    # ── Phase 1 — BFS (B-3: one Cypher per depth level) ──────────────────
    frontier: set[str] = {entity_id}
    visited: dict[str, dict] = {}
    # visited[node_id] = {"depth": int, "project_id": str, "edge_types": set[str]}

    for depth in range(1, max_depth + 1):
        if not frontier:
            break
        batch = await impact_repo.fetch_batch_neighbors(list(frontier), driver, database)
        next_frontier: set[str] = set()
        for rec in batch:
            if rec.id not in visited:
                visited[rec.id] = {
                    "depth": depth,
                    "project_id": rec.project_id,
                    "edge_types": {rec.edge_type},
                }
                next_frontier.add(rec.id)
            else:
                visited[rec.id]["edge_types"].add(rec.edge_type)
        frontier = next_frontier

    # ── Phase 2 — Risk scoring ────────────────────────────────────────────
    project_risks: dict[str, str] = {}
    for info in visited.values():
        pid = info["project_id"]
        risk = RISK_BY_DEPTH.get(info["depth"], "LOW")
        if "CONTRADICTS" in info["edge_types"]:
            risk = "CRITICAL"
        project_risks[pid] = _max_risk(project_risks.get(pid, "LOW"), risk)

    overall_risk = "LOW"
    if project_risks:
        overall_risk = max(project_risks.values(), key=lambda r: RISK_ORDER.get(r, 0))

    # ── Phase 3 — Atomic ImpactEvent write ───────────────────────────────
    source_project_id = await federation_repo.get_node_project(
        node_id=entity_id, driver=driver, database=database
    )

    # Build min-depth per project for the affected list
    project_min_depth: dict[str, int] = {}
    for info in visited.values():
        pid = info["project_id"]
        project_min_depth[pid] = min(project_min_depth.get(pid, info["depth"]), info["depth"])

    affected_list = [
        {"project_id": pid, "depth": project_min_depth[pid], "risk_level": risk}
        for pid, risk in project_risks.items()
    ]
    event_node = await impact_repo.write_impact_event(
        event_id=str(uuid4()),
        source_entity_id=entity_id,
        source_project_id=source_project_id or "unknown",
        change_description=change_description,
        impact_type=impact_type,
        risk_level=overall_risk,
        affected=affected_list,
        driver=driver,
        database=database,
    )

    # ── Phase 4 — Build ImpactReport ─────────────────────────────────────
    affected_services = [
        AffectedServiceItem(
            project_id=pid,
            depth=project_min_depth[pid],
            risk_level=project_risks[pid],
            entity_count=sum(1 for info in visited.values() if info["project_id"] == pid),
        )
        for pid in project_risks
    ]

    if overall_risk in ("CRITICAL", "HIGH"):
        impact_next_step = (
            "HIGH RISK: call detect_conflicts(workspace_id=...) before proceeding with writes."
        )
    elif overall_risk == "MEDIUM":
        impact_next_step = (
            "Review affected_services and call retrieve_context on each impacted project_id."
        )
    else:
        impact_next_step = "Impact is contained. Proceed with upsert_entity_with_deps()."

    return ImpactReport(
        source_entity_id=entity_id,
        change_description=change_description,
        impact_type=impact_type,
        overall_risk=overall_risk,
        affected_services=affected_services,
        impact_event_id=event_node.id,
        created_at=event_node.created_at,
        next_step=impact_next_step,
    )


async def graph_health(
    workspace_id: str,
    driver: AsyncDriver,
    database: str,
    include_conflicts: bool = True,
) -> WorkspaceHealthReport:
    workspace_id = workspace_id.lower().strip()
    records = await impact_repo.graph_health(
        workspace_id=workspace_id, driver=driver, database=database
    )

    now = datetime.now(UTC)
    services: list[WorkspaceServiceHealth] = []
    for r in records:
        p = dict(r["p"])
        last_hygiene = p.get("last_hygiene_at")

        staleness_days: float | None = None
        if last_hygiene is not None:
            from graphbase_memories.graph.models import _dt

            lh = _dt(last_hygiene)
            if lh is not None:
                staleness_days = (
                    now - lh.replace(tzinfo=UTC) if lh.tzinfo is None else now - lh
                ).days

        conflict_count = int(r.get("conflict_count", 0))
        if conflict_count > 0:
            hygiene_status = "critical"
        elif last_hygiene is None or (staleness_days is not None and staleness_days > 30):
            hygiene_status = "needs_hygiene"
        else:
            hygiene_status = "clean"

        services.append(
            WorkspaceServiceHealth(
                service_id=p["id"],
                entity_count=int(r.get("entity_count", 0)),
                decision_count=int(r.get("decision_count", 0)),
                pattern_count=int(r.get("pattern_count", 0)),
                conflict_count=conflict_count,
                staleness_days=staleness_days,
                hygiene_status=hygiene_status,
            )
        )

    total_conflicts = sum(s.conflict_count for s in services)

    # Absorb detect_conflicts when include_conflicts=True
    conflict_records: list[ConflictRecord] = []
    if include_conflicts and total_conflicts > 0:
        conflict_records = await detect_conflicts(workspace_id, limit=100, driver=driver, database=database)

    if total_conflicts > 0:
        health_next_step = (
            "Conflicts detected: inspect conflict_records and resolve CONTRADICTS edges."
        )
    elif any(s.hygiene_status in ("needs_hygiene", "critical") for s in services):
        health_next_step = (
            "Hygiene needed: call run_hygiene() on services with needs_hygiene or critical status."
        )
    else:
        health_next_step = "Workspace is healthy. No immediate action required."

    return WorkspaceHealthReport(
        workspace_id=workspace_id,
        service_count=len(services),
        services=services,
        total_conflicts=total_conflicts,
        checked_at=now,
        next_step=health_next_step,
        conflict_records=conflict_records,
    )


async def detect_conflicts(
    workspace_id: str,
    limit: int,
    driver: AsyncDriver,
    database: str,
) -> list[ConflictRecord]:
    workspace_id = workspace_id.lower().strip()
    records = await impact_repo.detect_conflicts(
        workspace_id=workspace_id, limit=limit, driver=driver, database=database
    )

    results: list[ConflictRecord] = []
    for r in records:
        src = dict(r["src"]) if r.get("src") else {}
        tgt = dict(r["tgt"]) if r.get("tgt") else {}

        src_summary = src.get("entity_name") or src.get("title") or src.get("id", "")
        tgt_summary = tgt.get("entity_name") or tgt.get("title") or tgt.get("id", "")

        results.append(
            ConflictRecord(
                source_id=src.get("id", ""),
                source_project=r.get("project_a", ""),
                source_summary=src_summary,
                target_id=tgt.get("id", ""),
                target_project=r.get("project_b", ""),
                target_summary=tgt_summary,
                link_rationale=r.get("link_rationale"),
                link_confidence=r.get("link_confidence"),
            )
        )
    return results
