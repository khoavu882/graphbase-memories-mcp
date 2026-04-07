"""
HygieneEngine — 30-day cycle, report-only (no auto-mutation).
FR-58 to FR-61: runs 5 detection queries, returns HygieneReport.
Updates last_hygiene_at ONLY after report generation completes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from neo4j import AsyncDriver

from graphbase_memories.graph.repositories import hygiene_repo
from graphbase_memories.mcp.schemas.results import HygieneReport


async def run(
    project_id: str | None,
    scope: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> HygieneReport:
    """
    Execute all 5 hygiene detection checks. Returns a report.
    Does NOT mutate any nodes — caller must apply changes explicitly.
    """
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

    # Update last_hygiene_at after successful report
    await hygiene_repo.update_hygiene_timestamp(project_id, driver, database)

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
    )
