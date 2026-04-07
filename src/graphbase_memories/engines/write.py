"""
WriteEngine — governance gate (S-1), dedup, retry (FR-52), business-output-first (FR-48).

FR-48: business result is always returned regardless of write success.
FR-52: 1 retry on transient ServiceUnavailable before setting pending_retry/failed.
FR-55: global writes require a valid GovernanceToken (validated + consumed in one transaction).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from neo4j import AsyncDriver
from neo4j.exceptions import ServiceUnavailable

from graphbase_memories.config import settings
from graphbase_memories.engines import dedup as dedup_engine
from graphbase_memories.engines import scope as scope_engine
from graphbase_memories.graph.repositories import (
    context_repo,
    decision_repo,
    entity_repo,
    pattern_repo,
    session_repo,
    token_repo,
)
from graphbase_memories.mcp.schemas.artifacts import (
    ContextSchema,
    DecisionSchema,
    EntityFactSchema,
    EntityRelation,
    PatternSchema,
    SessionSchema,
)
from graphbase_memories.mcp.schemas.enums import DedupOutcome, SaveStatus
from graphbase_memories.mcp.schemas.results import BatchSaveResult, SaveResult

logger = logging.getLogger(__name__)


async def save_session(
    session_data: SessionSchema,
    project_id: str,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> SaveResult:
    scope_state = await scope_engine.validate(project_id, focus, driver, database)
    if not scope_engine.is_write_allowed(scope_state):
        return SaveResult(status=SaveStatus.blocked_scope, message=f"Scope state: {scope_state}")

    return await _with_retry(
        _do_save_session,
        session_data=session_data,
        project_id=project_id,
        focus=focus,
        driver=driver,
        database=database,
    )


async def _do_save_session(*, session_data, project_id, focus, driver, database) -> SaveResult:
    node = await session_repo.create(
        objective=session_data.objective,
        actions_taken=session_data.actions_taken,
        decisions_made=session_data.decisions_made,
        open_items=session_data.open_items,
        next_actions=session_data.next_actions,
        save_scope=session_data.save_scope.value,
        project_id=project_id,
        focus=focus,
        driver=driver,
        database=database,
    )
    return SaveResult(status=SaveStatus.saved, artifact_id=node.id)


async def save_decision(
    decision: DecisionSchema,
    project_id: str,
    focus: str | None,
    governance_token: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> SaveResult:
    scope_state = await scope_engine.validate(project_id, focus, driver, database)
    if not scope_engine.is_write_allowed(scope_state):
        return SaveResult(status=SaveStatus.blocked_scope, message=f"Scope state: {scope_state}")

    # Governance gate for global writes (FR-55, S-1)
    if decision.scope.value == "global":
        if not governance_token:
            return SaveResult(
                status=SaveStatus.failed,
                message="Global writes require a governance token. Call request_global_write_approval first.",
            )
        valid = await token_repo.validate_and_consume(governance_token, driver, database)
        if not valid:
            return SaveResult(
                status=SaveStatus.failed,
                message="Governance token is invalid, expired, or already used.",
            )

    return await _with_retry(
        _do_save_decision,
        decision=decision,
        project_id=project_id,
        focus=focus,
        driver=driver,
        database=database,
    )


async def _do_save_decision(*, decision, project_id, focus, driver, database) -> SaveResult:
    new_id = str(uuid.uuid4())
    content_hash = decision_repo.compute_content_hash(decision.title, decision.rationale)

    dedup_outcome, related_id = await dedup_engine.check_decision(
        title=decision.title,
        rationale=decision.rationale,
        content_hash=content_hash,
        scope=decision.scope.value,
        new_id=new_id,
        driver=driver,
        database=database,
    )

    if dedup_outcome == DedupOutcome.duplicate_skip:
        return SaveResult(
            status=SaveStatus.saved,
            artifact_id=related_id,
            dedup_outcome=dedup_outcome,
            message="Duplicate detected — existing record returned.",
        )

    if dedup_outcome == DedupOutcome.manual_review:
        return SaveResult(
            status=SaveStatus.failed,
            dedup_outcome=dedup_outcome,
            message=f"Cannot distinguish duplicate vs supersede. Review candidate: {related_id}",
        )

    node = await decision_repo.create(
        title=decision.title,
        rationale=decision.rationale,
        owner=decision.owner,
        date=decision.date.isoformat(),
        scope=decision.scope.value,
        confidence=decision.confidence,
        project_id=project_id,
        focus=focus,
        dedup_status=dedup_outcome.value,
        driver=driver,
        database=database,
    )

    if dedup_outcome == DedupOutcome.supersede and related_id:
        await decision_repo.add_supersedes(node.id, related_id, driver, database)

    return SaveResult(status=SaveStatus.saved, artifact_id=node.id, dedup_outcome=dedup_outcome)


async def save_pattern(
    pattern: PatternSchema,
    project_id: str,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> SaveResult:
    scope_state = await scope_engine.validate(project_id, focus, driver, database)
    if not scope_engine.is_write_allowed(scope_state):
        return SaveResult(status=SaveStatus.blocked_scope, message=f"Scope state: {scope_state}")

    return await _with_retry(
        _do_save_pattern,
        pattern=pattern,
        project_id=project_id,
        focus=focus,
        driver=driver,
        database=database,
    )


async def _do_save_pattern(*, pattern, project_id, focus, driver, database) -> SaveResult:
    from graphbase_memories.graph.repositories.pattern_repo import compute_content_hash

    content_hash = compute_content_hash(pattern.trigger, pattern.repeatable_steps)
    dedup = await dedup_engine.check_pattern(
        trigger=pattern.trigger,
        content_hash=content_hash,
        scope=pattern.scope.value,
        driver=driver,
        database=database,
    )

    if dedup == DedupOutcome.duplicate_skip:
        return SaveResult(
            status=SaveStatus.saved, dedup_outcome=dedup, message="Duplicate pattern skipped."
        )

    node = await pattern_repo.create(
        trigger=pattern.trigger,
        repeatable_steps=pattern.repeatable_steps,
        exclusions=pattern.exclusions,
        scope=pattern.scope.value,
        last_validated_at=pattern.last_validated_at.isoformat(),
        project_id=project_id,
        focus=focus,
        driver=driver,
        database=database,
    )
    return SaveResult(status=SaveStatus.saved, artifact_id=node.id, dedup_outcome=dedup)


async def save_context(
    context: ContextSchema,
    project_id: str,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> SaveResult:
    scope_state = await scope_engine.validate(project_id, focus, driver, database)
    if not scope_engine.is_write_allowed(scope_state):
        return SaveResult(status=SaveStatus.blocked_scope, message=f"Scope state: {scope_state}")

    node = await context_repo.create(
        content=context.content,
        topic=context.topic,
        scope=context.scope.value,
        relevance_score=context.relevance_score,
        project_id=project_id,
        focus=focus,
        driver=driver,
        database=database,
    )
    return SaveResult(status=SaveStatus.saved, artifact_id=node.id)


async def upsert_entity(
    entity: EntityFactSchema,
    related_entities: list[EntityRelation],
    project_id: str,
    focus: str | None,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> SaveResult:
    scope_state = await scope_engine.validate(project_id, focus, driver, database)
    if not scope_engine.is_write_allowed(scope_state):
        return SaveResult(status=SaveStatus.blocked_scope, message=f"Scope state: {scope_state}")

    node = await entity_repo.upsert(
        entity_name=entity.entity_name,
        fact=entity.fact,
        scope=entity.scope.value,
        project_id=project_id,
        focus=focus,
        driver=driver,
        database=database,
    )

    for rel in related_entities:
        await entity_repo.link_entities(
            node.id, rel.entity_id, rel.relationship_type, driver, database
        )

    return SaveResult(status=SaveStatus.saved, artifact_id=node.id)


async def save_batch(
    session_data: SessionSchema,
    decisions: list[DecisionSchema],
    patterns: list[PatternSchema],
    project_id: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> BatchSaveResult:
    """FR-41: batched save of session + related decisions and patterns."""
    session_result = await save_session(session_data, project_id, None, driver, database)

    decision_results = []
    for d in decisions:
        r = await save_decision(d, project_id, None, None, driver, database)
        decision_results.append(r)
        # Link artifact to session
        if r.artifact_id and session_result.artifact_id:
            await session_repo.link_produced(
                session_result.artifact_id, r.artifact_id, driver, database
            )

    pattern_results = []
    for p in patterns:
        r = await save_pattern(p, project_id, None, driver, database)
        pattern_results.append(r)
        if r.artifact_id and session_result.artifact_id:
            await session_repo.link_produced(
                session_result.artifact_id, r.artifact_id, driver, database
            )

    all_results = [session_result, *decision_results, *pattern_results]
    failed = any(r.status in (SaveStatus.failed, SaveStatus.pending_retry) for r in all_results)
    overall = SaveStatus.partial if failed else SaveStatus.saved

    return BatchSaveResult(
        session=session_result,
        decisions=decision_results,
        patterns=pattern_results,
        overall=overall,
    )


async def _with_retry(fn, **kwargs) -> SaveResult:
    """1 retry on ServiceUnavailable — FR-52."""
    for attempt in range(settings.write_max_retries + 1):
        try:
            return await fn(**kwargs)
        except ServiceUnavailable:
            if attempt < settings.write_max_retries:
                await asyncio.sleep(0.5)
                continue
            return SaveResult(
                status=SaveStatus.pending_retry,
                message="Neo4j unavailable after retry. Save pending.",
            )
        except Exception:
            logger.exception("Write operation failed (attempt %d)", attempt + 1)
            return SaveResult(
                status=SaveStatus.failed,
                message="Write operation failed. Check server logs for details.",
            )
