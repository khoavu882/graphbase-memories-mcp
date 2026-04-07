// ============================================================
// Retrieval queries — parameterized, scope-priority ordered.
// Supersession filter: exclude nodes that have been superseded.
// Named query blocks are loaded as a single file; Python splits
// them by the "-- QUERY:" markers and executes by name.
// ============================================================

// -- QUERY: sessions_by_project
MATCH (s:Session)-[:BELONGS_TO]->(p:Project {id: $project_id})
WHERE NOT EXISTS { MATCH (s)<-[:PRODUCED]-(:Session) }
RETURN s {.*} AS node, 'Session' AS label, s.created_at AS created_at
ORDER BY s.created_at DESC LIMIT 20;

// -- QUERY: sessions_by_focus
MATCH (s:Session)-[:HAS_FOCUS]->(f:FocusArea {name: $focus, project_id: $project_id})
RETURN s {.*} AS node, 'Session' AS label, s.created_at AS created_at
ORDER BY s.created_at DESC LIMIT 10;

// -- QUERY: decisions_by_project
MATCH (d:Decision)-[:BELONGS_TO]->(p:Project {id: $project_id})
WHERE NOT EXISTS { MATCH (:Decision)-[:SUPERSEDES]->(d) }
RETURN d {.*} AS node, 'Decision' AS label, d.created_at AS created_at
ORDER BY d.created_at DESC LIMIT 20;

// -- QUERY: decisions_by_focus
MATCH (d:Decision)-[:HAS_FOCUS]->(f:FocusArea {name: $focus, project_id: $project_id})
WHERE NOT EXISTS { MATCH (:Decision)-[:SUPERSEDES]->(d) }
RETURN d {.*} AS node, 'Decision' AS label, d.created_at AS created_at
ORDER BY d.created_at DESC LIMIT 10;

// -- QUERY: decisions_global
MATCH (d:Decision)-[:BELONGS_TO]->(g:GlobalScope)
WHERE NOT EXISTS { MATCH (:Decision)-[:SUPERSEDES]->(d) }
RETURN d {.*} AS node, 'Decision' AS label, d.created_at AS created_at
ORDER BY d.created_at DESC LIMIT 10;

// -- QUERY: patterns_by_project
MATCH (p:Pattern)-[:BELONGS_TO]->(proj:Project {id: $project_id})
RETURN p {.*} AS node, 'Pattern' AS label, p.created_at AS created_at
ORDER BY p.last_validated_at DESC LIMIT 10;

// -- QUERY: patterns_global
MATCH (p:Pattern)-[:BELONGS_TO]->(g:GlobalScope)
RETURN p {.*} AS node, 'Pattern' AS label, p.created_at AS created_at
ORDER BY p.last_validated_at DESC LIMIT 5;

// -- QUERY: context_by_project
MATCH (c:Context)-[:BELONGS_TO]->(proj:Project {id: $project_id})
RETURN c {.*} AS node, 'Context' AS label, c.created_at AS created_at
ORDER BY c.relevance_score DESC, c.created_at DESC LIMIT 10;

// -- QUERY: context_by_focus
MATCH (c:Context)-[:HAS_FOCUS]->(f:FocusArea {name: $focus, project_id: $project_id})
RETURN c {.*} AS node, 'Context' AS label, c.created_at AS created_at
ORDER BY c.relevance_score DESC LIMIT 5;

// -- QUERY: conflicts_check
MATCH (d:Decision)-[:CONFLICTS_WITH]->(other:Decision)
WHERE d.scope = $scope
RETURN count(d) AS conflict_count;

// -- QUERY: hygiene_due_check
MATCH (p:Project {id: $project_id})
RETURN p.last_hygiene_at AS last_hygiene_at;
