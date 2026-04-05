"""
CLI integration tests: inject, inspect subcommands. [B2 fix]
Uses subprocess to test the full import chain independently of in-process MCP tests.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


def _run_cli(args: list[str], tmp_path, input_text: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "GRAPHBASE_DATA_DIR": str(tmp_path)}
    return subprocess.run(
        [sys.executable, "-m", "graphbase_memories"] + args,
        capture_output=True, text=True, env=env,
        timeout=10,
    )


# ---------------------------------------------------------------------------
# inject subcommand
# ---------------------------------------------------------------------------

def test_inject_empty_project_exits_zero(tmp_path):
    """[B2] inject for an unknown project must exit 0 with no traceback."""
    result = _run_cli(["inject", "--project", "no-memories"], tmp_path)
    assert result.returncode == 0
    assert result.stderr == ""


def test_inject_empty_project_no_output(tmp_path):
    """[B2] inject for a project with no memories must produce empty stdout."""
    result = _run_cli(["inject", "--project", "empty"], tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_inject_with_memories_outputs_yaml(tmp_path):
    """[B2] inject must output YAML when project has memories."""
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine
    from graphbase_memories.graph.engine import MemoryNode
    from datetime import datetime, timezone
    from uuid import uuid4

    cfg = Config(backend="sqlite", data_dir=tmp_path, log_level="WARNING", log_to_file=False)
    eng = SQLiteEngine(cfg, "cli-test")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    mem = MemoryNode(
        id=str(uuid4()), project="cli-test", type="decision",
        title="Use async calls", content="All inter-service calls must be async.",
        tags=["arch"], created_at=now, updated_at=now,
        valid_until=None, is_deleted=False,
    )
    eng.store_memory_with_entities(mem, ["event-bus"])

    result = _run_cli(["inject", "--project", "cli-test"], tmp_path)
    assert result.returncode == 0
    assert result.stderr == ""
    assert "decisions:" in result.stdout
    assert "async" in result.stdout.lower()


def test_inject_max_tokens_respected(tmp_path):
    """[B2+Q3] inject --max-tokens limits output size."""
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine
    from graphbase_memories.graph.engine import MemoryNode
    from datetime import datetime, timezone
    from uuid import uuid4

    cfg = Config(backend="sqlite", data_dir=tmp_path, log_level="WARNING", log_to_file=False)
    eng = SQLiteEngine(cfg, "token-test")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    for i in range(10):
        mem = MemoryNode(
            id=str(uuid4()), project="token-test", type="decision",
            title=f"Decision {i}", content="x" * 400,
            tags=[], created_at=now, updated_at=now,
            valid_until=None, is_deleted=False,
        )
        eng.store_memory_with_entities(mem, [])

    result = _run_cli(["inject", "--project", "token-test", "--max-tokens", "80"], tmp_path)
    assert result.returncode == 0
    output_tokens = len(result.stdout) // 4
    assert output_tokens <= 92  # 80 + 15% margin


# ---------------------------------------------------------------------------
# inspect subcommand
# ---------------------------------------------------------------------------

def test_inspect_empty_project_no_memories_message(tmp_path):
    """[B2] inspect must print a friendly message for an empty project."""
    result = _run_cli(["inspect", "--project", "nothing"], tmp_path)
    assert result.returncode == 0
    assert "no memories" in result.stdout.lower()


def test_inspect_lists_memories(tmp_path):
    """[B2] inspect must list memory titles for a non-empty project."""
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine
    from graphbase_memories.graph.engine import MemoryNode
    from datetime import datetime, timezone
    from uuid import uuid4

    cfg = Config(backend="sqlite", data_dir=tmp_path, log_level="WARNING", log_to_file=False)
    eng = SQLiteEngine(cfg, "inspect-test")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    mem = MemoryNode(
        id=str(uuid4()), project="inspect-test", type="pattern",
        title="Retry pattern", content="Exponential backoff.",
        tags=["resilience"], created_at=now, updated_at=now,
        valid_until=None, is_deleted=False,
    )
    eng.store_memory_with_entities(mem, [])

    result = _run_cli(["inspect", "--project", "inspect-test"], tmp_path)
    assert result.returncode == 0
    assert "Retry pattern" in result.stdout
    assert "pattern" in result.stdout
