"""
Lifecycle tools: MCP tool registration for Phase 8 lifecycle APIs.

Thin wrappers that instantiate lifecycle objects and delegate to
domain methods. All lifecycle logic lives in the lifecycle/ package.

Tools registered:
  - resolve_active_project
  - ensure_project
  - get_lifecycle_context
  - save_session_context
  - list_available_tools
"""

from __future__ import annotations

from dataclasses import asdict

from fastmcp import FastMCP

from graphbase_memories.config import Config
from graphbase_memories.lifecycle.assembler import LifecycleContextAssembler
from graphbase_memories.lifecycle.coordinator import LifecycleCoordinator
from graphbase_memories.lifecycle.inventory import get_tool_inventory
from graphbase_memories.lifecycle.resolver import LifecycleProjectResolver
from graphbase_memories.tools._types import MemoryInput


def register_lifecycle_tools(mcp: FastMCP) -> None:
    """Register Phase 8 lifecycle orchestration tools."""

    # Lazy accessors — read provider's config at call time, not import time.
    # This is critical: server.py registers tools at module-load, but test
    # fixtures replace the provider config AFTER that via _set_config_for_test().
    def _get_config():
        from graphbase_memories._provider import _config
        return _config

    def _get_resolver():
        return LifecycleProjectResolver(_get_config())

    def _get_coordinator():
        return LifecycleCoordinator(_get_config(), _get_resolver())

    def _get_assembler():
        return LifecycleContextAssembler(_get_config())

    @mcp.tool()
    def resolve_active_project(
        workspace_root: str = "",
        cwd: str | None = None,
        project_override: str | None = None,
    ) -> dict:
        """
        Map the active workspace to a Graphbase project namespace.

        Callers must provide workspace_root or project_override.
        In stdio mode the MCP server cannot infer the active workspace.

        Args:
            workspace_root:   Absolute path to the repo/workspace root.
            cwd:              Optional current working directory (reserved for monorepo).
            project_override: Skip all heuristics — use this project ID directly.

        Returns:
            {project_id, project_slug, workspace_root, storage_path, exists, identity_mode}
        """
        try:
            resolved = _get_resolver().resolve(workspace_root, cwd, project_override)
            return asdict(resolved) | {"storage_path": str(resolved.storage_path)}
        except ValueError as exc:
            return {"error": "resolution_failed", "message": str(exc)}

    @mcp.tool()
    def ensure_project(
        project_id: str,
        workspace_root: str | None = None,
        initialize_context: bool = False,
    ) -> dict:
        """
        Create or validate project storage.

        If the project already exists, returns {created: false} without side effects.
        If new, creates the project directory, initialises the DB, and writes project.json.

        Args:
            project_id:         Canonical project identifier from resolve_active_project.
            workspace_root:     Workspace path (stored in project.json for future resolution).
            initialize_context: If true, seeds a bootstrap context memory.

        Returns:
            {project_id, created, db_initialized, context_seeded}
        """
        try:
            return _get_coordinator().ensure_project(project_id, workspace_root, initialize_context)
        except Exception as exc:
            return {"error": "ensure_failed", "message": str(exc)}

    @mcp.tool()
    def get_lifecycle_context(
        project_id: str,
        entity: str | None = None,
        entity_type: str = "service",
        max_tokens: int = 500,
        include_recent_sessions: bool = True,
        include_inventory: bool = True,
    ) -> dict:
        """
        Return startup-ready project context as a structured bundle.

        Provides both a prioritised YAML context block (for prompt injection)
        and structured fields (decisions, patterns, sessions, entities, stale warnings).

        Args:
            project_id:              Canonical project identifier.
            entity:                  Optional entity to scope context to.
            entity_type:             Type of the focus entity (default: "service").
            max_tokens:              Token budget for YAML context block.
            include_recent_sessions: Whether to include recent session list.
            include_inventory:       Whether to include tool inventory.

        Returns:
            {project_id, bootstrap_state, yaml_context, recent_sessions,
             decisions, patterns, entities, stale_warnings, tool_inventory}
        """
        try:
            ctx = _get_assembler().assemble(
                project_id, entity, entity_type, max_tokens,
                include_recent_sessions, include_inventory,
            )
            return asdict(ctx)
        except Exception as exc:
            return {"error": "context_assembly_failed", "message": str(exc)}

    @mcp.tool()
    def save_session_context(
        project_id: str,
        session: MemoryInput,
        decisions: list[MemoryInput],
        patterns: list[MemoryInput],
        context_items: list[MemoryInput] | None = None,
        entity_facts: list[dict] | None = None,
    ) -> dict:
        """
        High-level save endpoint for lifecycle skills.

        Stores a session memory with its decisions, patterns, optional context items,
        and optional entity facts. All items are linked via LEARNED_DURING edges.
        Decisions with matching prior titles get SUPERSEDES edges automatically.

        Precondition: ensure_project must have been called first.

        Args:
            project_id:    Canonical project identifier.
            session:       Session narrative {title, content, entities?, tags?}.
            decisions:     Decisions discovered this session.
            patterns:      Patterns observed this session.
            context_items: Optional context memories to link to the session.
            entity_facts:  Optional entity facts: {title, content, entity_name, entity_type?, tags?}.

        Returns:
            {session_id, decisions, patterns, context_items, entity_facts, errors}
            Or {error, message} if project is not initialized.
        """
        return _get_coordinator().save_session(
            project_id, session, decisions, patterns, context_items, entity_facts,
        )

    @mcp.tool()
    def list_available_tools() -> dict:
        """
        Return a categorized inventory of all available Graphbase MCP tools.

        Static — no project context required. Includes api_version for
        capability detection by agent skills.

        Returns:
            {api_version, write: [...], read: [...], lifecycle: [...], ...}
        """
        return get_tool_inventory()
