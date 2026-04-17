"""Federation tools: service registration and liveness management."""

from __future__ import annotations

from fastmcp import Context

from graphbase_memories.config import settings
from graphbase_memories.engines import federation as federation_engine
from graphbase_memories.mcp.schemas.results import (
    ServiceInfo,
    ServiceListResult,
    ServiceRegistrationResult,
)
from graphbase_memories.mcp.server import mcp


@mcp.tool()
async def register_federated_service(
    ctx: Context,
    service_id: str,
    workspace_id: str,
    display_name: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    active: bool = True,
) -> ServiceRegistrationResult | ServiceInfo:
    """
    Register (or re-activate) a service in a workspace.
    Creates the Workspace node if it does not exist.
    workspace_id is normalized to lowercase automatically.

    When active=False: marks the service as idle (deregistration path).
    Does not delete any data. Replaces the removed deregister_service tool.
    """
    driver = ctx.lifespan_context["driver"]
    if active:
        return await federation_engine.register_service(
            service_id,
            workspace_id,
            display_name,
            description,
            tags or [],
            driver,
            settings.neo4j_database,
        )
    return await federation_engine.deregister_service(service_id, driver, settings.neo4j_database)


@mcp.tool()
async def list_active_services(
    ctx: Context,
    workspace_id: str,
    max_idle_minutes: int = 60,
) -> ServiceListResult:
    """
    List all active services in a workspace.
    Services with last_seen older than max_idle_minutes are excluded.
    """
    driver = ctx.lifespan_context["driver"]
    return await federation_engine.list_services(
        workspace_id, max_idle_minutes, driver, settings.neo4j_database
    )
