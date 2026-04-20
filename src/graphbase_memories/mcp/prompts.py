"""MCP prompts: reusable agent workflow templates exposed via prompts/get RPC.

Prompts differ from tools — they return Message sequences that guide agents
through multi-step workflows rather than returning data directly.
"""

from __future__ import annotations

from fastmcp import Context
from fastmcp.prompts import Message

from graphbase_memories.mcp.server import mcp

# ── analysis_routing internals ────────────────────────────────────────────────

_SEQUENTIAL_KEYWORDS = {
    "strategic", "strategy", "multi-factor", "planning", "roadmap",
    "prioritize", "milestone", "initiative", "phase",
}
_DEBATE_KEYWORDS = {
    "trade-off", "tradeoff", "compare", "versus", "vs", "debate",
    "alternatives", "option", "choose", "decision between",
}
_SOCRATIC_KEYWORDS = {
    "unclear", "requirements", "discovery", "explore", "what do you mean",
    "clarify", "understand", "not sure", "ambiguous",
}
_SUGGESTED_STEPS: dict[str, list[str]] = {
    "sequential": [
        "1. Define the problem statement and success criteria.",
        "2. Gather relevant context from memory (retrieve_context).",
        "3. Break the problem into sequential steps or phases.",
        "4. Analyze each step for dependencies and risks.",
        "5. Synthesize conclusions and save durable decisions.",
    ],
    "debate": [
        "1. Enumerate the competing options or trade-offs.",
        "2. Retrieve prior decisions on similar trade-offs.",
        "3. Evaluate each option against criteria (cost, risk, fit).",
        "4. State the recommended option with rationale.",
        "5. Save the final decision with confidence score.",
    ],
    "socratic": [
        "1. Identify what is unclear or ambiguous in the request.",
        "2. Ask targeted clarifying questions (one at a time).",
        "3. Confirm understanding before proceeding.",
        "4. Restate requirements in your own words for validation.",
        "5. Proceed with analysis only after requirements are resolved.",
    ],
}


def _route_analysis(task_description: str, task_type_hint: str | None) -> tuple[str, str]:
    """Return (mode, rationale) for a task description."""
    text = (task_description + " " + (task_type_hint or "")).lower()
    if task_type_hint:
        hint = task_type_hint.lower()
        if any(k in hint for k in _SEQUENTIAL_KEYWORDS):
            return "sequential", "task_type_hint matched sequential keywords"
        if any(k in hint for k in _DEBATE_KEYWORDS):
            return "debate", "task_type_hint matched debate keywords"
        if any(k in hint for k in _SOCRATIC_KEYWORDS):
            return "socratic", "task_type_hint matched socratic keywords"
    debate_score = sum(1 for k in _DEBATE_KEYWORDS if k in text)
    socratic_score = sum(1 for k in _SOCRATIC_KEYWORDS if k in text)
    sequential_score = sum(1 for k in _SEQUENTIAL_KEYWORDS if k in text)
    if debate_score > max(sequential_score, socratic_score):
        return "debate", "task description suggests trade-off evaluation"
    if socratic_score > max(sequential_score, debate_score):
        return "socratic", "task description suggests requirements discovery"
    return "sequential", "default: structured multi-step analysis"


# ── analysis_routing ──────────────────────────────────────────────────────────


@mcp.prompt()
def analysis_routing(
    task_description: str,
    task_type_hint: str | None = None,
) -> list[Message]:
    """Route a task to the appropriate analysis mode (sequential/debate/socratic).

    Returns guidance messages describing which mode to enter and suggested steps.
    """
    mode, rationale = _route_analysis(task_description, task_type_hint)
    return [
        Message(
            role="user",
            content=(
                f"Analysis routing for: {task_description}\n\n"
                f"Recommended mode: {mode}\n"
                f"Rationale: {rationale}\n\n"
                "Suggested steps:\n"
                + "\n".join(f"  {s}" for s in _SUGGESTED_STEPS[mode])
            ),
        )
    ]


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
                "2. Call `run_hygiene(project_id=project_id)` — inspect `stale_items` in the "
                "   report to identify stale nodes.\n"
                "3. If the report shows `stale_count > 0` or `archived_count > 0`, "
                "   summarise what was archived or flagged.\n"
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
                f"1. Query the graph to map which nodes depend on entity '{entity_id}' "
                "   (traverse up to 2 hops and identify dependents with impact_level = critical or high).\n"
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
                "Use `CONTRADICTS` only when the entity facts are mutually exclusive"
                " across services."
            ),
        )
    ]
