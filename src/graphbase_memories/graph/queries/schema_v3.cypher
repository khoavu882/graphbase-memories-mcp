// ============================================================
// graphbase — Neo4j Schema DDL v3 — Topology Nodes
// Idempotent: safe to re-run on every server startup.
// ADR-TOPO-001 | feat/graph-entity-facts
// ============================================================

// ── :Service (dual-label :Project:Service) ─────────────────
// No separate UNIQUE constraint — :Project constraint (schema.cypher)
// already enforces id uniqueness. :Service label shares the same
// id property as :Project on the same Neo4j node.

CREATE INDEX service_health_status IF NOT EXISTS
  FOR (s:Service) ON (s.health_status);

CREATE INDEX service_bounded_context IF NOT EXISTS
  FOR (s:Service) ON (s.bounded_context);

CREATE INDEX service_workspace_id IF NOT EXISTS
  FOR (s:Service) ON (s.workspace_id);

// ── :DataSource ────────────────────────────────────────────
CREATE CONSTRAINT datasource_id_unique IF NOT EXISTS
  FOR (ds:DataSource) REQUIRE ds.id IS UNIQUE;

CREATE INDEX datasource_type IF NOT EXISTS
  FOR (ds:DataSource) ON (ds.source_type);

CREATE INDEX datasource_workspace IF NOT EXISTS
  FOR (ds:DataSource) ON (ds.workspace_id);

// ── :MessageQueue ──────────────────────────────────────────
CREATE CONSTRAINT mq_id_unique IF NOT EXISTS
  FOR (mq:MessageQueue) REQUIRE mq.id IS UNIQUE;

CREATE INDEX mq_workspace IF NOT EXISTS
  FOR (mq:MessageQueue) ON (mq.workspace_id);

CREATE INDEX mq_type IF NOT EXISTS
  FOR (mq:MessageQueue) ON (mq.queue_type);

// ── :Feature ───────────────────────────────────────────────
CREATE CONSTRAINT feature_id_unique IF NOT EXISTS
  FOR (f:Feature) REQUIRE f.id IS UNIQUE;

CREATE INDEX feature_workspace IF NOT EXISTS
  FOR (f:Feature) ON (f.workspace_id);

// ── :BoundedContext ────────────────────────────────────────
CREATE CONSTRAINT bc_id_unique IF NOT EXISTS
  FOR (bc:BoundedContext) REQUIRE bc.id IS UNIQUE;

CREATE INDEX bc_workspace IF NOT EXISTS
  FOR (bc:BoundedContext) ON (bc.workspace_id);

CREATE INDEX bc_domain IF NOT EXISTS
  FOR (bc:BoundedContext) ON (bc.domain);

// ── Full-text index for cross-topology search ──────────────
// Covers Service, Feature, BoundedContext name + bounded_context fields.
// Used by federation search to surface topology nodes alongside EntityFact/Decision.
CREATE FULLTEXT INDEX topology_fulltext IF NOT EXISTS
  FOR (n:Service|Feature|BoundedContext) ON EACH [n.name, n.bounded_context];
