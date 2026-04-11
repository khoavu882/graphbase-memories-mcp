// ── Workspace constraints
CREATE CONSTRAINT workspace_id_unique IF NOT EXISTS
  FOR (w:Workspace) REQUIRE w.id IS UNIQUE;

// ── ImpactEvent constraints
CREATE CONSTRAINT impact_event_id_unique IF NOT EXISTS
  FOR (ie:ImpactEvent) REQUIRE ie.id IS UNIQUE;

// ── Project — composite index for list_active_services (B-4 fix)
CREATE INDEX project_workspace_status IF NOT EXISTS
  FOR (p:Project) ON (p.workspace_id, p.status);

// ── Project — workspace FK for workspace-scoped lookups
CREATE INDEX project_workspace_id IF NOT EXISTS
  FOR (p:Project) ON (p.workspace_id);

// ── Project — liveness ordering
CREATE INDEX project_last_seen IF NOT EXISTS
  FOR (p:Project) ON (p.last_seen);

// ── ImpactEvent — audit query by source entity
CREATE INDEX impact_event_source_entity IF NOT EXISTS
  FOR (ie:ImpactEvent) ON (ie.source_entity_id);

// ── ImpactEvent — time-series ordering
CREATE INDEX impact_event_created IF NOT EXISTS
  FOR (ie:ImpactEvent) ON (ie.created_at);
