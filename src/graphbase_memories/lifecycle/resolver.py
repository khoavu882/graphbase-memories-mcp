"""
Lifecycle project resolver: derives a canonical Graphbase project ID from
the current workspace.

Resolution precedence:
  1. project_override (explicit) → identity_mode = "override"
  2. project.json mapping for workspace_root → identity_mode = "project-json"
  3. Legacy slug-compatible directory lookup → identity_mode = "legacy-slug"
  4. Repo-basename slug from workspace_root → identity_mode = "workspace-derived"
  5. Repo-basename + stable hash suffix on collision → identity_mode = "workspace-derived"

Design constraint: identity_mode is returned for diagnostic purposes;
callers should not branch on it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from graphbase_memories._provider import list_known_project_ids
from graphbase_memories.config import Config


@dataclass
class ResolvedProject:
    """Result of workspace → project-ID resolution."""

    project_id: str          # canonical key for get_engine()
    project_slug: str        # human-readable slug (may equal project_id)
    workspace_root: str      # canonical absolute path
    storage_path: Path       # e.g. ~/.graphbase/<project_id>/
    exists: bool             # True if memories.db exists at storage_path
    identity_mode: str       # "override" | "project-json" | "legacy-slug" | "workspace-derived"


class LifecycleProjectResolver:
    """Map a workspace path to a canonical Graphbase project namespace."""

    def __init__(self, config: Config) -> None:
        self._config = config

    def resolve(
        self,
        workspace_root: str,
        cwd: str | None = None,
        project_override: str | None = None,
    ) -> ResolvedProject:
        """
        Resolve the active workspace to a Graphbase project ID.

        Args:
            workspace_root: Absolute path to the repo/workspace root.
            cwd:            Optional current working directory (unused in v1,
                            reserved for monorepo sub-project resolution).
            project_override: Skip all heuristics — use this project ID directly.

        Returns:
            ResolvedProject with the canonical project identity.

        Raises:
            ValueError: If workspace_root is empty/None and project_override
                        is not provided.
        """
        # --- Step 1: Explicit override ---
        if project_override:
            storage_path = self._config.data_dir / project_override
            return ResolvedProject(
                project_id=project_override,
                project_slug=project_override,
                workspace_root=workspace_root or "",
                storage_path=storage_path,
                exists=(storage_path / "memories.db").exists(),
                identity_mode="override",
            )

        if not workspace_root:
            raise ValueError(
                "workspace_root is required when project_override is not set. "
                "The MCP server cannot infer the active workspace in stdio mode."
            )

        canonical = str(Path(workspace_root).resolve())
        slug = self._slugify(canonical)

        # --- Step 2: project.json mapping ---
        mapped = self._find_project_json_match(canonical)
        if mapped:
            storage_path = self._config.data_dir / mapped
            return ResolvedProject(
                project_id=mapped,
                project_slug=slug,
                workspace_root=canonical,
                storage_path=storage_path,
                exists=(storage_path / "memories.db").exists(),
                identity_mode="project-json",
            )

        # --- Step 3: Legacy slug ---
        if self._find_legacy_slug(slug):
            # Verify no collision: slug dir exists but may belong to another workspace
            if not self._has_collision(slug, canonical):
                storage_path = self._config.data_dir / slug
                return ResolvedProject(
                    project_id=slug,
                    project_slug=slug,
                    workspace_root=canonical,
                    storage_path=storage_path,
                    exists=True,
                    identity_mode="legacy-slug",
                )

        # --- Step 4 & 5: Workspace-derived slug (with collision handling) ---
        project_id = slug
        if self._has_collision(slug, canonical):
            project_id = f"{slug}-{self._hash_suffix(canonical)}"

        storage_path = self._config.data_dir / project_id
        return ResolvedProject(
            project_id=project_id,
            project_slug=slug,
            workspace_root=canonical,
            storage_path=storage_path,
            exists=(storage_path / "memories.db").exists(),
            identity_mode="workspace-derived",
        )

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _slugify(canonical_path: str) -> str:
        """Derive a filesystem-safe slug from a canonical workspace path."""
        slug = Path(canonical_path).name.lower().replace(" ", "-")
        slug = re.sub(r"[^a-z0-9_-]", "", slug)
        return slug or "unnamed-project"

    def _has_collision(self, slug: str, canonical_root: str) -> bool:
        """Check if slug is used by a different workspace."""
        project_json = self._config.data_dir / slug / "project.json"
        if project_json.exists():
            try:
                data = json.loads(project_json.read_text())
                return data.get("workspace_root") != canonical_root
            except (json.JSONDecodeError, OSError):
                return False
        return False

    @staticmethod
    def _hash_suffix(canonical: str) -> str:
        """Stable 8-char hash suffix for collision disambiguation."""
        return hashlib.sha256(canonical.encode()).hexdigest()[:8]

    def _find_project_json_match(self, canonical_root: str) -> str | None:
        """Scan all project.json files for a matching workspace_root."""
        data_dir = self._config.data_dir
        if not data_dir.exists():
            return None
        for subdir in data_dir.iterdir():
            pj = subdir / "project.json"
            if pj.exists():
                try:
                    data = json.loads(pj.read_text())
                    if data.get("workspace_root") == canonical_root:
                        return subdir.name
                except (json.JSONDecodeError, OSError):
                    continue
        return None

    def _find_legacy_slug(self, slug: str) -> bool:
        """Check if a slug directory exists on disk with a memories.db."""
        known = list_known_project_ids()
        return slug in known
