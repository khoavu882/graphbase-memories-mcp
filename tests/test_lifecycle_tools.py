"""
Tests for Phase 8 lifecycle tools.

Test matrix (19 tests):
  Resolution:  test_resolve_same_workspace_yields_same_id,
               test_resolve_with_override, test_resolve_legacy_slug_reused,
               test_resolve_collision_appends_hash, test_resolve_canonical_path
  Bootstrap:   test_ensure_creates_storage, test_ensure_idempotent,
               test_ensure_with_initialize_context
  Context:     test_lifecycle_context_existing, test_lifecycle_context_empty,
               test_lifecycle_context_entity_filter,
               test_lifecycle_context_stale_warnings,
               test_lifecycle_context_includes_inventory
  Save/Load:   test_save_session_continuity, test_save_with_context_items,
               test_save_with_entity_facts, test_save_partial_failure
  Misc:        test_list_tools_static, test_data_dir_fallback
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from conftest import PROJECT, parse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_decision(mcp, project: str, title: str, content: str):
    """Store a decision memory for test setup."""
    return mcp.call_tool("store_memory", {
        "project": project,
        "type": "decision",
        "title": title,
        "content": content,
        "tags": ["test"],
    })


def _seed_pattern(mcp, project: str, title: str, content: str):
    """Store a pattern memory for test setup."""
    return mcp.call_tool("store_memory", {
        "project": project,
        "type": "pattern",
        "title": title,
        "content": content,
        "tags": ["test"],
    })


# ===================================================================
# Resolution tests
# ===================================================================


class TestResolve:
    """Tests for resolve_active_project."""

    @pytest.mark.asyncio
    async def test_resolve_same_workspace_yields_same_id(self, mcp, tmp_path):
        ws = str(tmp_path / "my-project")
        Path(ws).mkdir()
        r1 = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": ws,
        }))
        r2 = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": ws,
        }))
        assert r1["project_id"] == r2["project_id"]
        assert r1["project_slug"] == "my-project"

    @pytest.mark.asyncio
    async def test_resolve_with_override(self, mcp, tmp_path):
        r = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": str(tmp_path),
            "project_override": "custom-slug",
        }))
        assert r["project_id"] == "custom-slug"
        assert r["identity_mode"] == "override"

    @pytest.mark.asyncio
    async def test_resolve_legacy_slug_reused(self, mcp, engine, tmp_path):
        # The engine fixture creates PROJECT ("test") in tmp_path (the data_dir).
        # So "test" is a known legacy slug.
        ws = str(tmp_path / "test")
        Path(ws).mkdir(exist_ok=True)
        r = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": ws,
        }))
        assert r["project_id"] == "test"
        assert r["identity_mode"] == "legacy-slug"
        assert r["exists"] is True

    @pytest.mark.asyncio
    async def test_resolve_collision_appends_hash(self, mcp, tmp_path):
        # Create two workspaces with the same basename
        ws1 = tmp_path / "parent1" / "myapp"
        ws2 = tmp_path / "parent2" / "myapp"
        ws1.mkdir(parents=True)
        ws2.mkdir(parents=True)

        # Resolve first workspace — gets the base slug
        r1 = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": str(ws1),
        }))
        # Ensure project for first workspace (creates project.json)
        await mcp.call_tool("ensure_project", {
            "project_id": r1["project_id"],
            "workspace_root": str(ws1),
        })

        # Resolve second workspace — should detect collision and append hash
        r2 = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": str(ws2),
        }))
        assert r1["project_id"] != r2["project_id"]
        assert r2["project_id"].startswith("myapp-")

    @pytest.mark.asyncio
    async def test_resolve_canonical_path(self, mcp, tmp_path):
        # Create a symlink pointing to a real directory
        real = tmp_path / "real-project"
        real.mkdir()
        link = tmp_path / "link-project"
        link.symlink_to(real)

        r_real = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": str(real),
        }))
        r_link = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": str(link),
        }))
        # Both should resolve to the same canonical project ID
        assert r_real["project_id"] == r_link["project_id"]

    @pytest.mark.asyncio
    async def test_resolve_no_workspace_raises_error(self, mcp):
        r = parse(await mcp.call_tool("resolve_active_project", {
            "workspace_root": "",
        }))
        assert "error" in r
        assert r["error"] == "resolution_failed"


# ===================================================================
# Bootstrap tests
# ===================================================================


class TestEnsure:
    """Tests for ensure_project."""

    @pytest.mark.asyncio
    async def test_ensure_creates_storage(self, mcp, tmp_path):
        r = parse(await mcp.call_tool("ensure_project", {
            "project_id": "new-proj",
            "workspace_root": str(tmp_path / "new-proj"),
        }))
        assert r["created"] is True
        assert r["db_initialized"] is True
        assert r["context_seeded"] is False
        assert (tmp_path / "new-proj" / "memories.db").exists()
        assert (tmp_path / "new-proj" / "project.json").exists()

    @pytest.mark.asyncio
    async def test_ensure_idempotent(self, mcp, tmp_path):
        await mcp.call_tool("ensure_project", {
            "project_id": "idempotent",
            "workspace_root": str(tmp_path / "idempotent"),
        })
        r = parse(await mcp.call_tool("ensure_project", {
            "project_id": "idempotent",
            "workspace_root": str(tmp_path / "idempotent"),
        }))
        assert r["created"] is False
        assert r["db_initialized"] is True

    @pytest.mark.asyncio
    async def test_ensure_with_initialize_context(self, mcp, tmp_path):
        r = parse(await mcp.call_tool("ensure_project", {
            "project_id": "seeded",
            "workspace_root": str(tmp_path / "seeded"),
            "initialize_context": True,
        }))
        assert r["context_seeded"] is True
        # Verify seed memory exists
        memories = parse(await mcp.call_tool("list_memories", {
            "project": "seeded",
        }))
        assert len(memories) >= 1
        assert any(m["title"] == "Project initialized" for m in memories)


# ===================================================================
# Context assembly tests
# ===================================================================


class TestLifecycleContext:
    """Tests for get_lifecycle_context."""

    @pytest.mark.asyncio
    async def test_lifecycle_context_existing(self, mcp, engine):
        # Seed some data
        await _seed_decision(mcp, PROJECT, "Use SQLite for v1", "SQLite is simpler.")
        await _seed_pattern(mcp, PROJECT, "Atomic writes everywhere", "Use temp+rename.")

        r = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": PROJECT,
        }))
        assert r["project_id"] == PROJECT
        assert r["bootstrap_state"] == "existing"
        assert len(r["decisions"]) >= 1
        assert len(r["patterns"]) >= 1
        assert r["yaml_context"] != ""
        assert "api_version" in r["tool_inventory"]

    @pytest.mark.asyncio
    async def test_lifecycle_context_empty(self, mcp, tmp_path):
        # Ensure a fresh empty project
        await mcp.call_tool("ensure_project", {
            "project_id": "empty-proj",
        })
        r = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": "empty-proj",
        }))
        assert r["bootstrap_state"] == "empty"
        assert r["decisions"] == []
        assert r["patterns"] == []
        assert r["recent_sessions"] == []

    @pytest.mark.asyncio
    async def test_lifecycle_context_entity_filter(self, mcp, engine):
        # Store a memory linked to an entity
        await mcp.call_tool("store_memory", {
            "project": PROJECT,
            "type": "decision",
            "title": "Auth uses JWT",
            "content": "JWT for stateless auth.",
            "tags": ["auth"],
            "entities": ["auth-service"],
        })
        r = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": PROJECT,
            "entity": "auth-service",
            "entity_type": "service",
        }))
        assert r["bootstrap_state"] == "existing"
        # YAML context should reference this entity
        assert r["yaml_context"] != ""

    @pytest.mark.asyncio
    async def test_lifecycle_context_stale_warnings(self, mcp, engine):
        # Store and then age a memory (manually patch updated_at)
        r = parse(await _seed_decision(mcp, PROJECT, "Old decision", "Outdated."))
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        engine._con.execute(
            "UPDATE memories SET updated_at = ? WHERE id = ?",
            (old_date, r["id"]),
        )
        engine._con.commit()

        ctx = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": PROJECT,
        }))
        stale_ids = [w["id"] for w in ctx["stale_warnings"]]
        assert r["id"] in stale_ids

    @pytest.mark.asyncio
    async def test_lifecycle_context_includes_inventory(self, mcp, engine):
        await _seed_decision(mcp, PROJECT, "Dummy", "For inventory test.")
        r = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": PROJECT,
            "include_inventory": True,
        }))
        assert "lifecycle" in r["tool_inventory"]
        assert "resolve_active_project" in r["tool_inventory"]["lifecycle"]

    @pytest.mark.asyncio
    async def test_lifecycle_context_no_inventory(self, mcp, engine):
        await _seed_decision(mcp, PROJECT, "Dummy2", "For no-inventory test.")
        r = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": PROJECT,
            "include_inventory": False,
        }))
        assert r["tool_inventory"] == {}

    @pytest.mark.asyncio
    async def test_lifecycle_context_small_project_uses_single_list_query(self, mcp, engine, monkeypatch):
        """[v3] Small projects should reuse the initial list_memories fetch."""
        original_list_memories = engine.list_memories
        list_calls: list[tuple[tuple, dict]] = []

        def counted_list_memories(*args, **kwargs):
            list_calls.append((args, kwargs))
            return original_list_memories(*args, **kwargs)

        monkeypatch.setattr(engine, "list_memories", counted_list_memories)

        for i in range(10):
            await mcp.call_tool("store_memory", {
                "project": PROJECT,
                "type": "decision",
                "title": f"Decision {i}",
                "content": "d",
                "tags": [],
                "entities": [],
            })
            await mcp.call_tool("store_memory", {
                "project": PROJECT,
                "type": "pattern",
                "title": f"Pattern {i}",
                "content": "p",
                "tags": [],
                "entities": [],
            })
            await mcp.call_tool("store_memory", {
                "project": PROJECT,
                "type": "session",
                "title": f"Session {i}",
                "content": "s",
                "tags": [],
                "entities": [],
            })

        r = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": PROJECT,
        }))
        assert len(r["decisions"]) == 10
        assert len(r["patterns"]) == 10
        assert len(r["recent_sessions"]) == 5
        assert len(list_calls) == 1

    @pytest.mark.asyncio
    async def test_lifecycle_context_falls_back_only_for_missing_sparse_type(self, mcp, engine, monkeypatch):
        """[v3] Saturated top-50 should trigger a targeted fallback only for absent types."""
        original_list_memories = engine.list_memories
        list_calls: list[tuple[tuple, dict]] = []

        def counted_list_memories(*args, **kwargs):
            list_calls.append((args, kwargs))
            return original_list_memories(*args, **kwargs)

        monkeypatch.setattr(engine, "list_memories", counted_list_memories)

        await mcp.call_tool("store_memory", {
            "project": PROJECT,
            "type": "decision",
            "title": "Old decision",
            "content": "old",
            "tags": [],
            "entities": [],
        })
        for i in range(60):
            await mcp.call_tool("store_memory", {
                "project": PROJECT,
                "type": "context",
                "title": f"Context {i}",
                "content": "ctx",
                "tags": [],
                "entities": [],
            })
        await mcp.call_tool("store_memory", {
            "project": PROJECT,
            "type": "pattern",
            "title": "Recent pattern",
            "content": "pattern",
            "tags": [],
            "entities": [],
        })

        r = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": PROJECT,
            "include_recent_sessions": False,
        }))
        assert any(item["title"] == "Old decision" for item in r["decisions"])
        assert any(item["title"] == "Recent pattern" for item in r["patterns"])
        assert len(list_calls) == 2


# ===================================================================
# Save/load continuity tests
# ===================================================================


class TestSaveSession:
    """Tests for save_session_context."""

    @pytest.mark.asyncio
    async def test_save_session_continuity(self, mcp, engine):
        r = parse(await mcp.call_tool("save_session_context", {
            "project_id": PROJECT,
            "session": {
                "title": "Session: lifecycle validation",
                "content": "Validated lifecycle APIs end-to-end.",
                "entities": [],
                "tags": ["test-session"],
            },
            "decisions": [{
                "title": "Keep 3-call load protocol",
                "content": "Resolve→Ensure→Context gives clients control.",
                "entities": [],
                "tags": ["architecture"],
            }],
            "patterns": [{
                "title": "Atomic writes pattern",
                "content": "All project.json writes use temp+rename.",
                "entities": [],
                "tags": ["reliability"],
            }],
        }))
        assert "session_id" in r
        assert len(r["decisions"]) == 1
        assert len(r["patterns"]) == 1
        assert r["errors"] == []

        # Verify round-trip via lifecycle context
        ctx = parse(await mcp.call_tool("get_lifecycle_context", {
            "project_id": PROJECT,
        }))
        session_titles = [s["title"] for s in ctx["recent_sessions"]]
        assert "Session: lifecycle validation" in session_titles

    @pytest.mark.asyncio
    async def test_save_with_context_items(self, mcp, engine):
        r = parse(await mcp.call_tool("save_session_context", {
            "project_id": PROJECT,
            "session": {
                "title": "Session: ctx items",
                "content": "Testing context items.",
                "entities": [],
                "tags": ["test"],
            },
            "decisions": [],
            "patterns": [],
            "context_items": [{
                "title": "Dev environment setup",
                "content": "Python 3.14, uv for deps.",
                "entities": [],
                "tags": ["devenv"],
            }],
        }))
        assert len(r["context_items"]) == 1
        assert "id" in r["context_items"][0]

    @pytest.mark.asyncio
    async def test_save_with_entity_facts(self, mcp, engine):
        r = parse(await mcp.call_tool("save_session_context", {
            "project_id": PROJECT,
            "session": {
                "title": "Session: entity facts",
                "content": "Testing entity facts.",
                "entities": [],
                "tags": ["test"],
            },
            "decisions": [],
            "patterns": [],
            "entity_facts": [{
                "title": "Auth service uses Redis",
                "content": "Redis backs token revocation.",
                "entity_name": "auth-service",
                "entity_type": "service",
                "tags": ["runtime"],
            }],
        }))
        assert len(r["entity_facts"]) == 1
        assert "id" in r["entity_facts"][0]

    @pytest.mark.asyncio
    async def test_save_partial_failure(self, mcp, engine):
        """A bad decision doesn't prevent good ones from being stored."""
        r = parse(await mcp.call_tool("save_session_context", {
            "project_id": PROJECT,
            "session": {
                "title": "Session: partial failure",
                "content": "Testing partial failure handling.",
                "entities": [],
                "tags": ["test"],
            },
            "decisions": [
                {
                    "title": "Good decision",
                    "content": "This should succeed.",
                    "entities": [],
                    "tags": [],
                },
            ],
            "patterns": [],
            "entity_facts": [
                {
                    # Missing required 'title' — should fail
                    "content": "No title here.",
                    "entity_name": "broken",
                },
            ],
        }))
        assert len(r["decisions"]) == 1  # good decision saved
        # Entity fact may fail (missing title) — but session + decisions still saved
        assert "session_id" in r

    @pytest.mark.asyncio
    async def test_save_without_ensure_fails(self, mcp):
        """save_session_context must fail if project isn't initialized."""
        r = parse(await mcp.call_tool("save_session_context", {
            "project_id": "nonexistent-project",
            "session": {
                "title": "Should fail",
                "content": "Project doesn't exist.",
                "entities": [],
                "tags": [],
            },
            "decisions": [],
            "patterns": [],
        }))
        assert r.get("error") == "project_not_initialized"


# ===================================================================
# Misc tests
# ===================================================================


class TestMisc:
    """Tests for list_available_tools and data dir selection."""

    @pytest.mark.asyncio
    async def test_list_tools_static(self, mcp):
        r = parse(await mcp.call_tool("list_available_tools", {}))
        assert r["api_version"] == "8.0"
        assert "write" in r
        assert "lifecycle" in r
        assert "resolve_active_project" in r["lifecycle"]
        assert len(r["lifecycle"]) == 5

    def test_data_dir_defaults_to_graphbase_without_legacy_fallback(self, tmp_path, monkeypatch):
        """Default data dir is ~/.graphbase even if the legacy dir exists."""
        from graphbase_memories.config import _default_data_dir

        monkeypatch.delenv("GRAPHBASE_DATA_DIR", raising=False)
        new_dir = tmp_path / ".graphbase"
        legacy_dir = tmp_path / ".graphbase-memories"

        # Patch home expansion for test isolation
        monkeypatch.setattr(
            "graphbase_memories.config.Path.expanduser",
            lambda self: tmp_path / self.name if str(self).startswith("~") else self,
        )

        # Case: neither exists → new default
        result = _default_data_dir()
        assert result.name == ".graphbase"

        # Case: only legacy exists → still new default
        legacy_dir.mkdir()
        result = _default_data_dir()
        assert result == new_dir

        # Case: both exist → prefer new
        new_dir.mkdir()
        result = _default_data_dir()
        assert result == new_dir

    def test_data_dir_env_override(self, tmp_path, monkeypatch):
        """GRAPHBASE_DATA_DIR env var takes precedence."""
        from graphbase_memories.config import _default_data_dir

        custom = tmp_path / "custom"
        monkeypatch.setenv("GRAPHBASE_DATA_DIR", str(custom))
        result = _default_data_dir()
        assert result == custom
