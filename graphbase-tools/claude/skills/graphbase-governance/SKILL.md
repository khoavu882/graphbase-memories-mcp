---
name: graphbase-governance
description: Govern global decision writes. Use when you need to write a cross-service standard, policy, or decision that affects all services in the workspace. Requires a governance token.
version: 2.1.0
tools:
  - request_global_write_approval
---

# graphbase-governance — Governance Skill

## Why governance?

Global-scope decisions (scope="global") affect every service in the workspace. An accidental or
poorly-considered global decision can corrupt the shared knowledge base. Governance tokens are
time-limited write approvals that ensure intentional global decision writes.

## Governance Workflow

```
request_global_write_approval(
  content_preview="<brief summary of what will be written>"
)
→ GovernanceTokenResult { token, expires_at, ttl_seconds, instructions }
```

Pass the token immediately to the write call:

```
store_session_with_learnings(
  ...,
  governance_token="<token>",
  decisions=[{
    ...,
    scope="global"
  }]
)
```

## Token Rules

- Tokens expire (TTL default: 60 seconds). Use promptly.
- One token per global decision write operation.
- Tokens are consumed on use — request a new one if the write fails.
- Never persist or reuse tokens across sessions.

## When to invoke governance

| You want to write | Scope | Needs token? |
|---|---|---|
| Team convention specific to this service | `project` | No |
| Auth pattern used only in this repo | `project` | No |
| OpenTelemetry decision standard for all services | `global` | **Yes** |
| REST versioning decision for the platform | `global` | **Yes** |
| ADR that governs multiple services | `global` | **Yes** |

Only invoke this skill when writing a global-scope decision. For project-scoped writes,
use `save_decision` or `store_session_with_learnings` directly without a token.
