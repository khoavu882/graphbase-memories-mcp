---
name: graphbase-governance
description: Govern global memory writes. Use when you need to write a cross-service standard, policy, or decision that affects all services in the workspace. Requires a governance token.
version: 2.0.0
tools:
  - request_global_write_approval
---

# graphbase-governance — Governance Skill

## Why governance?

Global-scope memories (scope="global") affect every service in the workspace. An accidental or
poorly-considered global write can corrupt the shared knowledge base. Governance tokens are
time-limited write approvals that ensure intentional global writes.

## Governance Workflow

```
request_global_write_approval(
  rationale="<why this write must be global — one clear sentence>",
  content_preview="<brief summary of what will be written>",
  ttl_seconds=300   # 5 minutes — enough for the write operation
)
→ GovernanceToken { id, expires_at }
```

Pass the token immediately to the write call:

```
store_session_with_learnings(
  ...,
  decisions=[{
    ...,
    scope="global",
    governance_token_id="<token.id>"
  }]
)
```

## Token Rules

- Tokens expire (TTL default: 300 seconds). Use promptly.
- One token per global write operation.
- Tokens are consumed on use — request a new one if the write fails.
- Never persist or reuse tokens across sessions.

## When to invoke governance

| You want to write | Scope | Needs token? |
|---|---|---|
| Team convention specific to this service | `project` | No |
| Auth pattern used only in this repo | `project` | No |
| OpenTelemetry span standard for all services | `global` | **Yes** |
| REST versioning policy for the platform | `global` | **Yes** |
| ADR that governs multiple services | `global` | **Yes** |

Only invoke this skill when the write scope is `global`. For project-scoped writes,
use `store_session_with_learnings` directly without a token.
