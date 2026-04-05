# Session Workflows

Five real-world patterns for using graphbase-memories effectively.

## 1. Session logging

At the end of a productive session, log what happened:

```
Store a session memory for today: we refactored the auth middleware to use
JWT instead of session cookies, motivated by the compliance requirement
from last week's audit.
```

Claude calls `store_memory(type="session", ...)` with relevant entity tags (`auth-middleware`, `JWT`, `compliance`).

**Why**: Future sessions start with this context pre-loaded. You won't re-explain the refactor motivation.

## 2. Decision recording

Before committing to an architectural choice, record the decision and rationale:

```
Store a decision memory: we chose PostgreSQL over Redis for the session store
because Redis's TTL-based expiry doesn't meet the audit trail requirement.
Tag it with: session-store, postgres, redis, compliance.
```

Later, if the decision changes:

```
Store a new decision: we're moving back to Redis with a PostgreSQL audit log
side table. Supersede the previous session-store decision.
```

Claude creates the new memory and adds a `SUPERSEDES` edge pointing to the old one.

## 3. Pattern capture

When you discover a reusable technique:

```
Store a pattern: when a service depends on an external API, wrap the client
in a circuit breaker with a 5-second timeout. We burned 3 hours debugging
cascading failures before adding this.
```

Future sessions can search: `search_memories(query="circuit breaker timeout")`.

## 4. Blast radius analysis before refactoring

Before touching a shared component:

```
Show the blast radius for entity "user-auth-service" with depth 2.
```

`get_blast_radius` returns all memories and co-occurring entities within 2 hops — revealing which past decisions, patterns, and sessions are affected by changes to that service.

## 5. End-of-session batch save

To persist a full session — summary, decisions, and patterns — in one call, use `store_session_with_learnings`:

```
Store the session: we migrated the auth service from session cookies to JWT.
Decisions: [
  { "title": "Use JWT for auth tokens", "content": "Stateless tokens eliminate sticky-session requirement. Trade-off: revocation requires blocklist." },
  { "title": "Refresh token rotation", "content": "Single-use refresh tokens mitigate token theft window." }
]
Patterns: [
  { "title": "Test token expiry with frozen clock", "content": "Use pytest-freezegun to simulate expired tokens without sleep()." }
]
```

Claude calls `store_session_with_learnings(project, session, decisions, patterns)`.

The tool handles:
- Storing the session memory and returning `session_id`
- Creating `LEARNED_DURING` edges from each decision and pattern to the session
- SUPERSEDES dedup: if a prior decision with the same title exists, the new one automatically supersedes it

**Why use this instead of separate tool calls?** Each decision previously required 3 MCP calls: `search_memories` (dedup check) + `store_memory` + `relate_memories` (LEARNED_DURING). For a session with 3 decisions and 2 patterns, that was 5+3+2+2 = 12 calls. `store_session_with_learnings` reduces this to 1.

## 6. Stale memory review

Weekly (or before a major release):

```
Show stale memories for this project older than 30 days.
```

`get_stale_memories` returns records not updated in 30+ days and flags them `is_expired=1`. Review them, then purge in bulk with `purge_expired_memories(older_than_days=30)` when ready.
