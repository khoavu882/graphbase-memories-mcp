"""
HygieneEngine — 30-day cycle, report-only (no auto-mutation).
FR-58 to FR-61: runs 5 detection queries, returns HygieneReport.
Updates last_hygiene_at ONLY after report generation completes.

check_pending_only fast-path: skips all content scans, returns only pending/failed
write state. Does NOT update last_hygiene_at or run token cleanup.
"""

from __future__ import annotations

from datetime import UTC, datetime

from neo4j import AsyncDriver

from graphbase_memories.domain.results import HygieneReport
from graphbase_memories.graph.repositories import hygiene_repo, token_repo


async def run(
    project_id: str | None,
    scope: str,
    driver: AsyncDriver,
    database: str = "neo4j",
    check_pending_only: bool = False,
) -> HygieneReport:
    """
    Execute hygiene detection checks. Returns a report.
    Does NOT mutate any nodes — caller must apply changes explicitly.

    When check_pending_only=True: skips all content scans (duplicates, outdated,
    obsolete, drift) and returns only pending/failed write state. Does NOT update
    last_hygiene_at or run token cleanup.
    """
    if check_pending_only:
        unresolved = await hygiene_repo.find_unresolved_saves(project_id, driver, database)
        pending_ids = [r["id"] for r in unresolved]
        oldest_at: datetime | None = None
        if unresolved:
            oldest_raw = unresolved[-1].get("created_at")  # ordered DESC, last = oldest
            if oldest_raw is not None:
                oldest_at = (
                    oldest_raw.to_native()
                    if hasattr(oldest_raw, "to_native")
                    else datetime.fromisoformat(str(oldest_raw))
                )
        return HygieneReport(
            project_id=project_id,
            scope=scope,
            duplicates_found=0,
            outdated_decisions=0,
            obsolete_patterns=0,
            entity_drift_count=0,
            unresolved_saves=len(unresolved),
            candidate_ids={},
            checked_at=datetime.now(UTC),
            pending_only=True,
            pending_artifact_ids=pending_ids,
            oldest_pending_at=oldest_at,
            next_step=(
                f"Resolve {len(unresolved)} pending save(s) by retrying "
                "store_session_with_learnings() for each pending artifact."
                if unresolved
                else "No pending saves. All writes resolved."
            ),
        )

    duplicates = await hygiene_repo.find_duplicate_decisions(project_id, driver, database)
    outdated = await hygiene_repo.find_outdated_decisions(project_id, driver, database)
    obsolete = await hygiene_repo.find_obsolete_patterns(project_id, driver, database)
    drift = await hygiene_repo.find_entity_drift(project_id, driver, database)
    unresolved = await hygiene_repo.find_unresolved_saves(project_id, driver, database)

    candidate_ids = {
        "duplicate_decisions": [f"{r['id1']}+{r['id2']}" for r in duplicates],
        "outdated_decisions": [r["id"] for r in outdated],
        "obsolete_patterns": [r["id"] for r in obsolete],
        "entity_drift": [f"{r['id1']}+{r['id2']}" for r in drift],
        "unresolved_saves": [r["id"] for r in unresolved],
    }

    # Clean up expired/used GovernanceTokens as part of each hygiene cycle
    await token_repo.cleanup_expired(driver, database)

    # Update last_hygiene_at after successful report
    await hygiene_repo.update_hygiene_timestamp(project_id, driver, database)

    if len(duplicates) > 0 or len(unresolved) > 0:
        hygiene_next_step = (
            f"Run run_hygiene(project_id='{project_id}', scope='{scope}') "
            "to merge duplicates and resolve pending saves."
        )
    elif len(outdated) > 0 or len(obsolete) > 0:
        hygiene_next_step = (
            "Review outdated artifacts: retrieve_context then save_decision to supersede old ones."
        )
    else:
        hygiene_next_step = "Graph is clean. No action required."

    return HygieneReport(
        project_id=project_id,
        scope=scope,
        duplicates_found=len(duplicates),
        outdated_decisions=len(outdated),
        obsolete_patterns=len(obsolete),
        entity_drift_count=len(drift),
        unresolved_saves=len(unresolved),
        candidate_ids=candidate_ids,
        checked_at=datetime.now(UTC),
        next_step=hygiene_next_step,
    )
