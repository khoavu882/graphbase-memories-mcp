// == BATCH_NEIGHBORS ==
MATCH (src)-[r:CROSS_SERVICE_LINK]->(tgt)
WHERE src.id IN $node_ids
MATCH (tgt)-[:BELONGS_TO]->(p:Project)
RETURN tgt.id AS id, p.id AS project_id, r.type AS edge_type;

// == WRITE_IMPACT_EVENT ==
CREATE (ie:ImpactEvent {
  id:                 $event_id,
  source_entity_id:   $source_entity_id,
  source_project_id:  $source_project_id,
  change_description: $change_description,
  impact_type:        $impact_type,
  risk_level:         $risk_level,
  affected_count:     $affected_count,
  created_at:         datetime()
})
WITH ie
UNWIND $affected AS row
MATCH (p:Project {id: row.project_id})
CREATE (ie)-[:AFFECTS {depth: row.depth, risk_level: row.risk_level}]->(p)
RETURN ie;

// == GRAPH_HEALTH ==
MATCH (p:Project)-[:MEMBER_OF]->(w:Workspace {id: $workspace_id})
OPTIONAL MATCH (entity:EntityFact)-[:BELONGS_TO]->(p)
OPTIONAL MATCH (decision:Decision)-[:BELONGS_TO]->(p)
OPTIONAL MATCH (pattern:Pattern)-[:BELONGS_TO]->(p)
OPTIONAL MATCH (d2:Decision)-[conflict_rel]-(other:Decision)
  WHERE type(conflict_rel) = "CONFLICTS_WITH"
    AND ((d2)-[:BELONGS_TO]->(p) OR (other)-[:BELONGS_TO]->(p))
WITH p,
     count(DISTINCT entity)   AS entity_count,
     count(DISTINCT decision) AS decision_count,
     count(DISTINCT pattern)  AS pattern_count,
     count(DISTINCT d2)       AS conflict_count
RETURN p, entity_count, decision_count, pattern_count, conflict_count
ORDER BY p.id;

// == DETECT_CONFLICTS ==
MATCH (src)-[r:CROSS_SERVICE_LINK {type: "CONTRADICTS"}]->(tgt)
MATCH (src)-[:BELONGS_TO]->(p1:Project)-[:MEMBER_OF]->(w:Workspace {id: $workspace_id})
MATCH (tgt)-[:BELONGS_TO]->(p2:Project)-[:MEMBER_OF]->(w)
WHERE p1.id <> p2.id
RETURN src, tgt,
       r.rationale AS link_rationale,
       r.confidence AS link_confidence,
       r.created_at AS link_created_at,
       p1.id AS project_a, p2.id AS project_b
ORDER BY link_created_at DESC
LIMIT $limit;
