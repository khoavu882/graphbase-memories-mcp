// ============================================================
// graphbase — Neo4j Schema DDL — Unified v3 Baseline
// Idempotent: safe to re-run on every server startup.
// Supersedes schema.cypher (v1), schema_v2.cypher, schema_v3.cypher.
// ============================================================

// ── 1. Node Uniqueness Constraints ───────────────────────────

// Core nodes
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
  FOR (p:Project) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT global_scope_unique IF NOT EXISTS
  FOR (g:GlobalScope) REQUIRE g.id IS UNIQUE;

CREATE CONSTRAINT focus_id_unique IF NOT EXISTS
  FOR (f:FocusArea) REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT session_id_unique IF NOT EXISTS
  FOR (s:Session) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT decision_id_unique IF NOT EXISTS
  FOR (d:Decision) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT pattern_id_unique IF NOT EXISTS
  FOR (p:Pattern) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT context_id_unique IF NOT EXISTS
  FOR (c:Context) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT entity_fact_id_unique IF NOT EXISTS
  FOR (e:EntityFact) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT governance_token_id_unique IF NOT EXISTS
  FOR (t:GovernanceToken) REQUIRE t.id IS UNIQUE;

// Workspace / cross-service nodes
CREATE CONSTRAINT workspace_id_unique IF NOT EXISTS
  FOR (w:Workspace) REQUIRE w.id IS UNIQUE;

CREATE CONSTRAINT impact_event_id_unique IF NOT EXISTS
  FOR (ie:ImpactEvent) REQUIRE ie.id IS UNIQUE;

// Topology nodes
// Note: :Service uses dual-label :Project:Service — the project_id_unique constraint
// already enforces id uniqueness. No separate UNIQUE constraint needed for :Service.

CREATE CONSTRAINT datasource_id_unique IF NOT EXISTS
  FOR (ds:DataSource) REQUIRE ds.id IS UNIQUE;

CREATE CONSTRAINT mq_id_unique IF NOT EXISTS
  FOR (mq:MessageQueue) REQUIRE mq.id IS UNIQUE;

CREATE CONSTRAINT feature_id_unique IF NOT EXISTS
  FOR (f:Feature) REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT bc_id_unique IF NOT EXISTS
  FOR (bc:BoundedContext) REQUIRE bc.id IS UNIQUE;

// ── 2. Property Indexes ───────────────────────────────────────

// Dedup — exact content hash matching
CREATE INDEX decision_content_hash IF NOT EXISTS
  FOR (d:Decision) ON (d.content_hash);

CREATE INDEX pattern_content_hash IF NOT EXISTS
  FOR (p:Pattern) ON (p.content_hash);

// GovernanceToken TTL cleanup
CREATE INDEX governance_token_expires IF NOT EXISTS
  FOR (t:GovernanceToken) ON (t.expires_at);

// Hygiene scheduling
CREATE INDEX project_hygiene IF NOT EXISTS
  FOR (p:Project) ON (p.last_hygiene_at);

// Scope + status filtering
CREATE INDEX session_status IF NOT EXISTS
  FOR (s:Session) ON (s.status);

CREATE INDEX decision_scope IF NOT EXISTS
  FOR (d:Decision) ON (d.scope);

// EntityFact MERGE dedup (entity_name + scope composite)
CREATE INDEX entity_fact_name_scope IF NOT EXISTS
  FOR (e:EntityFact) ON (e.entity_name, e.scope);

// Workspace-scoped lookups and liveness ordering
CREATE INDEX project_workspace_status IF NOT EXISTS
  FOR (p:Project) ON (p.workspace_id, p.status);

CREATE INDEX project_workspace_id IF NOT EXISTS
  FOR (p:Project) ON (p.workspace_id);

CREATE INDEX project_last_seen IF NOT EXISTS
  FOR (p:Project) ON (p.last_seen);

// ImpactEvent audit and time-series ordering
CREATE INDEX impact_event_source_entity IF NOT EXISTS
  FOR (ie:ImpactEvent) ON (ie.source_entity_id);

CREATE INDEX impact_event_created IF NOT EXISTS
  FOR (ie:ImpactEvent) ON (ie.created_at);

// Service topology indexes
CREATE INDEX service_health_status IF NOT EXISTS
  FOR (s:Service) ON (s.health_status);

CREATE INDEX service_bounded_context IF NOT EXISTS
  FOR (s:Service) ON (s.bounded_context);

CREATE INDEX service_workspace_id IF NOT EXISTS
  FOR (s:Service) ON (s.workspace_id);

// DataSource indexes
CREATE INDEX datasource_type IF NOT EXISTS
  FOR (ds:DataSource) ON (ds.source_type);

CREATE INDEX datasource_workspace IF NOT EXISTS
  FOR (ds:DataSource) ON (ds.workspace_id);

// MessageQueue indexes
CREATE INDEX mq_workspace IF NOT EXISTS
  FOR (mq:MessageQueue) ON (mq.workspace_id);

CREATE INDEX mq_type IF NOT EXISTS
  FOR (mq:MessageQueue) ON (mq.queue_type);

// Feature indexes
CREATE INDEX feature_workspace IF NOT EXISTS
  FOR (f:Feature) ON (f.workspace_id);

// BoundedContext indexes
CREATE INDEX bc_workspace IF NOT EXISTS
  FOR (bc:BoundedContext) ON (bc.workspace_id);

CREATE INDEX bc_domain IF NOT EXISTS
  FOR (bc:BoundedContext) ON (bc.domain);

// ── 3. Full-Text Indexes ──────────────────────────────────────

CREATE FULLTEXT INDEX decision_fulltext IF NOT EXISTS
  FOR (d:Decision) ON EACH [d.title, d.rationale];

CREATE FULLTEXT INDEX pattern_fulltext IF NOT EXISTS
  FOR (p:Pattern) ON EACH [p.trigger, p.repeatable_steps_text];

CREATE FULLTEXT INDEX context_fulltext IF NOT EXISTS
  FOR (c:Context) ON EACH [c.content, c.topic];

CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
  FOR (e:EntityFact) ON EACH [e.entity_name, e.fact];

// Cross-topology search: Service, Feature, BoundedContext name + bounded_context fields.
// Used by federation search to surface topology nodes alongside EntityFact/Decision.
CREATE FULLTEXT INDEX topology_fulltext IF NOT EXISTS
  FOR (n:Service|Feature|BoundedContext) ON EACH [n.name, n.bounded_context];

// ── 4. Singleton Bootstrap ────────────────────────────────────

MERGE (:GlobalScope {id: "global"});
