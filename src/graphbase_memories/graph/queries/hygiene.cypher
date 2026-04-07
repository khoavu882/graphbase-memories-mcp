// ============================================================
// Hygiene queries — read-only detection + last_hygiene_at update.
// HygieneEngine never auto-mutates; it reports candidates only.
// ============================================================

// -- QUERY: projects_due_for_hygiene
MATCH (p:Project)
WHERE p.last_hygiene_at IS NULL
   OR p.last_hygiene_at < datetime() - duration({days: 30})
RETURN p.id AS id, p.name AS name, p.last_hygiene_at AS last_hygiene_at;

// -- QUERY: global_due_for_hygiene
MATCH (g:GlobalScope {id: "global"})
WHERE g.last_hygiene_at IS NULL
   OR g.last_hygiene_at < datetime() - duration({days: 30})
RETURN g.id AS id, g.last_hygiene_at AS last_hygiene_at;

// -- QUERY: duplicate_decisions
// Find decision pairs with the same content_hash — true duplicates
MATCH (d1:Decision), (d2:Decision)
WHERE d1.content_hash = d2.content_hash
  AND d1.id < d2.id
  AND ($project_id IS NULL OR
       EXISTS { (d1)-[:BELONGS_TO]->(:Project {id: $project_id}) })
RETURN d1.id AS id1, d2.id AS id2, d1.title AS title
LIMIT 50;

// -- QUERY: outdated_decisions
// Decisions older than 180 days with no outgoing SUPERSEDES
MATCH (d:Decision)
WHERE d.created_at < datetime() - duration({days: 180})
  AND NOT EXISTS { MATCH (d)-[:SUPERSEDES]->() }
  AND ($project_id IS NULL OR
       EXISTS { (d)-[:BELONGS_TO]->(:Project {id: $project_id}) })
RETURN d.id AS id, d.title AS title, d.created_at AS created_at
ORDER BY d.created_at ASC LIMIT 20;

// -- QUERY: obsolete_patterns
// Patterns not validated in 90 days
MATCH (p:Pattern)
WHERE p.last_validated_at < datetime() - duration({days: 90})
  AND ($project_id IS NULL OR
       EXISTS { (p)-[:BELONGS_TO]->(:Project {id: $project_id}) })
RETURN p.id AS id, p.trigger AS trigger, p.last_validated_at AS last_validated_at
ORDER BY p.last_validated_at ASC LIMIT 20;

// -- QUERY: entity_fact_drift
// EntityFacts with same entity_name but different facts (potential merge)
MATCH (e1:EntityFact), (e2:EntityFact)
WHERE e1.entity_name = e2.entity_name
  AND e1.id < e2.id
  AND e1.scope = e2.scope
  AND ($project_id IS NULL OR
       EXISTS { (e1)-[:BELONGS_TO]->(:Project {id: $project_id}) })
RETURN e1.id AS id1, e2.id AS id2, e1.entity_name AS entity_name
LIMIT 20;

// -- QUERY: unresolved_saves
// Sessions/Decisions with failed/pending_retry status
MATCH (s:Session)
WHERE s.status IN ["pending_retry", "failed", "partial"]
  AND ($project_id IS NULL OR
       EXISTS { (s)-[:BELONGS_TO]->(:Project {id: $project_id}) })
RETURN s.id AS id, "Session" AS type, s.status AS status, s.created_at AS created_at
ORDER BY s.created_at DESC LIMIT 20;

// -- QUERY: update_project_hygiene_at
MATCH (p:Project {id: $project_id})
SET p.last_hygiene_at = datetime()
RETURN p.id AS id;

// -- QUERY: update_global_hygiene_at
MATCH (g:GlobalScope {id: "global"})
SET g.last_hygiene_at = datetime()
RETURN g.id AS id;
