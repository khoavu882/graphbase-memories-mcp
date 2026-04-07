// ============================================================
// Write queries — MERGE/CREATE per node type.
// All parameterized. Relationships created in same transaction.
// ============================================================

// -- QUERY: ensure_project
MERGE (p:Project {id: $project_id})
ON CREATE SET p.name = $name, p.created_at = datetime()
RETURN p.id AS id;

// -- QUERY: ensure_focus_area
MERGE (f:FocusArea {id: $focus_id})
ON CREATE SET f.name = $name, f.project_id = $project_id,
              f.description = $description, f.created_at = datetime()
WITH f
MATCH (p:Project {id: $project_id})
MERGE (f)-[:BELONGS_TO]->(p)
RETURN f.id AS id;

// -- QUERY: create_session
CREATE (s:Session {
  id: $id,
  objective: $objective,
  actions_taken: $actions_taken,
  decisions_made: $decisions_made,
  open_items: $open_items,
  next_actions: $next_actions,
  save_scope: $save_scope,
  status: $status,
  created_at: datetime()
})
WITH s
MATCH (p:Project {id: $project_id})
MERGE (p)<-[:BELONGS_TO]-(s)
RETURN s.id AS id;

// -- QUERY: link_session_focus
MATCH (s:Session {id: $session_id})
MATCH (f:FocusArea {name: $focus, project_id: $project_id})
MERGE (s)-[:HAS_FOCUS]->(f)
RETURN s.id AS id;

// -- QUERY: create_decision
CREATE (d:Decision {
  id: $id,
  title: $title,
  rationale: $rationale,
  owner: $owner,
  date: date($date),
  scope: $scope,
  confidence: $confidence,
  content_hash: $content_hash,
  dedup_status: $dedup_status,
  created_at: datetime()
})
WITH d
CALL {
  WITH d
  MATCH (p:Project {id: $project_id})
  MERGE (d)-[:BELONGS_TO]->(p)
}
RETURN d.id AS id;

// -- QUERY: link_decision_focus
MATCH (d:Decision {id: $decision_id})
MATCH (f:FocusArea {name: $focus, project_id: $project_id})
MERGE (d)-[:HAS_FOCUS]->(f)
RETURN d.id AS id;

// -- QUERY: link_decision_global
MATCH (d:Decision {id: $decision_id})
MATCH (g:GlobalScope {id: "global"})
MERGE (d)-[:BELONGS_TO]->(g)
RETURN d.id AS id;

// -- QUERY: supersede_decision
MATCH (newer:Decision {id: $newer_id})
MATCH (older:Decision {id: $older_id})
MERGE (newer)-[:SUPERSEDES]->(older)
RETURN newer.id AS id;

// -- QUERY: create_pattern
CREATE (p:Pattern {
  id: $id,
  trigger: $trigger,
  repeatable_steps: $repeatable_steps,
  repeatable_steps_text: $repeatable_steps_text,
  exclusions: $exclusions,
  scope: $scope,
  last_validated_at: datetime($last_validated_at),
  content_hash: $content_hash,
  created_at: datetime()
})
WITH p
MATCH (proj:Project {id: $project_id})
MERGE (p)-[:BELONGS_TO]->(proj)
RETURN p.id AS id;

// -- QUERY: create_context
CREATE (c:Context {
  id: $id,
  content: $content,
  topic: $topic,
  scope: $scope,
  relevance_score: $relevance_score,
  created_at: datetime()
})
WITH c
MATCH (proj:Project {id: $project_id})
MERGE (c)-[:BELONGS_TO]->(proj)
RETURN c.id AS id;

// -- QUERY: create_entity_fact
MERGE (e:EntityFact {entity_name: $entity_name, scope: $scope})
ON CREATE SET e.id = $id, e.fact = $fact, e.created_at = datetime()
ON MATCH SET e.fact = $fact
WITH e
MATCH (proj:Project {id: $project_id})
MERGE (e)-[:BELONGS_TO]->(proj)
RETURN e.id AS id;

// -- QUERY: link_entities
MATCH (a:EntityFact {id: $from_id})
MATCH (b:EntityFact {id: $to_id})
CALL apoc.merge.relationship(a, $relationship_type, {}, {}, b)
YIELD rel
RETURN type(rel) AS rel_type;

// -- QUERY: session_produced_artifact
MATCH (s:Session {id: $session_id})
MATCH (a {id: $artifact_id})
MERGE (s)-[:PRODUCED]->(a)
RETURN s.id AS id;

// -- QUERY: update_session_status
MATCH (s:Session {id: $session_id})
SET s.status = $status
RETURN s.id AS id;
