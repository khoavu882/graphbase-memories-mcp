"""
Lifecycle coordinator: orchestrates startup and save workflows using
Graphbase as the memory backend.

ensure_project: creates storage and writes project.json (atomic).
save_session:   delegates to _session_batch + enrichments.

Implementation prerequisite (review C1):
  Core session batch logic is imported from _session_batch.py to share
  dedup semantics with the Phase 7 store_session_with_learnings tool.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from graphbase_memories._provider import get_engine
from graphbase_memories._utils import _now
from graphbase_memories.config import Config
from graphbase_memories.lifecycle.resolver import LifecycleProjectResolver
from graphbase_memories.tools._session_batch import (
    make_edge,
    make_node,
    store_session_batch,
)
from graphbase_memories.tools._types import MemoryInput


class LifecycleCoordinator:
    """Orchestrate lifecycle workflows: bootstrap and session save."""

    def __init__(self, config: Config, resolver: LifecycleProjectResolver) -> None:
        self._config = config
        self._resolver = resolver

    def ensure_project(
        self,
        project_id: str,
        workspace_root: str | None = None,
        initialize_context: bool = False,
    ) -> dict:
        """
        Create or validate project storage.

        If memories.db already exists, returns {created: false}.
        Otherwise, creates the project directory, initialises the DB schema,
        writes project.json, and optionally seeds a bootstrap context memory.

        Returns:
            {project_id, created, db_initialized, context_seeded}
        """
        db_path = self._config.data_dir / project_id / "memories.db"

        if db_path.exists():
            # Touch last_loaded_at (best-effort)
            self._update_last_loaded(project_id)
            return {
                "project_id": project_id,
                "created": False,
                "db_initialized": True,
                "context_seeded": False,
            }

        # --- Create storage ---
        project_dir = self._config.data_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        # Instantiate engine — creates DB schema
        engine = get_engine(project_id)

        # Write project.json (atomic)
        self._write_project_json(project_id, workspace_root)

        # Optional context seed
        context_seeded = False
        if initialize_context:
            seed_node = make_node(
                project_id,
                MemoryInput(
                    title="Project initialized",
                    content=f"Bootstrap record for {project_id}.",
                    tags=["init:v1"],
                ),
                "context",
            )
            engine.store_memory_with_entities(seed_node, [])
            context_seeded = True

        return {
            "project_id": project_id,
            "created": True,
            "db_initialized": True,
            "context_seeded": context_seeded,
        }

    def save_session(
        self,
        project_id: str,
        session: MemoryInput,
        decisions: list[MemoryInput],
        patterns: list[MemoryInput],
        context_items: list[MemoryInput] | None = None,
        entity_facts: list[dict] | None = None,
    ) -> dict:
        """
        High-level save endpoint for lifecycle skills.

        1. Validates project exists (fails if not initialized)
        2. Delegates core session+decisions+patterns to store_session_batch
        3. Stores context_items as type="context" with LEARNED_DURING edges
        4. Stores entity_facts as type="entity_fact" with LEARNED_DURING edges

        Returns:
            {session_id, decisions, patterns, context_items, entity_facts, errors}
        """
        # --- Precondition: project must exist ---
        db_path = self._config.data_dir / project_id / "memories.db"
        if not db_path.exists():
            return {
                "error": "project_not_initialized",
                "message": f"Project '{project_id}' not found. Call ensure_project first.",
            }

        engine = get_engine(project_id)

        # --- Core batch: session + decisions + patterns ---
        result = store_session_batch(engine, project_id, session, decisions, patterns)
        session_id = result["session_id"]
        errors = list(result.get("errors", []))

        # --- Context items ---
        context_items_out: list[dict] = []
        for i, item in enumerate(context_items or []):
            try:
                node = make_node(project_id, item, "context")
                node = engine.store_memory_with_entities(
                    node, item.get("entities") or []
                )
                engine.store_edge(
                    make_edge(node.id, session_id, "LEARNED_DURING")
                )
                context_items_out.append({"id": node.id})
            except Exception as exc:
                errors.append({"index": i, "type": "context_item", "message": str(exc)})

        # --- Entity facts ---
        entity_facts_out: list[dict] = []
        for i, fact in enumerate(entity_facts or []):
            try:
                entity_name = fact["entity_name"]
                entity_type = fact.get("entity_type", "concept")
                fact_input = MemoryInput(
                    title=fact["title"],
                    content=fact["content"],
                    tags=fact.get("tags") or [],
                )
                node = make_node(project_id, fact_input, "entity_fact")
                node = engine.store_memory_with_entities(node, [entity_name])
                engine.store_edge(
                    make_edge(node.id, session_id, "LEARNED_DURING")
                )
                entity_facts_out.append({"id": node.id})
            except Exception as exc:
                errors.append({"index": i, "type": "entity_fact", "message": str(exc)})

        return {
            "session_id": session_id,
            "decisions": result["decisions"],
            "patterns": result["patterns"],
            "context_items": context_items_out,
            "entity_facts": entity_facts_out,
            "errors": errors,
        }

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    def _write_project_json(self, project_id: str, workspace_root: str | None) -> None:
        """Write project.json using atomic rename pattern (review C2)."""
        project_dir = self._config.data_dir / project_id
        target = project_dir / "project.json"
        tmp = target.with_suffix(".json.tmp")

        now = _now()
        data = {
            "project_id": project_id,
            "workspace_root": workspace_root or "",
            "created_at": now,
            "last_loaded_at": now,
        }

        tmp.write_text(json.dumps(data, indent=2))
        os.rename(str(tmp), str(target))

    def _update_last_loaded(self, project_id: str) -> None:
        """Best-effort update of last_loaded_at in project.json (review m3)."""
        target = self._config.data_dir / project_id / "project.json"
        try:
            if target.exists():
                data = json.loads(target.read_text())
                data["last_loaded_at"] = _now()
                tmp = target.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(data, indent=2))
                os.rename(str(tmp), str(target))
        except OSError:
            pass  # best-effort — concurrent access or read-only FS
