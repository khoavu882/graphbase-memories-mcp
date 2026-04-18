"""
AnalysisRouter — M-1: routes task to analysis mode + returns suggested_steps.
Keyword-based routing — simple, deterministic, no LLM call needed.
"""

from __future__ import annotations

from graphbase_memories.domain.enums import AnalysisMode
from graphbase_memories.domain.results import AnalysisResult

_SEQUENTIAL_KEYWORDS = {
    "strategic",
    "strategy",
    "multi-factor",
    "planning",
    "roadmap",
    "prioritize",
    "milestone",
    "initiative",
    "phase",
}
_DEBATE_KEYWORDS = {
    "trade-off",
    "tradeoff",
    "compare",
    "versus",
    "vs",
    "debate",
    "alternatives",
    "option",
    "choose",
    "decision between",
}
_SOCRATIC_KEYWORDS = {
    "unclear",
    "requirements",
    "discovery",
    "explore",
    "what do you mean",
    "clarify",
    "understand",
    "not sure",
    "ambiguous",
}

_SUGGESTED_STEPS: dict[AnalysisMode, list[str]] = {
    AnalysisMode.sequential: [
        "1. Define the problem statement and success criteria.",
        "2. Gather relevant context from memory (retrieve_context).",
        "3. Break the problem into sequential steps or phases.",
        "4. Analyze each step for dependencies and risks.",
        "5. Synthesize conclusions and save durable decisions.",
    ],
    AnalysisMode.debate: [
        "1. Enumerate the competing options or trade-offs.",
        "2. Retrieve prior decisions on similar trade-offs.",
        "3. Evaluate each option against criteria (cost, risk, fit).",
        "4. State the recommended option with rationale.",
        "5. Save the final decision with confidence score.",
    ],
    AnalysisMode.socratic: [
        "1. Identify what is unclear or ambiguous in the request.",
        "2. Ask targeted clarifying questions (one at a time).",
        "3. Confirm understanding before proceeding.",
        "4. Restate requirements in your own words for validation.",
        "5. Proceed with analysis only after requirements are resolved.",
    ],
}


def route(
    task_description: str,
    task_type_hint: str | None = None,
) -> AnalysisResult:
    text = (task_description + " " + (task_type_hint or "")).lower()

    if task_type_hint:
        hint = task_type_hint.lower()
        if any(k in hint for k in _SEQUENTIAL_KEYWORDS):
            return _result(AnalysisMode.sequential, "task_type_hint matched sequential keywords")
        if any(k in hint for k in _DEBATE_KEYWORDS):
            return _result(AnalysisMode.debate, "task_type_hint matched debate keywords")
        if any(k in hint for k in _SOCRATIC_KEYWORDS):
            return _result(AnalysisMode.socratic, "task_type_hint matched socratic keywords")

    debate_score = sum(1 for k in _DEBATE_KEYWORDS if k in text)
    socratic_score = sum(1 for k in _SOCRATIC_KEYWORDS if k in text)
    sequential_score = sum(1 for k in _SEQUENTIAL_KEYWORDS if k in text)

    if debate_score > max(sequential_score, socratic_score):
        return _result(AnalysisMode.debate, "task description suggests trade-off evaluation")
    if socratic_score > max(sequential_score, debate_score):
        return _result(AnalysisMode.socratic, "task description suggests requirements discovery")

    return _result(AnalysisMode.sequential, "default: structured multi-step analysis")


def _result(mode: AnalysisMode, rationale: str) -> AnalysisResult:
    return AnalysisResult(
        mode=mode,
        rationale=rationale,
        suggested_steps=_SUGGESTED_STEPS[mode],
    )
