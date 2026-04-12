"""MCP prompts: reusable agent workflow templates exposed via prompts/get RPC.

Prompts differ from tools — they return Message sequences that guide agents
through multi-step workflows rather than returning data directly.
"""

from __future__ import annotations

from fastmcp import Context
from fastmcp.prompts import Message

from graphbase_memories.mcp.server import mcp

# ── memory_review ─────────────────────────────────────────────────────────────


@mcp.prompt()
async def memory_review(
    ctx: Context,
    project_id: str,
    scope: str = "project",
) -> list[Message]:
    """Guided workflow: retrieve, assess freshness, and flag hygiene needs for a project."""
    return [
        Message(
            role="user",
            content=(
                f"You are reviewing the memory graph for project '{project_id}' "
                f"with scope '{scope}'. Follow these steps:\n\n"
                "1. Call `retrieve_context(project_id, scope)` to load current memories.\n"
                "2. Call `memory_freshness(project_id=project_id)` to identify stale nodes.\n"
                "3. If freshness report shows `stale_count > 0`, call `run_hygiene(project_id)` "
                "   and summarise what was archived or updated.\n"
                "4. Report a brief summary: how many decisions, patterns, and entity facts "
                "   are active, how many are stale, and what the next recommended action is.\n\n"
                "Do not modify any memory content during this review — read-only assessment only."
            ),
        )
    ]


# ── impact_before_edit ────────────────────────────────────────────────────────


@mcp.prompt()
async def impact_before_edit(
    ctx: Context,
    entity_id: str,
    proposed_change: str,
) -> list[Message]:
    """Guided workflow: run impact analysis before modifying a graph entity."""
    return [
        Message(
            role="user",
            content=(
                f"Before modifying entity '{entity_id}', you must assess downstream impact.\n\n"
                f"Proposed change: {proposed_change}\n\n"
                "Steps:\n"
                f"1. Call `route_analysis(entity_id='{entity_id}', max_depth=2)` to map "
                "   which nodes depend on this entity.\n"
                "2. If any critical dependencies are found (impact_level = critical or high), "
                "   pause and report them to the user before proceeding.\n"
                "3. If the change is safe to proceed, call `request_governance_token()` "
                "   to obtain write authorization.\n"
                "4. Apply the change using the appropriate upsert tool "
                "   (e.g. `upsert_entity_with_deps`, `save_decision`).\n"
                "5. Call `propagate_impact_event` with a description of what changed.\n\n"
                "Never skip the governance token step for entities with critical dependents."
            ),
        )
    ]


# ── federated_sync ────────────────────────────────────────────────────────────


@mcp.prompt()
async def federated_sync(
    ctx: Context,
    source_service_id: str,
    workspace_id: str,
) -> list[Message]:
    """Guided workflow: synchronise cross-service entity links within a workspace."""
    return [
        Message(
            role="user",
            content=(
                f"You are performing a federated sync for service '{source_service_id}' "
                f"in workspace '{workspace_id}'.\n\n"
                "Steps:\n"
                "1. Read `graphbase://services` to list all active services in the workspace.\n"
                "2. Call `retrieve_context` for each peer service to identify shared concepts.\n"
                "3. For each shared entity, call `find_cross_service_links` to detect existing "
                "   links and gaps.\n"
                "4. Where gaps exist, call `link_cross_service_entities` with an appropriate "
                "   `link_type` (DEPENDS_ON, SHARES_CONCEPT, EXTENDS, or CONTRADICTS).\n"
                "5. After linking, call `detect_workspace_conflicts` to surface any "
                "   contradictions introduced by the new links.\n"
                "6. Report: how many new links were created, how many conflicts detected, "
                "   and which services now share the most cross-service entities.\n\n"
                "Use `CONTRADICTS` only when the entity facts are mutually exclusive across services."
            ),
        )
    ]
