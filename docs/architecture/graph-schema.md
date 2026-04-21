# Graph Schema

Neo4j schema DDL is defined in `src/graphbase_memories/graph/queries/schema.cypher` and runs automatically on server startup (idempotent — all statements use `IF NOT EXISTS`). The current release baseline is the unified **v3** schema that includes memory, federation, impact, and topology nodes.

---

## Constraints

Uniqueness constraints enforce primary keys and create implicit B-tree indexes:

```cypher
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
  FOR (p:Project) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT global_scope_unique IF NOT EXISTS
  FOR (g:GlobalScope) REQUIRE g.id IS UNIQUE;

CREATE CONSTRAINT focus_id_unique IF NOT EXISTS
  FOR (f:FocusArea) REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT session_id_unique IF NOT EXISTS
  FOR (s:Session) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT decision_id_unique IF NOT EXISTS
  FOR (d:Decision) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT pattern_id_unique IF NOT EXISTS
  FOR (p:Pattern) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT context_id_unique IF NOT EXISTS
  FOR (c:Context) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT entity_fact_id_unique IF NOT EXISTS
  FOR (e:EntityFact) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT governance_token_id_unique IF NOT EXISTS
  FOR (t:GovernanceToken) REQUIRE t.id IS UNIQUE;

CREATE CONSTRAINT workspace_id_unique IF NOT EXISTS
  FOR (w:Workspace) REQUIRE w.id IS UNIQUE;

CREATE CONSTRAINT impact_event_id_unique IF NOT EXISTS
  FOR (ie:ImpactEvent) REQUIRE ie.id IS UNIQUE;

CREATE CONSTRAINT datasource_id_unique IF NOT EXISTS
  FOR (ds:DataSource) REQUIRE ds.id IS UNIQUE;

CREATE CONSTRAINT mq_id_unique IF NOT EXISTS
  FOR (mq:MessageQueue) REQUIRE mq.id IS UNIQUE;

CREATE CONSTRAINT feature_id_unique IF NOT EXISTS
  FOR (f:Feature) REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT bc_id_unique IF NOT EXISTS
  FOR (bc:BoundedContext) REQUIRE bc.id IS UNIQUE;
```

---

## Full-text indexes

Used by DedupEngine (similarity search) and keyword retrieval:

```cypher
CREATE FULLTEXT INDEX decision_fulltext IF NOT EXISTS
  FOR (d:Decision) ON EACH [d.title, d.rationale];

CREATE FULLTEXT INDEX pattern_fulltext IF NOT EXISTS
  FOR (p:Pattern) ON EACH [p.trigger, p.repeatable_steps_text];

CREATE FULLTEXT INDEX context_fulltext IF NOT EXISTS
  FOR (c:Context) ON EACH [c.content, c.topic];

CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
  FOR (e:EntityFact) ON EACH [e.entity_name, e.fact];

CREATE FULLTEXT INDEX topology_fulltext IF NOT EXISTS
  FOR (n:Service|Feature|BoundedContext) ON EACH [n.name, n.bounded_context];
```

---

## Property indexes

Exact-match, scheduling, workspace, impact, and topology indexes:

```cypher
// Exact hash dedup for Decision (O(1) lookup)
CREATE INDEX decision_content_hash IF NOT EXISTS
  FOR (d:Decision) ON (d.content_hash);

CREATE INDEX pattern_content_hash IF NOT EXISTS
  FOR (p:Pattern) ON (p.content_hash);

// TTL cleanup for GovernanceToken
CREATE INDEX governance_token_expires IF NOT EXISTS
  FOR (t:GovernanceToken) ON (t.expires_at);

CREATE INDEX project_hygiene IF NOT EXISTS
  FOR (p:Project) ON (p.last_hygiene_at);

CREATE INDEX session_status IF NOT EXISTS
  FOR (s:Session) ON (s.status);

CREATE INDEX decision_scope IF NOT EXISTS
  FOR (d:Decision) ON (d.scope);

CREATE INDEX entity_fact_name_scope IF NOT EXISTS
  FOR (e:EntityFact) ON (e.entity_name, e.scope);

CREATE INDEX project_workspace_status IF NOT EXISTS
  FOR (p:Project) ON (p.workspace_id, p.status);

CREATE INDEX project_workspace_id IF NOT EXISTS
  FOR (p:Project) ON (p.workspace_id);

CREATE INDEX project_last_seen IF NOT EXISTS
  FOR (p:Project) ON (p.last_seen);

CREATE INDEX impact_event_source_entity IF NOT EXISTS
  FOR (ie:ImpactEvent) ON (ie.source_entity_id);

CREATE INDEX impact_event_created IF NOT EXISTS
  FOR (ie:ImpactEvent) ON (ie.created_at);

CREATE INDEX service_health_status IF NOT EXISTS
  FOR (s:Service) ON (s.health_status);

CREATE INDEX service_bounded_context IF NOT EXISTS
  FOR (s:Service) ON (s.bounded_context);

CREATE INDEX service_workspace_id IF NOT EXISTS
  FOR (s:Service) ON (s.workspace_id);

CREATE INDEX datasource_type IF NOT EXISTS
  FOR (ds:DataSource) ON (ds.source_type);

CREATE INDEX datasource_workspace IF NOT EXISTS
  FOR (ds:DataSource) ON (ds.workspace_id);

CREATE INDEX mq_workspace IF NOT EXISTS
  FOR (mq:MessageQueue) ON (mq.workspace_id);

CREATE INDEX mq_type IF NOT EXISTS
  FOR (mq:MessageQueue) ON (mq.queue_type);

CREATE INDEX feature_workspace IF NOT EXISTS
  FOR (f:Feature) ON (f.workspace_id);

CREATE INDEX bc_workspace IF NOT EXISTS
  FOR (bc:BoundedContext) ON (bc.workspace_id);

CREATE INDEX bc_domain IF NOT EXISTS
  FOR (bc:BoundedContext) ON (bc.domain);
```

---

## Node property schemas

=== "Session"
    | Property | Type | Description |
    |---|---|---|
    | `id` | string | Primary key |
    | `objective` | string | Session goal |
    | `actions_taken` | string[] | What was done |
    | `decisions_made` | string[] | Key decisions (brief) |
    | `open_items` | string[] | Unresolved issues |
    | `next_actions` | string[] | Next steps |
    | `save_scope` | enum | `global / project / focus` |
    | `status` | enum | `saved / partial / pending_retry / failed / blocked_scope` |
    | `created_at` | datetime | Creation timestamp |

=== "Decision"
    | Property | Type | Description |
    |---|---|---|
    | `id` | string | Primary key |
    | `title` | string | Short title (full-text indexed) |
    | `rationale` | string | Why this decision was made (full-text indexed) |
    | `owner` | string | Who owns the decision |
    | `date` | date | Decision date |
    | `scope` | enum | `global / project / focus` |
    | `confidence` | float | 0.0–1.0 |
    | `content_hash` | string | SHA-256 for exact dedup |
    | `dedup_status` | enum | `new / duplicate_skip / supersede / manual_review` |
    | `created_at` | datetime | |

=== "Pattern"
    | Property | Type | Description |
    |---|---|---|
    | `id` | UUID | Primary key |
    | `trigger` | string | When to apply this pattern (full-text indexed) |
    | `repeatable_steps` | string[] | Ordered steps |
    | `repeatable_steps_text` | string | Space-joined helper field for full-text indexing |
    | `exclusions` | string[] | When NOT to apply |
    | `scope` | enum | `global / project / focus` |
    | `last_validated_at` | datetime | Last validation timestamp |
    | `created_at` | datetime | |

=== "Context"
    | Property | Type | Description |
    |---|---|---|
    | `id` | string | Primary key |
    | `content` | string | Free-form text (full-text indexed) |
    | `topic` | string | Short tag (full-text indexed) |
    | `scope` | enum | `global / project / focus` |
    | `relevance_score` | float | 0.0–1.0 |
    | `created_at` | datetime | |

=== "EntityFact"
    | Property | Type | Description |
    |---|---|---|
    | `id` | string | Primary key |
    | `entity_name` | string | Canonical name (MERGE key, full-text indexed) |
    | `fact` | string | A single fact statement (full-text indexed) |
    | `scope` | enum | `global / project / focus` |
    | `normalized_at` | datetime? | Set by hygiene after merge |
    | `created_at` | datetime | |

=== "Project"
    | Property | Type | Description |
    |---|---|---|
    | `id` | UUID | Primary key |
    | `name` | string | Human-readable name |
    | `workspace_id` | string? | Workspace membership |
    | `display_name` | string? | Human-readable service label |
    | `status` | string? | Federation liveness status |
    | `last_seen` | datetime? | Last service registration heartbeat |
    | `created_at` | datetime | |
    | `last_hygiene_at` | datetime? | Last hygiene run timestamp |

=== "Workspace"
    | Property | Type | Description |
    |---|---|---|
    | `id` | string | Primary key |
    | `name` | string | Human-readable name |
    | `created_at` | datetime | |

=== "ImpactEvent"
    | Property | Type | Description |
    |---|---|---|
    | `id` | string | Primary key |
    | `source_entity_id` | string | Changed entity |
    | `source_project_id` | string | Source project/service |
    | `change_description` | string | Change summary |
    | `impact_type` | string | Change category |
    | `risk_level` | string | Overall risk |
    | `affected_count` | integer | Number of affected services |
    | `created_at` | datetime | |

=== "Topology Nodes"
    | Label | Key properties |
    |---|---|
    | `Service` | Dual-label `:Project:Service`; `workspace_id`, `service_type`, `bounded_context`, `owner_team`, `health_status`, `env`, `version`, `sla`, `docs_url`, `tags`, `updated_at` |
    | `DataSource` | `id`, `source_type`, `host`, `workspace_id`, `owner_team`, `health_status`, `version`, `tags`, `created_at`, `updated_at` |
    | `MessageQueue` | `id`, `queue_type`, `topic_or_exchange`, `workspace_id`, `owner_team`, `schema_version`, `tags`, `created_at`, `updated_at` |
    | `Feature` | `id`, `name`, `workspace_id`, `workflow_order`, `owner_team`, `tags`, `created_at`, `updated_at` |
    | `BoundedContext` | `id`, `name`, `domain`, `workspace_id`, `tags`, `created_at`, `updated_at` |

=== "GovernanceToken"
    | Property | Type | Description |
    |---|---|---|
    | `id` | UUID | Primary key (the token value) |
    | `content_preview` | string | What the token was requested for |
    | `expires_at` | datetime | Expiry time (indexed for cleanup) |
    | `used` | boolean | True after the token is consumed |
    | `created_at` | datetime | |

---

## Singleton initialization

```cypher
// Ensure GlobalScope singleton exists on startup
MERGE (:GlobalScope {id: "global"});
```

This runs every startup — `MERGE` is idempotent, so it is safe to run repeatedly.
