// ============================================================
// Freshness queries — find nodes not updated within threshold.
// Uses coalesce(updated_at, created_at) for nodes without update tracking.
// Filters by project via BELONGS_TO relationship (nodes don't store project_id
// as a property — they link to Project or GlobalScope via :BELONGS_TO).
//
// age_days uses epoch milliseconds to avoid duration normalization:
// duration.between().days only gives the days *component*, not total days.
// 60 days would be "2 months + 0 days" → .days = 0. epochMillis is reliable.
// ============================================================

// == FRESHNESS_SCAN ==
MATCH (n)-[:BELONGS_TO]->(p)
WHERE (n:Session OR n:Decision OR n:Pattern OR n:Context OR n:EntityFact)
  AND ($project_id IS NULL OR p.id = $project_id)
  AND coalesce(n.updated_at, n.created_at) < datetime($threshold_iso)
WITH n, labels(n)[0] AS label,
     coalesce(n.updated_at, n.created_at) AS last_active,
     p.id AS proj_id
ORDER BY last_active ASC
LIMIT $scan_limit
RETURN n {.*} AS node, label,
       toInteger((datetime().epochMillis - last_active.epochMillis) / 86400000) AS age_days,
       proj_id
