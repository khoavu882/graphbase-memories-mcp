"""
FederationEngine — service registration, liveness, and cross-service search.

AD-7: workspace_id is always normalized to lowercase at the engine layer.
AD-8: CrossServiceLinkType enum is validated in Python before any Cypher write.
B-2:  This module owns register/deregister/list; cross-service linking is in
      create_cross_service_link (separate from intra-project entity linking).
"""

from __future__ import annotations

from neo4j import AsyncDriver

from graphbase_memories.domain.enums import CrossServiceLinkType, RetrievalStatus, SaveStatus
from graphbase_memories.domain.results import (
    CrossServiceBundle,
    CrossServiceItem,
    SaveResult,
    ServiceInfo,
    ServiceListResult,
    ServiceRegistrationResult,
)
from graphbase_memories.graph.models import ProjectNode
from graphbase_memories.graph.repositories import federation_repo


def _to_service_info(p: ProjectNode) -> ServiceInfo:
    return ServiceInfo(
        service_id=p.id,
        display_name=p.display_name or p.name,
        workspace_id=p.workspace_id,
        status=p.status,
        last_seen=p.last_seen,
        tags=p.tags,
    )


async def register_service(
    service_id: str,
    workspace_id: str,
    display_name: str | None,
    description: str | None,
    tags: list[str],
    driver: AsyncDriver,
    database: str,
) -> ServiceRegistrationResult:
    workspace_id = workspace_id.lower().strip()  # AD-7
    project, _workspace, workspace_created = await federation_repo.register_service(
        service_id=service_id,
        workspace_id=workspace_id,
        display_name=display_name,
        description=description,
        tags=tags,
        driver=driver,
        database=database,
    )
    return ServiceRegistrationResult(
        service_info=_to_service_info(project),
        workspace_created=workspace_created,
        status=SaveStatus.saved,
    )


async def deregister_service(
    service_id: str,
    driver: AsyncDriver,
    database: str,
) -> ServiceInfo:
    project = await federation_repo.deregister_service(
        service_id=service_id,
        driver=driver,
        database=database,
    )
    return _to_service_info(project)


async def list_services(
    workspace_id: str,
    max_idle_minutes: int,
    driver: AsyncDriver,
    database: str,
) -> ServiceListResult:
    workspace_id = workspace_id.lower().strip()  # AD-7
    projects = await federation_repo.list_active_services(
        workspace_id=workspace_id,
        max_idle_minutes=max_idle_minutes,
        driver=driver,
        database=database,
    )
    status = RetrievalStatus.empty if not projects else RetrievalStatus.succeeded
    return ServiceListResult(
        services=[_to_service_info(p) for p in projects],
        workspace_id=workspace_id,
        retrieval_status=status,
    )


async def search_cross_service(
    query: str,
    workspace_id: str,
    target_project_ids: list[str] | None,
    node_types: list[str] | None,
    limit: int,
    driver: AsyncDriver,
    database: str,
) -> CrossServiceBundle:
    workspace_id = workspace_id.lower().strip()  # AD-7
    raw: list[dict] = []

    search_all = node_types is None
    if search_all or "EntityFact" in node_types:
        raw += await federation_repo.search_entities(
            query=query,
            workspace_id=workspace_id,
            target_project_ids=target_project_ids,
            limit=limit,
            driver=driver,
            database=database,
        )
    if search_all or "Decision" in node_types:
        raw += await federation_repo.search_decisions(
            query=query,
            workspace_id=workspace_id,
            target_project_ids=target_project_ids,
            limit=limit,
            driver=driver,
            database=database,
        )

    # Re-rank merged results by score desc, cap at limit
    raw.sort(key=lambda r: float(r.get("score", 0)), reverse=True)
    raw = raw[:limit]

    queried_projects = list({r["source_project"] for r in raw if r.get("source_project")})
    items = []
    for r in raw:
        node = dict(r["node"]) if r.get("node") else {}
        node_type = r.get("node_type", "Unknown")
        if node_type == "EntityFact":
            summary = f"{node.get('entity_name', '')}: {node.get('fact', '')}"
        else:
            summary = node.get("title", node.get("id", ""))
        items.append(
            CrossServiceItem(
                node_id=node.get("id", ""),
                node_type=node_type,
                source_project=r.get("source_project", ""),
                score=float(r.get("score", 0)),
                summary=summary,
            )
        )

    status = RetrievalStatus.empty if not items else RetrievalStatus.succeeded
    return CrossServiceBundle(
        items=items,
        total_count=len(items),
        queried_projects=queried_projects,
        retrieval_status=status,
    )


async def create_cross_service_link(
    source_entity_id: str,
    target_entity_id: str,
    link_type: str,
    rationale: str,
    confidence: float,
    created_by: str | None,
    driver: AsyncDriver,
    database: str,
) -> SaveResult:
    # Step 1 — validate enum (AD-8)
    if link_type not in CrossServiceLinkType.__members__.values():
        raise ValueError(
            f"Invalid link_type: {link_type!r}. "
            f"Must be one of: {[e.value for e in CrossServiceLinkType]}"
        )

    # Step 2-3 — resolve owning projects
    source_project = await federation_repo.get_node_project(
        node_id=source_entity_id, driver=driver, database=database
    )
    target_project = await federation_repo.get_node_project(
        node_id=target_entity_id, driver=driver, database=database
    )

    # Step 4 — node not found
    if source_project is None or target_project is None:
        missing = source_entity_id if source_project is None else target_entity_id
        return SaveResult(status=SaveStatus.failed, message=f"node not found: {missing!r}")

    # Step 5 — same-project rejection
    if source_project == target_project:
        return SaveResult(
            status=SaveStatus.failed,
            message=f"same-project links blocked (both in {source_project!r})",
        )

    # Step 6 — duplicate check
    already_exists = await federation_repo.check_csl_exists(
        source_id=source_entity_id,
        target_id=target_entity_id,
        link_type=link_type,
        driver=driver,
        database=database,
    )
    if already_exists:
        return SaveResult(status=SaveStatus.duplicate_skip)

    # Step 7 — default created_by
    created_by = created_by or "unknown"

    # Step 8 — write
    await federation_repo.create_cross_service_link(
        source_id=source_entity_id,
        target_id=target_entity_id,
        link_type=link_type,
        rationale=rationale,
        confidence=confidence,
        created_by=created_by,
        driver=driver,
        database=database,
    )
    return SaveResult(status=SaveStatus.saved)
