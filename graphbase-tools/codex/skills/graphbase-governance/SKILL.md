---
name: graphbase-governance
description: Use before writing global-scope decisions or guarded multi-node topology batches that require a one-time governance token.
---

# Graphbase Governance

Request a one-time token:

```text
request_global_write_approval(content_preview="<what will be written>")
```

Use the returned `token` immediately as `governance_token`.

Token rules:

- Default TTL is 60 seconds.
- Tokens are consumed on use.
- Request a new token for each global decision write or guarded batch operation.
- Do not store tokens in memory, docs, or commits.

Project-scoped decisions, patterns, contexts, sessions, and entity facts do not need a governance token.
