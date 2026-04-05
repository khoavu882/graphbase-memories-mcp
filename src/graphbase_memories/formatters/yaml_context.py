"""
YAML context formatter for graphbase-memories.

render_context() builds a compact YAML block for hook injection.

Design decisions:
  [Q3] Hard token cap with priority ordering:
       P1 decisions → P2 service_metadata → P3 patterns → P4 stale_warnings
       → P5 related_entities → P6 recent sessions
       Each priority block is only included if remaining budget permits.

  Token counting: len(text) // 4 (GPT-3.5 heuristic, ±15% — sufficient for
  a 500-token budget where ±75 tokens is acceptable, no C extensions required).

  Content truncation: long content fields are truncated to fit the budget.
  Titles are never truncated.

  Output format: YAML sections separated by blank lines, no document separators
  within a single get_context call. Valid as a fenced code block in markdown.
"""

from __future__ import annotations

from graphbase_memories.graph.engine import EntityNode, MemoryNode

# ---------------------------------------------------------------------------
# Token budget helpers
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4   # GPT-3.5 rule of thumb; ±15% accuracy


def _token_count(text: str) -> int:
    """Estimate token count from character count."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, appending '…' if truncated."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_memory_list(
    memories: list[MemoryNode],
    header: str,
    content_chars: int,
    budget_chars: int,
) -> str:
    """Render a titled list of memories within budget (shared by decisions/patterns)."""
    if not memories:
        return ""
    lines = [f"{header}:"]
    for m in memories:
        entry = f"  - title: {m.title!r}\n    content: {_truncate(m.content, content_chars)!r}"
        if budget_chars - len("\n".join(lines)) - len(entry) < 0:
            break
        lines.append(entry)
    if len(lines) == 1:
        return ""   # header only — nothing fit
    return "\n".join(lines)


def _render_decisions(decisions: list[MemoryNode], budget_chars: int) -> str:
    return _render_memory_list(decisions, "decisions", 120, budget_chars)


def _render_patterns(patterns: list[MemoryNode], budget_chars: int) -> str:
    return _render_memory_list(patterns, "patterns", 100, budget_chars)


def _render_service_metadata(metadata: dict, budget_chars: int) -> str:
    """Render entity metadata as a flat YAML block (P2 priority).

    Only includes scalar values (str, int, float, bool) to keep output compact.
    Lists are joined as comma-separated strings. Nested dicts are skipped.
    """
    if not metadata:
        return ""
    lines = ["service_metadata:"]
    for key, value in metadata.items():
        if isinstance(value, dict):
            continue   # skip nested objects — too noisy for context injection
        if isinstance(value, list):
            rendered_val = repr(", ".join(str(v) for v in value))
        else:
            rendered_val = repr(str(value))
        entry = f"  {key}: {rendered_val}"
        if budget_chars - len("\n".join(lines)) - len(entry) < 0:
            break
        lines.append(entry)
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _render_stale_warnings(stale: list[MemoryNode]) -> str:
    """Render stale memory warning list (titles only — brief by design)."""
    if not stale:
        return ""
    lines = ["stale_warnings:"]
    for s in stale[:5]:   # cap at 5 — this is a nudge, not a dump
        lines.append(f"  - {s.title!r}  # expired")
    return "\n".join(lines)


def _render_entities(entities: list[EntityNode], budget_chars: int) -> str:
    """Render related entity names."""
    if not entities:
        return ""
    lines = ["related_entities:"]
    for e in entities:
        entry = f"  - name: {e.name!r}\n    type: {e.type!r}"
        if budget_chars - len("\n".join(lines)) - len(entry) < 0:
            break
        lines.append(entry)
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _render_sessions(memories: list[MemoryNode], budget_chars: int) -> str:
    """Render recent session titles as context filler."""
    sessions = [m for m in memories if m.type == "session"]
    if not sessions:
        return ""
    lines = ["recent_sessions:"]
    for s in sessions[:3]:
        entry = f"  - {s.title!r}"
        if budget_chars - len("\n".join(lines)) - len(entry) < 0:
            break
        lines.append(entry)
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_context(
    memories: list[MemoryNode],
    entities: list[EntityNode],
    stale: list[MemoryNode],
    focus_entity: str | None,
    max_tokens: int,
    entity_metadata: dict | None = None,
) -> str:
    """
    Build a priority-ordered YAML context block hard-capped at max_tokens. [Q3]

    Priority order:
      P1: decisions        (~100 tokens, always included if they fit)
      P2: service_metadata (~60 tokens — current real-world state of focus entity)
      P3: patterns         (~80 tokens)
      P4: stale_warnings   (~60 tokens — is_expired memories needing review)
      P5: related_entities (~40 tokens)
      P6: recent session titles (~40 tokens, filler)

    entity_metadata: dict from EntityNode.metadata for the focus entity.
                     Passed separately so this function stays a pure formatter.

    Returns empty string if no memories exist (graceful degradation).
    """
    if not memories and not stale and not entities and not entity_metadata:
        return ""

    budget = max_tokens * _CHARS_PER_TOKEN   # work in characters throughout
    sections: list[str] = []

    # P1: decisions
    decisions = [m for m in memories if m.type == "decision"]
    block = _render_decisions(decisions, budget)
    if block:
        sections.append(block)
        budget -= len(block)

    # P2: service_metadata (current entity state — highest practical value per token)
    if budget > 60 * _CHARS_PER_TOKEN and entity_metadata:
        block = _render_service_metadata(entity_metadata, budget)
        if block:
            sections.append(block)
            budget -= len(block)

    # P3: patterns (only if budget remains)
    if budget > 80 * _CHARS_PER_TOKEN:
        patterns = [m for m in memories if m.type == "pattern"]
        block = _render_patterns(patterns, budget)
        if block:
            sections.append(block)
            budget -= len(block)

    # P4: stale warnings
    if budget > 60 * _CHARS_PER_TOKEN and stale:
        block = _render_stale_warnings(stale)
        if block:
            sections.append(block)
            budget -= len(block)

    # P5: related entities
    if budget > 40 * _CHARS_PER_TOKEN and entities:
        block = _render_entities(entities, budget)
        if block:
            sections.append(block)
            budget -= len(block)

    # P6: recent session titles (filler)
    if budget > 40 * _CHARS_PER_TOKEN:
        block = _render_sessions(memories, budget)
        if block:
            sections.append(block)

    return "\n\n".join(sections)
