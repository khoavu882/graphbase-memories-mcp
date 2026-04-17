# Analysis Tool

One tool for routing a task description to the most appropriate reasoning mode.

!!! note "Prefer the `analysis_routing` prompt"
    `analysis_routing` is now registered as an MCP **prompt** (not a tool call), so it does not
    consume tool-call budget. Most agent hosts surface it via the prompts panel. Use
    `route_analysis` only if your host does not support MCP prompts.

---

## `route_analysis`

!!! warning "Deprecated — use `analysis_routing` prompt instead"
    `route_analysis` still works but emits a `DeprecationWarning`. It will be removed in a future
    release. Switch to the `analysis_routing` MCP prompt.

Analyze a task description and recommend a reasoning mode: **sequential**, **debate**, or **socratic**.
This tool does not perform the analysis itself — it routes the task so the agent can apply the right
thinking strategy.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `task_description` | `string` | Yes | Description of the task or problem to analyze |
| `task_type_hint` | `string \| null` | No | Optional hint to influence routing (see hints below) |

### Returns: `AnalysisResult`

```json
{
  "mode": "sequential",
  "rationale": "Task involves multi-step planning with ordering constraints — sequential decomposition is appropriate.",
  "suggested_steps": [
    "Define the problem scope and success criteria",
    "Identify dependencies between sub-tasks",
    "Execute sub-tasks in dependency order",
    "Validate the result against the success criteria"
  ]
}
```

---

## Routing logic

| Keywords in task / hint | Mode | Best for |
|---|---|---|
| `strategic`, `multi-factor`, `planning` | `sequential` | Ordered multi-step problems |
| `trade-off`, `compare`, `debate`, `pros and cons` | `debate` | Evaluating competing options |
| `unclear`, `requirements`, `discovery`, `what should` | `socratic` | Ill-defined problems needing clarification |
| (none / unknown) | `sequential` | Safe default |

### Mode descriptions

**sequential** — Break the task into ordered steps with explicit dependencies. Use when the
problem has a clear structure and steps must be done in sequence.

**debate** — Evaluate multiple competing approaches by arguing for and against each. Use when
trade-offs between options are unclear.

**socratic** — Clarify the problem through questioning before attempting to solve it. Use when
requirements are ambiguous or the problem is poorly defined.

---

## Memory save rule

Only the `final_conclusion` of an analysis is eligible for memory save. Intermediate discussion,
debate points, and exploratory questions are **never persisted** automatically.

To save a conclusion reached through analysis:
```python
save_decision(
    decision={
        "title": "Route complex planning tasks through sequential mode",
        "rationale": "Sequential mode provides ordered step decomposition with dependency tracking, which prevents out-of-order execution errors.",
        "scope": "global",
        ...
    },
    project_id="my-project",
    governance_token="..."
)
```

---

## Example

```python
route_analysis(
    task_description="Decide whether to use vector embeddings or full-text + Jaccard similarity for decision deduplication",
    task_type_hint="trade-off"
)
# Returns: mode="debate", with suggested_steps for evaluating both options
```
