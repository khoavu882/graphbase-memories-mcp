"""MCP resources: passive read-only context exposed via graphbase:// URIs.

Resources differ from tools — they are polled by agents to build context rather
than invoked to take action. All resources return YAML strings so agents can
parse them with standard YAML tooling or read them as plain text.
"""

from __future__ import annotations

import logging

from fastmcp import Context

from graphbase_memories.mcp.server import mcp

logger = logging.getLogger(__name__)


# ── graphbase://schema ────────────────────────────────────────────────────────

_SCHEMA_YAML = """
# graphbase — Graph Schema Reference
# Use this to construct Cypher queries in route_analysis tool.
#
# NOTE: Services are stored as :Project nodes with workspace metadata.
# A Project that has called register_service() has workspace_id, status,
# last_seen, display_name properties and links to :Workspace via [:MEMBER_OF].

node_labels:
  - Project        # id, name, workspace_id?, status?, last_seen?, last_hygiene_at
  - GlobalScope    # id="global" singleton
  - FocusArea      # name, project_id
  - Session        # id, status, content, created_at, updated_at
  - Decision       # id, title, rationale, scope, content_hash, created_at
  - Pattern        # id, trigger, repeatable_steps_text, created_at
  - Context        # id, content, topic, created_at
  - EntityFact     # id, entity_name, fact, scope, created_at
  - GovernanceToken # id, expires_at, granted_at
  - ImpactEvent    # id, source_entity_id, change_description, created_at
  - Workspace      # id, name, created_at

relationships:
  BELONGS_TO:      (Session|Decision|Pattern|Context|EntityFact) -> (Project|GlobalScope)
  HAS_FOCUS:       (Decision|Pattern|Context|EntityFact) -> FocusArea
  SUPERSEDES:      Decision -> Decision
  CONFLICTS_WITH:  (Decision|Pattern) -> (Decision|Pattern)
  CROSS_SERVICE_LINK: EntityFact -> EntityFact  # link_type, rationale, confidence
  CONTRADICTS:     (Decision|Pattern) -> (Decision|Pattern)
  MEMBER_OF:       Project -> Workspace  # set when register_service() is called

link_types_for_CROSS_SERVICE_LINK:
  - DEPENDS_ON
  - SHARES_CONCEPT
  - CONTRADICTS
  - SUPERSEDES
  - EXTENDS

example_cypher:
  find_recent_decisions: |
    MATCH (d:Decision)-[:BELONGS_TO]->(p:Project {id: $project_id})
    WHERE NOT (:Decision)-[:SUPERSEDES]->(d)
    RETURN d.title, d.rationale ORDER BY d.created_at DESC LIMIT 10

  list_services_in_workspace: |
    MATCH (p:Project)-[:MEMBER_OF]->(w:Workspace {id: $workspace_id})
    WHERE p.status = 'active'
    RETURN p.id AS service_id, p.display_name, p.last_seen

  fulltext_search: |
    CALL db.index.fulltext.queryNodes('decision_fulltext', $search_text)
    YIELD node, score
    RETURN node.id, node.title, score ORDER BY score DESC LIMIT 10

fulltext_indexes:
  - decision_fulltext  # Decision.title + Decision.rationale
  - pattern_fulltext   # Pattern.trigger + Pattern.repeatable_steps_text
  - context_fulltext   # Context.content + Context.topic
  - entity_fulltext    # EntityFact.entity_name + EntityFact.fact
"""


@mcp.resource("graphbase://schema")
async def schema_resource() -> str:
    """Graph schema: node labels, relationships, and example Cypher queries."""
    return _SCHEMA_YAML


# ── graphbase://services ──────────────────────────────────────────────────────


@mcp.resource("graphbase://services")
async def services_resource(ctx: Context) -> str:
    """Live list of all registered services across all workspaces."""
    from graphbase_memories.config import settings

    driver = ctx.lifespan_context["driver"]
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(
                "MATCH (p:Project)-[:MEMBER_OF]->(w:Workspace) "
                "RETURN p.id AS id, p.display_name AS name, "
                "w.id AS workspace, p.status AS status, p.last_seen AS last_seen "
                "ORDER BY w.id, p.id"
            )
            records = [dict(r) async for r in result]
    except Exception:
        logger.exception("services_resource: Neo4j query failed")
        return "error: Could not fetch services from Neo4j."

    if not records:
        return "services: []\n# No services registered. Call register_service() to add one."

    lines = ["services:"]
    for r in records:
        lines.append(f"  - id: {r['id']}")
        if r.get("name"):
            lines.append(f"    name: {r['name']}")
        lines.append(f"    workspace: {r.get('workspace', 'unknown')}")
        lines.append(f"    status: {r.get('status', 'unknown')}")
    return "\n".join(lines)


# ── graphbase://health/{workspace_id} ─────────────────────────────────────────


@mcp.resource("graphbase://health/{workspace_id}")
async def health_resource(ctx: Context, workspace_id: str) -> str:
    """Workspace health snapshot: node counts, conflict count, hygiene status per service."""
    from graphbase_memories.config import settings
    from graphbase_memories.engines import impact as impact_engine

    driver = ctx.lifespan_context["driver"]
    try:
        report = await impact_engine.graph_health(workspace_id, driver, settings.neo4j_database)
    except Exception:
        logger.exception("health_resource: graph_health failed for workspace %s", workspace_id)
        return f"error: Could not fetch health for workspace '{workspace_id}'."

    lines = [
        f"workspace_id: {report.workspace_id}",
        f"service_count: {report.service_count}",
        f"total_conflicts: {report.total_conflicts}",
        "services:",
    ]
    for svc in report.services:
        lines += [
            f"  - service_id: {svc.service_id}",
            f"    hygiene_status: {svc.hygiene_status}",
            f"    conflict_count: {svc.conflict_count}",
            f"    entity_count: {svc.entity_count}",
        ]
    return "\n".join(lines)


# ── graphbase://session/{session_id} ─────────────────────────────────────────


@mcp.resource("graphbase://session/{session_id}")
async def session_resource(ctx: Context, session_id: str) -> str:
    """Per-session memory view with scope, content preview, and timestamps."""
    from graphbase_memories.config import settings

    driver = ctx.lifespan_context["driver"]
    try:
        async with driver.session(database=settings.neo4j_database) as session:
            result = await session.run(
                "MATCH (s:Session {id: $sid}) "
                "RETURN s.id AS id, s.project_id AS project_id, s.status AS status, "
                "s.content AS content, s.created_at AS created_at, s.updated_at AS updated_at "
                "LIMIT 1",
                sid=session_id,
            )
            record = await result.single()
    except Exception:
        logger.exception("session_resource: Neo4j query failed for session %s", session_id)
        return f"error: Could not fetch session '{session_id}' from Neo4j."

    if not record:
        return f"error: Session '{session_id}' not found."

    r = dict(record)
    return (
        f"session_id: {r['id']}\n"
        f"project_id: {r.get('project_id', 'unknown')}\n"
        f"status: {r.get('status', 'unknown')}\n"
        f"created_at: {r.get('created_at')}\n"
        f"updated_at: {r.get('updated_at')}\n"
        f"content_preview: |\n  {str(r.get('content', ''))[:200]}"
    )
