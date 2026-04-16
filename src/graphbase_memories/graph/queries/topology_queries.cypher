// ============================================================
// graphbase — Topology Traversal Queries
// ADR-TOPO-001 | Named query blocks for topology_repo.py
//
// NOTE: Neo4j does NOT support parameterized relationship types
// in variable-length path expressions. Three separate blocks are
// required for downstream/upstream/both traversal directions.
// ============================================================

// == GET_SERVICE_DEPENDENCIES_DOWNSTREAM ==
// Traverse services that $service_id calls (outbound dependency chain).
// depth: 1–6 (validated in topology_repo before query execution).
MATCH path = (start:Service {id: $service_id})
             -[:CALLS_DOWNSTREAM*1..$depth]->(dep:Service)
WHERE dep.id <> $service_id
WITH DISTINCT dep, min(length(path)) AS depth
RETURN dep.id          AS service_id,
       dep.name        AS name,
       dep.service_type AS service_type,
       dep.health_status AS health_status,
       dep.bounded_context AS bounded_context,
       depth
ORDER BY depth, dep.name
LIMIT $limit;

// == GET_SERVICE_DEPENDENCIES_UPSTREAM ==
// Traverse services that call $service_id (inbound callers).
MATCH path = (start:Service {id: $service_id})
             -[:CALLS_UPSTREAM*1..$depth]->(dep:Service)
WHERE dep.id <> $service_id
WITH DISTINCT dep, min(length(path)) AS depth
RETURN dep.id          AS service_id,
       dep.name        AS name,
       dep.service_type AS service_type,
       dep.health_status AS health_status,
       dep.bounded_context AS bounded_context,
       depth
ORDER BY depth, dep.name
LIMIT $limit;

// == GET_SERVICE_DEPENDENCIES_BOTH ==
// Undirected traversal — all services connected in either direction.
// Uses undirected path syntax (-[]-) with relationship type filter.
MATCH path = (start:Service {id: $service_id})
             -[:CALLS_UPSTREAM|CALLS_DOWNSTREAM*1..$depth]-(dep:Service)
WHERE dep.id <> $service_id
WITH DISTINCT dep, min(length(path)) AS depth
RETURN dep.id          AS service_id,
       dep.name        AS name,
       dep.service_type AS service_type,
       dep.health_status AS health_status,
       dep.bounded_context AS bounded_context,
       depth
ORDER BY depth, dep.name
LIMIT $limit;

// == GET_FEATURE_WORKFLOW ==
// Return all services involved in a feature, ordered by workflow step.
MATCH (f:Feature {id: $feature_id})-[r:INVOLVES]->(s:Service)
RETURN s.id            AS service_id,
       s.name          AS name,
       s.service_type  AS service_type,
       s.health_status AS health_status,
       s.bounded_context AS bounded_context,
       r.step_order    AS step_order,
       r.role          AS role
ORDER BY r.step_order ASC;
