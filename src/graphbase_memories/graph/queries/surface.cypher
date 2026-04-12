// SURFACE_BY_KEYWORD
// Params: $keywords (list<string>), $threshold_iso (string ISO-8601)
// Returns entity names from nodes whose content matches keywords and predates threshold.
// Used by PostToolUse staleness detection (--keywords mode).
MATCH (n)
WHERE (n:Decision OR n:Pattern OR n:Context OR n:EntityFact)
  AND any(kw IN $keywords WHERE
    toLower(n.title) CONTAINS kw OR
    toLower(n.entity_name) CONTAINS kw OR
    toLower(n.trigger) CONTAINS kw OR
    toLower(n.topic) CONTAINS kw
  )
  AND coalesce(n.updated_at, n.created_at) < datetime($threshold_iso)
RETURN
  labels(n)[0] AS label,
  coalesce(n.title, n.entity_name, n.trigger, n.topic) AS entity_name
ORDER BY coalesce(n.updated_at, n.created_at) ASC
LIMIT 20;
