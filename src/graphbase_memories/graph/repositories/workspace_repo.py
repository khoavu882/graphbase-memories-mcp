"""
Workspace repository — read-only queries for Workspace nodes.
Writes to Workspace happen exclusively through federation_repo.register_service
to keep the MEMBER_OF relationship atomic with the workspace MERGE.
"""

from __future__ import annotations

from neo4j import AsyncDriver

from graphbase_memories.graph.models import WorkspaceNode


async def get(
    workspace_id: str, driver: AsyncDriver, database: str = "neo4j"
) -> WorkspaceNode | None:
    """Return the Workspace node for the given id, or None if not found."""
    async with driver.session(database=database) as session:
        result = await session.run(
            "MATCH (w:Workspace {id: $workspace_id}) RETURN w",
            workspace_id=workspace_id,
        )
        record = await result.single()
    if record is None:
        return None
    return WorkspaceNode.from_record(dict(record["w"]))


async def list_all(driver: AsyncDriver, database: str = "neo4j") -> list[WorkspaceNode]:
    """Return all Workspace nodes ordered by id."""
    async with driver.session(database=database) as session:
        result = await session.run("MATCH (w:Workspace) RETURN w ORDER BY w.id")
        records = await result.data()
    return [WorkspaceNode.from_record(dict(r["w"])) for r in records]
