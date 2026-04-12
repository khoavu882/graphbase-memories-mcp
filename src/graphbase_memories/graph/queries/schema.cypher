// ============================================================
// graphbase — Neo4j Schema DDL
// Idempotent: safe to re-run on every server startup.
// ============================================================

// ── Node Uniqueness Constraints ──────────────────────────────

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

// GovernanceToken node — S-1: durable token storage in graph
CREATE CONSTRAINT governance_token_id_unique IF NOT EXISTS
  FOR (t:GovernanceToken) REQUIRE t.id IS UNIQUE;

// ── Property Indexes ─────────────────────────────────────────

// content_hash index for exact dedup (S-2)
CREATE INDEX decision_content_hash IF NOT EXISTS
  FOR (d:Decision) ON (d.content_hash);

CREATE INDEX pattern_content_hash IF NOT EXISTS
  FOR (p:Pattern) ON (p.content_hash);

// GovernanceToken TTL cleanup index
CREATE INDEX governance_token_expires IF NOT EXISTS
  FOR (t:GovernanceToken) ON (t.expires_at);

// Hygiene scheduling indexes
CREATE INDEX project_hygiene IF NOT EXISTS
  FOR (p:Project) ON (p.last_hygiene_at);

// Scope + status filtering
CREATE INDEX session_status IF NOT EXISTS
  FOR (s:Session) ON (s.status);

CREATE INDEX decision_scope IF NOT EXISTS
  FOR (d:Decision) ON (d.scope);

// Composite index for EntityFact MERGE dedup (entity_name + scope)
CREATE INDEX entity_fact_name_scope IF NOT EXISTS
  FOR (e:EntityFact) ON (e.entity_name, e.scope);

// ── Full-text Indexes (dedup + keyword retrieval) ─────────────

CREATE FULLTEXT INDEX decision_fulltext IF NOT EXISTS
  FOR (d:Decision) ON EACH [d.title, d.rationale];

CREATE FULLTEXT INDEX pattern_fulltext IF NOT EXISTS
  FOR (p:Pattern) ON EACH [p.trigger, p.repeatable_steps_text];

CREATE FULLTEXT INDEX context_fulltext IF NOT EXISTS
  FOR (c:Context) ON EACH [c.content, c.topic];

CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
  FOR (e:EntityFact) ON EACH [e.entity_name, e.fact];

// ── Singleton Bootstrap ───────────────────────────────────────

// Ensure GlobalScope singleton always exists
MERGE (:GlobalScope {id: "global"});
