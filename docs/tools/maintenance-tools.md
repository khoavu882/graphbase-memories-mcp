# Maintenance Tools

Tools for memory lifecycle management.

## get_stale_memories

Return non-deleted memories not updated within a given number of days.

**Parameters**:

| Name | Type | Default | Description |
|---|---|---|---|
| `project` | str | — | Project slug |
| `age_days` | int | `30` | Age threshold in days |

**Returns**: `[{id, title, type, updated_at, tags, is_expired}]`

Use this to identify memories that may have become outdated and need review.

## flag_expired_memory

Mark a memory as expired (`is_expired=1`). Does NOT delete — expired memories are flagged in the YAML context injection and excluded from ranked search results.

**Parameters**:

| Name | Type | Description |
|---|---|---|
| `project` | str | Project slug |
| `memory_id` | str | Memory UUID |

**Returns**: `{memory_id, flagged}`

This is the first step of the two-step expiry lifecycle: flag → then purge in bulk.

## purge_expired_memories

Permanently delete memories where `is_expired=1` AND `updated_at` is older than `older_than_days`. **Irreversible.**

**Parameters**:

| Name | Type | Default | Description |
|---|---|---|---|
| `project` | str | — | Project slug |
| `older_than_days` | int | `30` | Age threshold in days |

**Returns**: `{purged: N}` — count of permanently deleted records.

Call `get_stale_memories` first and review the list before purging. The `older_than_days` guard prevents accidentally purging recently expired memories.

## Two-step expiry lifecycle

```
1. get_stale_memories(project, age_days=30)    → review the list
2. flag_expired_memory(project, memory_id)      → flag each one you want to remove
3. purge_expired_memories(project, older_than_days=30)  → permanent bulk delete
```

This design prevents accidental permanent deletion — you must explicitly flag memories before purge can remove them.
