"""
Federation repository — service registration, liveness, and cross-service link management.

AD-7: workspace_id is normalized to lowercase at this layer (enforced before Cypher).
AD-8: CrossServiceLinkType enum must be validated in Python before MERGE.
B-1: REGISTER_SERVICE uses a single Cypher statement (chained WITH) for atomicity.
"""

from __future__ import annotations

import re

from neo4j import AsyncDriver

from graphbase_memories.graph.driver import FEDERATION_QUERIES
from graphbase_memories.graph.models import ProjectNode, WorkspaceNode
from graphbase_memories.mcp.schemas.enums import CrossServiceLinkType


# Named query extractor — matches "// == NAME ==" blocks split by semicolons
def _query(name: str) -> str:
    pattern = rf"//\s*==\s*{re.escape(name)}\s*==\s*\n(.*?)(?=\n//\s*==|\Z)"
    m = re.search(pattern, FEDERATION_QUERIES, re.DOTALL)
    if not m:
        raise KeyError(f"Query block '{name}' not found in federation.cypher")
    return m.group(1).strip().rstrip(";")


_REGISTER_SERVICE = _query("REGISTER_SERVICE")
_DEREGISTER_SERVICE = _query("DEREGISTER_SERVICE")
_LIST_ACTIVE = _query("LIST_ACTIVE_SERVICES")
_SEARCH_ENTITIES = _query("SEARCH_ENTITIES")
_SEARCH_DECISIONS = _query("SEARCH_DECISIONS")
_CREATE_CSL = _query("CREATE_CROSS_SERVICE_LINK")
_GET_NODE_PROJECT = _query("GET_NODE_PROJECT")
_CHECK_CSL_EXISTS = _query("CHECK_CSL_EXISTS")


async def register_service(
    *,
    service_id: str,
    workspace_id: str,
    display_name: str | None,
    description: str | None,
    tags: list[str],
    driver: AsyncDriver,
    database: str = "neo4j",
) -> tuple[ProjectNode, WorkspaceNode, bool]:
    """
    Register (or re-activate) a service in a workspace.
    Returns (ProjectNode, WorkspaceNode, workspace_created).
    workspace_id is normalized to lowercase before write (AD-7).
    Uses single-statement Cypher for atomicity (B-1).
    """
    workspace_id = workspace_id.lower().strip()

    async def _tx(tx):
        await tx.run(
            _REGISTER_SERVICE,
            service_id=service_id,
            workspace_id=workspace_id,
            display_name=display_name or service_id,
            description=description,
            tags=tags,
        )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)

    # Read back both nodes after write (execute_write discards return value)
    async with driver.session(database=database) as session:
        result = await session.run(
            """
            MATCH (p:Project {id: $sid})
            MATCH (w:Workspace {id: $wid})
            RETURN p, w, (w.created_at = p.last_seen) AS workspace_created
            """,
            sid=service_id,
            wid=workspace_id,
        )
        record = await result.single()

    project = ProjectNode.from_record(dict(record["p"]))
    workspace = WorkspaceNode.from_record(dict(record["w"]))
    workspace_created = bool(record["workspace_created"])
    return project, workspace, workspace_created


async def deregister_service(
    *,
    service_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> ProjectNode:
    """Set service status to 'idle'. Returns updated ProjectNode."""

    async def _tx(tx):
        await tx.run(_DEREGISTER_SERVICE, service_id=service_id)

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)

    async with driver.session(database=database) as session:
        result = await session.run("MATCH (p:Project {id: $sid}) RETURN p", sid=service_id)
        record = await result.single()

    if record is None:
        raise ValueError(f"Service not found: {service_id!r}")
    return ProjectNode.from_record(dict(record["p"]))


async def list_active_services(
    *,
    workspace_id: str,
    max_idle_minutes: int,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[ProjectNode]:
    """Return active services in the workspace ordered by last_seen desc."""
    workspace_id = workspace_id.lower().strip()
    async with driver.session(database=database) as session:
        result = await session.run(
            _LIST_ACTIVE,
            workspace_id=workspace_id,
            max_idle_minutes=max_idle_minutes,
        )
        records = await result.data()
    return [ProjectNode.from_record(dict(r["p"])) for r in records]


async def search_entities(
    *,
    query: str,
    workspace_id: str,
    target_project_ids: list[str] | None,
    limit: int,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[dict]:
    """Full-text search across EntityFact nodes in the workspace."""
    workspace_id = workspace_id.lower().strip()
    async with driver.session(database=database) as session:
        result = await session.run(
            _SEARCH_ENTITIES,
            search_query=query,
            workspace_id=workspace_id,
            target_project_ids=target_project_ids,
            limit=limit,
        )
        return await result.data()


async def search_decisions(
    *,
    query: str,
    workspace_id: str,
    target_project_ids: list[str] | None,
    limit: int,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> list[dict]:
    """Full-text search across Decision nodes in the workspace."""
    workspace_id = workspace_id.lower().strip()
    async with driver.session(database=database) as session:
        result = await session.run(
            _SEARCH_DECISIONS,
            search_query=query,
            workspace_id=workspace_id,
            target_project_ids=target_project_ids,
            limit=limit,
        )
        return await result.data()


async def get_node_project(
    *,
    node_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> str | None:
    """Return the project_id that owns the given node, or None."""
    async with driver.session(database=database) as session:
        result = await session.run(_GET_NODE_PROJECT, node_id=node_id)
        record = await result.single()
    return record["project_id"] if record else None


async def check_csl_exists(
    *,
    source_id: str,
    target_id: str,
    link_type: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> bool:
    """Return True if a CROSS_SERVICE_LINK of this type already exists."""
    async with driver.session(database=database) as session:
        result = await session.run(
            _CHECK_CSL_EXISTS,
            source_id=source_id,
            target_id=target_id,
            link_type=link_type,
        )
        record = await result.single()
    return bool(record and record["count"] > 0)


async def create_cross_service_link(
    *,
    source_id: str,
    target_id: str,
    link_type: str,
    rationale: str,
    confidence: float,
    created_by: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> None:
    """
    Create a CROSS_SERVICE_LINK edge. link_type must be a valid CrossServiceLinkType (AD-8).
    Caller is responsible for: enum validation, same-project rejection, duplicate check.
    """
    if link_type not in CrossServiceLinkType.__members__.values():
        raise ValueError(
            f"Invalid link_type: {link_type!r}. "
            f"Must be one of: {[e.value for e in CrossServiceLinkType]}"
        )

    async def _tx(tx):
        await tx.run(
            _CREATE_CSL,
            source_id=source_id,
            target_id=target_id,
            link_type=link_type,
            rationale=rationale,
            confidence=confidence,
            created_by=created_by,
        )

    async with driver.session(database=database) as session:
        await session.execute_write(_tx)
