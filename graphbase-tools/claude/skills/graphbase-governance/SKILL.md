---
name: graphbase-governance
description: Govern global memory writes. Use when you need to write a cross-service standard, policy, or decision that affects all services in the workspace. Requires a governance token.
version: 1.0.0
tools:
  - check_governance_policy
  - request_global_write_approval
---

# graphbase-governance — Governance Skill

## Why governance?

Global-scope memories (scope="global") affect every service in the workspace. An accidental or
poorly-considered global write can corrupt the shared knowledge base. Governance tokens are
time-limited write approvals that ensure intentional global writes.

## Governance Workflow

```
1. check_governance_policy(
     proposed_decision="<description of what you want to write globally>",
     project_id="<your project>"
   )
   → AnalysisResult with mode and suggested_steps

2. If policy allows:
   request_global_write_approval(
     rationale="<why this must be global>",
     ttl_seconds=300   # 5 minutes — enough for the write operation
   )
   → GovernanceToken with id

3. Pass token to write tool:
   save_decision(
     ...,
     scope="global",
     governance_token_id="<token.id>"
   )
```

## Token Rules

- Tokens expire (TTL default: 300 seconds). Use promptly.
- One token per global write operation.
- Tokens are consumed on use — request a new one if the write fails.
- Never persist or reuse tokens across sessions.

## When NOT to use global scope

| Write | Correct scope |
|-------|--------------|
| Team convention for this service | `project` |
| Auth pattern used only in this repo | `project` |
| OpenTelemetry span standard for all services | `global` |
| REST versioning policy for the platform | `global` |
