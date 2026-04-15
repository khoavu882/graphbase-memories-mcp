// ============================================================
// graphbase — Topology CRUD Queries
// ADR-TOPO-001 | Named query blocks for topology_repo.py
//
// Dynamic link queries (LINK_SERVICE_DEPENDENCY, LINK_SERVICE_DATASOURCE,
// LINK_SERVICE_MQ) are NOT named blocks here — they use f-string
// interpolation in topology_repo.py AFTER whitelist validation,
// same pattern as entity_repo.link_entities().
// ============================================================

// == UPSERT_SERVICE_TOPOLOGY ==
// MERGE on :Project first — required for scope_engine.validate() compatibility.
// SET n:Service adds topology label (idempotent in Neo4j 5).
// ON CREATE SET r.joined_at preserves federation.cypher register_service parity.
MERGE (n:Project {id: $service_id})
  ON CREATE SET n.created_at = datetime(), n.name = $name
SET n:Service,
    n.workspace_id    = $workspace_id,
    n.display_name    = $display_name,
    n.service_type    = $service_type,
    n.bounded_context = $bounded_context,
    n.owner_team      = $owner_team,
    n.health_status   = $health_status,
    n.env             = $env,
    n.version         = $version,
    n.sla             = $sla,
    n.docs_url        = $docs_url,
    n.tags            = $tags,
    n.status          = "active",
    n.last_seen       = datetime(),
    n.updated_at      = datetime()
WITH n
MERGE (w:Workspace {id: $workspace_id})
  ON CREATE SET w.name = $workspace_id, w.created_at = datetime()
MERGE (n)-[r:MEMBER_OF]->(w)
  ON CREATE SET r.joined_at = datetime()
RETURN n, w;

// == UPSERT_DATASOURCE ==
MERGE (ds:DataSource {id: $source_id})
  ON CREATE SET ds.created_at = datetime()
SET ds.source_type   = $source_type,
    ds.host          = $host,
    ds.workspace_id  = $workspace_id,
    ds.owner_team    = $owner_team,
    ds.health_status = $health_status,
    ds.version       = $version,
    ds.tags          = $tags,
    ds.updated_at    = datetime()
WITH ds
MERGE (w:Workspace {id: $workspace_id})
  ON CREATE SET w.name = $workspace_id, w.created_at = datetime()
MERGE (ds)-[:PART_OF]->(w)
RETURN ds;

// == UPSERT_MESSAGE_QUEUE ==
MERGE (mq:MessageQueue {id: $queue_id})
  ON CREATE SET mq.created_at = datetime()
SET mq.queue_type        = $queue_type,
    mq.topic_or_exchange = $topic_or_exchange,
    mq.workspace_id      = $workspace_id,
    mq.owner_team        = $owner_team,
    mq.schema_version    = $schema_version,
    mq.tags              = $tags,
    mq.updated_at        = datetime()
WITH mq
MERGE (w:Workspace {id: $workspace_id})
  ON CREATE SET w.name = $workspace_id, w.created_at = datetime()
MERGE (mq)-[:PART_OF]->(w)
RETURN mq;

// == UPSERT_FEATURE ==
MERGE (f:Feature {id: $feature_id})
  ON CREATE SET f.created_at = datetime()
SET f.name           = $name,
    f.workspace_id   = $workspace_id,
    f.workflow_order = $workflow_order,
    f.owner_team     = $owner_team,
    f.tags           = $tags,
    f.updated_at     = datetime()
WITH f
MERGE (w:Workspace {id: $workspace_id})
  ON CREATE SET w.name = $workspace_id, w.created_at = datetime()
MERGE (w)-[:HAS_FEATURE]->(f)
RETURN f;

// == UPSERT_BOUNDED_CONTEXT ==
MERGE (bc:BoundedContext {id: $context_id})
  ON CREATE SET bc.created_at = datetime()
SET bc.name         = $name,
    bc.domain       = $domain,
    bc.workspace_id = $workspace_id,
    bc.tags         = $tags,
    bc.updated_at   = datetime()
WITH bc
MERGE (w:Workspace {id: $workspace_id})
  ON CREATE SET w.name = $workspace_id, w.created_at = datetime()
MERGE (bc)-[:PART_OF]->(w)
RETURN bc;

// == LINK_FEATURE_SERVICE ==
// Creates or updates INVOLVES relationship from Feature to Service.
// step_order and role SET on every call (idempotent update).
MATCH (f:Feature {id: $feature_id})
MATCH (s:Service {id: $service_id})
MERGE (f)-[r:INVOLVES]->(s)
SET r.step_order = $step_order,
    r.role       = $role,
    r.updated_at = datetime()
RETURN f, s, r;

// == LINK_SERVICE_CONTEXT ==
// Creates or updates MEMBER_OF_CONTEXT relationship.
// NOTE: MEMBER_OF_CONTEXT, not BELONGS_TO — avoids collision with
// artifact→Project ownership relationships (ADR-TOPO-001 Risk 2).
MATCH (s:Service {id: $service_id})
MATCH (bc:BoundedContext {id: $context_id})
MERGE (s)-[r:MEMBER_OF_CONTEXT]->(bc)
SET r.ownership  = $ownership,
    r.updated_at = datetime()
RETURN s, bc, r;
