# MCP Prompts

`graphbase` ships several **prompts**, not just tools. Prompts return guided message sequences that help an agent choose the next calls and reporting pattern without consuming a tool invocation.

---

## Registered prompts

| Prompt | Purpose | Typical follow-up calls |
|---|---|---|
| `analysis_routing` | Route a task into `sequential`, `debate`, or `socratic` mode | `retrieve_context`, then local reasoning/work |
| `memory_review` | Review project memory quality and freshness | `retrieve_context`, `run_hygiene` |
| `impact_before_edit` | Force an impact check before editing a critical entity | `propagate_impact`, `request_global_write_approval`, write tools |
| `federated_sync` | Guide cross-service sync work inside a workspace | `graphbase://services`, `search_cross_service`, `link_cross_service`, `graph_health` |

---

## `analysis_routing`

Use `analysis_routing(task_description, task_type_hint=None)` when you want the server to recommend a reasoning mode for the task.

It returns a single guidance message that includes:

- recommended mode: `sequential`, `debate`, or `socratic`
- rationale for that recommendation
- suggested next steps

### Example

```python
analysis_routing(
    task_description="Compare two service-boundary options for the payments workflow",
    task_type_hint="trade-off"
)
```

Expected guidance: prefer **debate** mode because the task is centered on evaluating alternatives.

---

## `memory_review`

Use `memory_review(project_id, scope="project")` to generate a read-only memory review workflow.

The prompt guides the agent to:

1. call `retrieve_context`
2. call `run_hygiene`
3. summarize stale or archived items
4. recommend the next action

This is the safest starting point when you want a quick state-of-memory health check before writing anything.

---

## `impact_before_edit`

Use `impact_before_edit(entity_id, proposed_change)` before changing a high-value entity fact or design decision with cross-service impact.

The prompt guides the agent to:

1. inspect downstream impact
2. pause if critical dependencies exist
3. request `request_global_write_approval` when a global write is needed
4. apply the appropriate write tool
5. record downstream impact with `propagate_impact`

---

## `federated_sync`

Use `federated_sync(source_service_id, workspace_id)` when reconciling related concepts across services.

The prompt guides the agent to:

1. read `graphbase://services`
2. use `search_cross_service` to inspect shared concepts
3. add missing links with `link_cross_service`
4. inspect resulting workspace conflicts with `graph_health`

---

## Prompts vs tools

- **Tools** return structured data or write results
- **Prompts** return guided instructions for the agent
- **Resources** return passive read-only context as YAML

For hosts that support all three MCP surfaces, `graphbase` is most effective when you mix them:

1. use a prompt to shape the workflow
2. use resources to gather passive context
3. use tools to read or mutate the graph
