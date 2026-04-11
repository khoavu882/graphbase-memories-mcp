// == REGISTER_SERVICE ==
MERGE (p:Project {id: $service_id})
  ON CREATE SET p.created_at = datetime(), p.name = $service_id
SET p.workspace_id = $workspace_id,
    p.display_name = $display_name,
    p.description  = $description,
    p.tags         = $tags,
    p.status       = "active",
    p.last_seen    = datetime()
WITH p
MERGE (w:Workspace {id: $workspace_id})
  ON CREATE SET w.name = $workspace_id, w.created_at = datetime()
MERGE (p)-[r:MEMBER_OF]->(w)
  ON CREATE SET r.joined_at = datetime()
RETURN p, w,
       (w.created_at = p.last_seen) AS workspace_created;

// == DEREGISTER_SERVICE ==
MATCH (p:Project {id: $service_id})
SET p.status = "idle"
RETURN p;

// == LIST_ACTIVE_SERVICES ==
MATCH (p:Project)-[:MEMBER_OF]->(w:Workspace {id: $workspace_id})
WHERE p.status = "active"
  AND (p.last_seen IS NULL OR
       p.last_seen >= datetime() - duration({minutes: $max_idle_minutes}))
RETURN p
ORDER BY p.last_seen DESC;

// == SEARCH_ENTITIES ==
CALL db.index.fulltext.queryNodes("entity_fulltext", $search_query) YIELD node, score
MATCH (node)-[:BELONGS_TO]->(p:Project)
WHERE p.workspace_id = $workspace_id
  AND ($target_project_ids IS NULL OR p.id IN $target_project_ids)
RETURN node, score, p.id AS source_project, labels(node)[0] AS node_type
ORDER BY score DESC
LIMIT $limit;

// == SEARCH_DECISIONS ==
CALL db.index.fulltext.queryNodes("decision_fulltext", $search_query) YIELD node, score
MATCH (node)-[:BELONGS_TO]->(p:Project)
WHERE p.workspace_id = $workspace_id
  AND ($target_project_ids IS NULL OR p.id IN $target_project_ids)
RETURN node, score, p.id AS source_project, labels(node)[0] AS node_type
ORDER BY score DESC
LIMIT $limit;

// == CREATE_CROSS_SERVICE_LINK ==
MATCH (src), (tgt)
WHERE src.id = $source_id AND tgt.id = $target_id
MERGE (src)-[r:CROSS_SERVICE_LINK {type: $link_type}]->(tgt)
SET r.rationale   = $rationale,
    r.confidence  = $confidence,
    r.created_by  = $created_by,
    r.created_at  = datetime()
RETURN src, tgt, r;

// == GET_NODE_PROJECT ==
MATCH (n)-[:BELONGS_TO]->(p:Project)
WHERE n.id = $node_id
RETURN n.id AS node_id, p.id AS project_id;

// == CHECK_CSL_EXISTS ==
MATCH (src)-[r:CROSS_SERVICE_LINK {type: $link_type}]->(tgt)
WHERE src.id = $source_id AND tgt.id = $target_id
RETURN count(r) AS count;
