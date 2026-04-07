// ============================================================
// Dedup queries — S-2: hash-first, then Jaccard via FULLTEXT.
// Step 1: exact hash match (deterministic, corpus-independent)
// Step 2: FULLTEXT top-5 candidates for Jaccard scoring in Python
// ============================================================

// -- QUERY: exact_hash_match_decision
MATCH (d:Decision)
WHERE d.content_hash = $content_hash
  AND d.scope = $scope
RETURN d.id AS id, d.title AS title LIMIT 1;

// -- QUERY: exact_hash_match_pattern
MATCH (p:Pattern)
WHERE p.content_hash = $content_hash
  AND p.scope = $scope
RETURN p.id AS id, p.trigger AS trigger LIMIT 1;

// -- QUERY: fulltext_candidates_decision
CALL db.index.fulltext.queryNodes("decision_fulltext", $query)
YIELD node, score
WHERE node.scope = $scope
  AND node.id <> $exclude_id
RETURN node.id AS id, node.title AS title, node.rationale AS rationale,
       node.date AS date, score
ORDER BY score DESC LIMIT 5;

// -- QUERY: fulltext_candidates_pattern
CALL db.index.fulltext.queryNodes("pattern_fulltext", $query)
YIELD node, score
WHERE node.scope = $scope
  AND node.id <> $exclude_id
RETURN node.id AS id, node.trigger AS trigger, score
ORDER BY score DESC LIMIT 5;

// -- QUERY: create_governance_token
CREATE (t:GovernanceToken {
  id: $id,
  content_preview: $content_preview,
  expires_at: datetime($expires_at),
  used: false,
  created_at: datetime()
})
RETURN t.id AS id;

// -- QUERY: validate_governance_token
MATCH (t:GovernanceToken {id: $token_id})
WHERE t.used = false
  AND t.expires_at > datetime()
RETURN t.id AS id, t.expires_at AS expires_at;

// -- QUERY: consume_governance_token
MATCH (t:GovernanceToken {id: $token_id})
SET t.used = true
RETURN t.id AS id;

// -- QUERY: cleanup_expired_tokens
MATCH (t:GovernanceToken)
WHERE t.expires_at < datetime() OR t.used = true
DELETE t
RETURN count(t) AS deleted;
