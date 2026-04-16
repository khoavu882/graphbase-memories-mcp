"""
ScopeEngine — stateless per-call scope validation.
project_id is required on every tool call (no server-side session state).
"""

from __future__ import annotations

from neo4j import AsyncDriver

from graphbase_memories.mcp.schemas.enums import ScopeState


async def validate(
    project_id: str | None,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> ScopeState:
    """
    Resolve scope state for a given project_id.

    resolved   — project exists in graph
    uncertain  — project_id given but not yet registered in graph
    unresolved — no project_id provided

    focus is accepted for API compatibility but not validated —
    FocusArea nodes are auto-created on first write.
    """
    if not project_id:
        return ScopeState.unresolved

    async with driver.session(database=database) as session:
        result = await session.run(
            "MATCH (p:Project {id: $pid}) RETURN p.id AS id LIMIT 1",
            pid=project_id,
        )
        record = await result.single()

    if record is None:
        return ScopeState.uncertain

    # Project exists — scope is resolved.
    # Focus is auto-created on first write, so a missing FocusArea is not unresolved.
    return ScopeState.resolved


def is_write_allowed(scope_state: ScopeState) -> bool:
    """FR-13, FR-37: only resolved scope allows writes."""
    return scope_state == ScopeState.resolved


def is_read_allowed(scope_state: ScopeState) -> bool:
    """FR-10: reads allowed when scope is resolved or uncertain (with degraded context)."""
    return scope_state in (ScopeState.resolved, ScopeState.uncertain)


async def validate_workspace(
    workspace_id: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> ScopeState:
    """
    Validate that a Workspace node exists in the graph.

    resolved   — workspace exists
    unresolved — workspace_id missing or workspace not found

    Distinct from validate(): workspace is a topology-layer anchor, not a project.
    Returns unresolved (not uncertain) for missing workspace because there is no
    auto-creation path — callers must register the workspace explicitly first.
    """
    if not workspace_id:
        return ScopeState.unresolved

    async with driver.session(database=database) as session:
        result = await session.run(
            "MATCH (w:Workspace {id: $wid}) RETURN w.id AS id LIMIT 1",
            wid=workspace_id,
        )
        record = await result.single()

    return ScopeState.resolved if record is not None else ScopeState.unresolved
