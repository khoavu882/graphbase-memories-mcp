# Graph Schema

Neo4j schema DDL is defined in `src/graphbase_memories/graph/queries/schema.cypher` and runs automatically on server startup (idempotent — all statements use `IF NOT EXISTS`).

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
```

---

## Full-text indexes

Used by DedupEngine (similarity search) and keyword retrieval:

```cypher
CREATE FULLTEXT INDEX decision_fulltext IF NOT EXISTS
  FOR (d:Decision) ON EACH [d.title, d.rationale];

CREATE FULLTEXT INDEX pattern_fulltext IF NOT EXISTS
  FOR (p:Pattern) ON EACH [p.trigger, p.repeatable_steps];

CREATE FULLTEXT INDEX context_fulltext IF NOT EXISTS
  FOR (c:Context) ON EACH [c.content, c.topic];

CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS
  FOR (e:EntityFact) ON EACH [e.entity_name, e.fact];
```

---

## Property indexes

```cypher
// Exact hash dedup for Decision (O(1) lookup)
CREATE INDEX decision_content_hash IF NOT EXISTS
  FOR (d:Decision) ON (d.content_hash);

// TTL cleanup for GovernanceToken
CREATE INDEX governance_token_expires_at IF NOT EXISTS
  FOR (t:GovernanceToken) ON (t.expires_at);
```

---

## Node property schemas

=== "Session"
    | Property | Type | Description |
    |---|---|---|
    | `id` | UUID | Primary key |
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
    | `id` | UUID | Primary key |
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
    | `repeatable_steps` | string[] | Ordered steps (full-text indexed) |
    | `exclusions` | string[] | When NOT to apply |
    | `scope` | enum | `global / project / focus` |
    | `last_validated_at` | datetime | Last validation timestamp |
    | `created_at` | datetime | |

=== "Context"
    | Property | Type | Description |
    |---|---|---|
    | `id` | UUID | Primary key |
    | `content` | string | Free-form text (full-text indexed) |
    | `topic` | string | Short tag (full-text indexed) |
    | `scope` | enum | `global / project / focus` |
    | `relevance_score` | float | 0.0–1.0 |
    | `created_at` | datetime | |

=== "EntityFact"
    | Property | Type | Description |
    |---|---|---|
    | `id` | UUID | Primary key |
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
    | `created_at` | datetime | |
    | `last_hygiene_at` | datetime? | Last hygiene run timestamp |

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
