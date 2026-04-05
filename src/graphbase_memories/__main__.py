"""
CLI entry point for graphbase-memories.

Subcommands:
    server   — Run MCP stdio server (default when no subcommand given)
    inject   — Output context YAML to stdout (called by Claude Code hooks)
    inspect  — List memories in a project (developer inspection)
    doctor   — Health check: Python, fastmcp, data dir, WAL, schema, FTS5
    export   — Export project memories to JSON (full fidelity, stdout by default)
    import   — Import a JSON export file (--merge or --replace)
    setup    — Patch .mcp.json and write Claude Code hook script
    devtools — Launch standalone HTTP DevTools UI for inspecting memories

Usage:
    python -m graphbase_memories              # MCP stdio server
    python -m graphbase_memories server       # MCP stdio server (explicit)
    python -m graphbase_memories server --transport sse --port 8765
    python -m graphbase_memories inject --project <slug> [--entity <name>] [--max-tokens N]
    python -m graphbase_memories inspect --project <slug> [--limit N]
    python -m graphbase_memories doctor [--project <slug>]
    python -m graphbase_memories export --project <slug> [--output -]
    python -m graphbase_memories import --file <path> [--merge | --replace]
    python -m graphbase_memories setup [--project-dir .] [--dry-run]
    python -m graphbase_memories devtools --project <slug> [--port 3001] [--static-dir <path>]

Environment variables (override via settings.json env block):
    GRAPHBASE_BACKEND    sqlite (default) | neo4j
    GRAPHBASE_DATA_DIR   ~/.graphbase (default)
    GRAPHBASE_LOG_LEVEL  WARNING (default)

[B2 FIX] This dual-mode entry point allows hooks to call:
    python -m graphbase_memories inject --project X
without starting the full MCP stdio server.
"""

import argparse
import json
import os
import pathlib
import sys
import threading
from dataclasses import dataclass


_ACTIVE_CONTEXT_PATH = pathlib.Path.home() / ".claude" / "session-env" / "active-context.json"


@dataclass(frozen=True)
class _ResolvedProject:
    project: str | None
    source: str | None


@dataclass(frozen=True)
class _DevtoolsSidecarConfig:
    project: str
    source: str
    host: str
    port: int
    open_browser: bool


def _read_active_context_project() -> str | None:
    """Best-effort restore of project identity from local active-context metadata."""
    try:
        data = json.loads(_ACTIVE_CONTEXT_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("project_id") or data.get("project_name")


def _resolve_devtools_project(explicit_project: str | None) -> _ResolvedProject:
    """Resolve DevTools project in supported precedence order."""
    if explicit_project:
        return _ResolvedProject(explicit_project, "--devtools-project")

    env_project = os.getenv("GRAPHBASE_PROJECT")
    if env_project:
        return _ResolvedProject(env_project, "GRAPHBASE_PROJECT")

    active_project = _read_active_context_project()
    if active_project:
        return _ResolvedProject(active_project, "active-context")

    return _ResolvedProject(None, None)


def _devtools_sidecar_config(args: argparse.Namespace) -> _DevtoolsSidecarConfig | None:
    resolved = _resolve_devtools_project(getattr(args, "devtools_project", None))
    if not resolved.project or not resolved.source:
        return None

    return _DevtoolsSidecarConfig(
        project=resolved.project,
        source=resolved.source,
        host=getattr(args, "devtools_host", "127.0.0.1"),
        port=getattr(args, "devtools_port", 3001),
        open_browser=getattr(args, "open_browser", False),
    )


def _start_devtools_sidecar(args: argparse.Namespace) -> threading.Thread | None:
    """Best-effort DevTools sidecar startup that never blocks MCP launch."""
    from graphbase_memories.devtools import run

    config = _devtools_sidecar_config(args)
    if not config:
        print(
            "[graphbase server] DevTools disabled: no project resolved "
            "(use --devtools-project or GRAPHBASE_PROJECT).",
            file=sys.stderr,
            flush=True,
        )
        return None

    def _runner() -> None:
        try:
            run(
                project=config.project,
                host=config.host,
                port=config.port,
                open_browser=config.open_browser,
                log_stream=sys.stderr,
            )
        except FileNotFoundError as exc:
            print(f"[graphbase server] DevTools startup failed: {exc}", file=sys.stderr, flush=True)
        except OSError as exc:
            print(f"[graphbase server] DevTools startup failed: {exc}", file=sys.stderr, flush=True)

    print(
        f"[graphbase server] Starting DevTools sidecar for project={config.project!r} "
        f"via {config.source} on {config.host}:{config.port}",
        file=sys.stderr,
        flush=True,
    )
    thread = threading.Thread(target=_runner, name="graphbase-devtools", daemon=True)
    thread.start()
    return thread


def cmd_server(args: argparse.Namespace) -> None:
    """Run the MCP stdio server (default transport: stdio)."""
    from graphbase_memories.server import mcp

    if getattr(args, "open_browser", False) and not getattr(args, "devtools", False):
        print(
            "[graphbase server] ERROR: --open-browser requires --devtools",
            file=sys.stderr,
        )
        sys.exit(2)

    transport = getattr(args, "transport", "stdio")
    if getattr(args, "devtools", False):
        _start_devtools_sidecar(args)
    if transport == "sse":
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8765)
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")


def cmd_inject(args: argparse.Namespace) -> None:
    """
    Output context YAML to stdout for hook injection. [B2 fix]

    Called by session-start.sh:
        timeout 3 python -m graphbase_memories inject --project <slug>

    Exits 0 with empty output if no memories exist yet (graceful degradation).
    Never raises an unhandled exception — hooks must not be blocked.

    Note: SQLiteEngine is instantiated directly (not via _provider.get_engine)
    to avoid importing the full MCP server stack. This subcommand is a fast,
    hook-safe path — it always uses SQLite regardless of GRAPHBASE_BACKEND.
    """
    try:
        from graphbase_memories.config import Config
        from graphbase_memories.graph.sqlite_engine import SQLiteEngine
        from graphbase_memories.formatters.yaml_context import render_context

        config = Config()
        engine = SQLiteEngine(config, project=args.project)

        entity: str | None = args.entity
        if entity:
            memories = engine.get_memories_for_entity(entity, args.project)
            entities = engine.get_related_entities(args.project, entity)
        else:
            memories = engine.list_memories(args.project, limit=50)
            entities = []

        stale = engine.get_stale_memories(args.project, age_days=30)
        ctx = render_context(memories, entities, stale, entity, args.max_tokens)
        print(ctx, end="")   # no trailing newline — hook safety
    except Exception as exc:  # noqa: BLE001
        # Hooks must not crash session startup — degrade silently to stderr
        print(f"[graphbase-memories] inject warning: {exc}", file=sys.stderr)
        sys.exit(0)


def cmd_inspect(args: argparse.Namespace) -> None:
    """
    List memories in a project (developer inspection).

    Note: SQLiteEngine is instantiated directly for the same reason as cmd_inject —
    fast, hook-friendly, no full server import. Always uses SQLite.
    """
    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine

    config = Config()
    engine = SQLiteEngine(config, project=args.project)
    memories = engine.list_memories(args.project, limit=args.limit)

    if not memories:
        print(f"[graphbase-memories] No memories found for project={args.project!r}")
        return

    for m in memories:
        expired_flag = " [EXPIRED]" if m.is_expired else ""
        tags = f"  tags={m.tags}" if m.tags else ""
        print(f"[{m.type:12}] {m.title}  ({m.id[:8]}…){expired_flag}{tags}")


def cmd_doctor(args: argparse.Namespace) -> None:
    """
    Health check: Python version, fastmcp, data dir, WAL mode, schema, FTS5.

    Prints a table of checks — each line is OK/WARN/FAIL. Exit code is 1 if any
    check fails, 0 otherwise.
    """
    import importlib.metadata
    import os

    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine

    SCHEMA_VERSION = 2  # keep in sync with sqlite_engine.py SCHEMA_VERSION

    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "", warn: bool = False) -> None:
        if ok:
            status = "OK  "
        elif warn:
            status = "WARN"
        else:
            status = "FAIL"
            failures.append(label)
        suffix = f"  ({detail})" if detail else ""
        print(f"  [{status}] {label}{suffix}")

    print("graphbase-memories doctor")
    print("─" * 44)

    # Python version
    vi = sys.version_info
    check(
        "Python >= 3.11",
        vi >= (3, 11),
        f"{vi.major}.{vi.minor}.{vi.micro}",
    )

    # fastmcp installed
    try:
        fm_version = importlib.metadata.version("fastmcp")
        check("fastmcp installed", True, fm_version)
    except importlib.metadata.PackageNotFoundError:
        check("fastmcp installed", False, "not found")

    # data dir writable
    config = Config()
    data_dir = config.data_dir
    dir_exists = data_dir.exists()
    dir_writable = dir_exists and os.access(data_dir, os.W_OK)
    if not dir_exists:
        check("data dir writable", False, f"{data_dir} does not exist", warn=True)
    else:
        check("data dir writable", dir_writable, str(data_dir))

    # per-project checks (if --project given)
    project = getattr(args, "project", None)
    if project:
        engine = SQLiteEngine(config, project=project)

        # WAL mode
        jm = engine.journal_mode()
        check("SQLite WAL mode", jm == "wal", jm)

        # Schema version
        sv = engine.schema_version()
        check(
            "Schema version",
            sv == SCHEMA_VERSION,
            f"got {sv}, expected {SCHEMA_VERSION}",
        )

        # FTS5 available (attempt a harmless MATCH query)
        try:
            engine._con.execute(
                "SELECT rowid FROM memories_fts WHERE memories_fts MATCH 'healthcheck' LIMIT 1"
            )
            check("FTS5 present", True)
        except Exception as exc:  # noqa: BLE001
            check("FTS5 present", False, str(exc))

        # Memory / entity counts
        mem_count = engine._con.execute(
            "SELECT COUNT(*) FROM memories WHERE is_deleted=0"
        ).fetchone()[0]
        ent_count = engine._con.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        print(f"\n  Project '{project}': {mem_count} memories, {ent_count} entities")
    else:
        # Cross-project overview
        from graphbase_memories._provider import get_all_known_projects

        projects = get_all_known_projects()
        if projects:
            print(f"\n  Known projects ({len(projects)}):")
            for proj in projects:
                eng = SQLiteEngine(config, project=proj)
                cnt = eng._con.execute(
                    "SELECT COUNT(*) FROM memories WHERE is_deleted=0"
                ).fetchone()[0]
                print(f"    {proj}: {cnt} memories")
        else:
            print("\n  No projects found in data dir.")

    # Hook script detection
    import pathlib
    hook_paths = [
        pathlib.Path.home() / ".claude" / "hooks" / "graphbase-memories-hook.sh",
        pathlib.Path.home() / ".claude" / "hooks" / "session-start.sh",
    ]
    hook_found = any(p.exists() for p in hook_paths)
    check("Hook script found", hook_found, warn=not hook_found)

    print("─" * 44)
    if failures:
        print(f"  {len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    else:
        print("  All checks passed.")


def cmd_export(args: argparse.Namespace) -> None:
    """
    Export all memories, entities, and edges for a project to JSON.

    Full fidelity: soft-deleted memories are included (per OQ-3 decision).
    Default output is stdout — pipe-friendly.
    """
    import json
    from datetime import datetime, timezone

    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine
    import importlib.metadata

    config = Config()
    engine = SQLiteEngine(config, project=args.project)

    # Fetch all memories (including soft-deleted per OQ-3)
    memories = engine.list_memories(args.project, limit=100_000, include_deleted=True)

    # Fetch entities by iterating memory links
    seen_entity_ids: set[str] = set()
    entities_data: list[dict] = []
    edges_data: list[dict] = []

    for m in memories:
        for e in engine.get_entities_for_memory(m.id):
            if e.id not in seen_entity_ids:
                seen_entity_ids.add(e.id)
                entities_data.append({
                    "id": e.id,
                    "name": e.name,
                    "type": e.type,
                    "project": e.project,
                    "metadata": e.metadata,
                    "created_at": e.created_at,
                    "updated_at": e.updated_at,
                })
        for edge in engine.get_edges_for_memory(m.id):
            edges_data.append({
                "id": edge.id,
                "from_id": edge.from_id,
                "from_type": edge.from_type,
                "to_id": edge.to_id,
                "to_type": edge.to_type,
                "type": edge.type,
                "properties": edge.properties,
                "created_at": edge.created_at,
            })

    try:
        version = importlib.metadata.version("graphbase-memories-mcp")
    except importlib.metadata.PackageNotFoundError:
        version = "dev"

    payload = {
        "format_version": "1.0",
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "generator": f"graphbase-memories-mcp {version}",
        "projects": {
            args.project: {
                "memories": [
                    {
                        "id": m.id,
                        "project": m.project,
                        "type": m.type,
                        "title": m.title,
                        "content": m.content,
                        "tags": m.tags,
                        "created_at": m.created_at,
                        "updated_at": m.updated_at,
                        "valid_until": m.valid_until,
                        "is_deleted": m.is_deleted,
                        "is_expired": m.is_expired,
                    }
                    for m in memories
                ],
                "entities": entities_data,
                "edges": edges_data,
            }
        },
    }

    output_path = getattr(args, "output", "-")
    if output_path == "-":
        print(json.dumps(payload, indent=2))
    else:
        import pathlib
        pathlib.Path(output_path).write_text(json.dumps(payload, indent=2))
        print(f"Exported to {output_path}", file=sys.stderr)


def cmd_import_(args: argparse.Namespace) -> None:
    """
    Import a JSON export file into a project.

    --merge:   skip memories/entities whose IDs already exist (safe, idempotent)
    --replace: wipe all project data first, then import (prompts for confirmation)
    """
    import json
    import pathlib

    from graphbase_memories.config import Config
    from graphbase_memories.graph.sqlite_engine import SQLiteEngine
    from graphbase_memories.graph.engine import MemoryNode

    data = json.loads(pathlib.Path(args.file).read_text())

    if data.get("format_version") != "1.0":
        print(
            f"[import] Unsupported format_version: {data.get('format_version')!r}. "
            "Expected '1.0'.",
            file=sys.stderr,
        )
        sys.exit(1)

    config = Config()
    projects_data = data.get("projects", {})

    for project, proj_data in projects_data.items():
        engine = SQLiteEngine(config, project=project)

        if args.replace:
            confirm = input(
                f"Type '{project}' to confirm replacing ALL data for this project: "
            ).strip()
            if confirm != project:
                print("[import] Aborted — confirmation did not match.", file=sys.stderr)
                sys.exit(1)
            # Soft-delete all memories, hard-delete entities and edges
            existing = engine.list_memories(project, limit=100_000, include_deleted=True)
            for m in existing:
                if not m.is_deleted:
                    engine.soft_delete(m.id)
            engine._con.execute(
                "DELETE FROM relationships WHERE from_type='entity' OR to_type='entity'"
            )
            engine._con.execute("DELETE FROM entities WHERE project=?", (project,))
            engine._con.commit()

        memories_raw = proj_data.get("memories", [])
        entities_raw = proj_data.get("entities", [])
        edges_raw = proj_data.get("edges", [])

        imported_mem = skipped_mem = 0
        imported_ent = skipped_ent = 0
        imported_edge = skipped_edge = 0

        # Import memories
        for mem in memories_raw:
            existing = engine.get_memory(mem["id"], include_deleted=True)
            if existing is not None and args.merge:
                skipped_mem += 1
                continue
            node = MemoryNode(
                id=mem["id"],
                project=mem["project"],
                type=mem["type"],
                title=mem["title"],
                content=mem["content"],
                tags=mem.get("tags", []),
                created_at=mem["created_at"],
                updated_at=mem["updated_at"],
                valid_until=mem.get("valid_until"),
                is_deleted=mem.get("is_deleted", False),
                is_expired=mem.get("is_expired", False),
            )
            engine._con.execute(
                """INSERT OR REPLACE INTO memories
                   (id, project, type, title, content, tags, created_at,
                    updated_at, valid_until, is_deleted, is_expired)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    node.id, node.project, node.type, node.title, node.content,
                    json.dumps(node.tags), node.created_at, node.updated_at,
                    node.valid_until, int(node.is_deleted), int(node.is_expired),
                ),
            )
            imported_mem += 1

        # Import entities
        for ent in entities_raw:
            row = engine._con.execute(
                "SELECT id FROM entities WHERE id=?", (ent["id"],)
            ).fetchone()
            if row is not None and args.merge:
                skipped_ent += 1
                continue
            engine._con.execute(
                """INSERT OR REPLACE INTO entities
                   (id, name, type, project, metadata, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    ent["id"], ent["name"], ent["type"], ent["project"],
                    json.dumps(ent.get("metadata", {})),
                    ent["created_at"], ent.get("updated_at"),
                ),
            )
            imported_ent += 1

        # Import edges
        for edge in edges_raw:
            row = engine._con.execute(
                "SELECT id FROM relationships WHERE id=?", (edge["id"],)
            ).fetchone()
            if row is not None and args.merge:
                skipped_edge += 1
                continue
            engine._con.execute(
                """INSERT OR REPLACE INTO relationships
                   (id, from_id, from_type, to_id, to_type, type, properties, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    edge["id"], edge["from_id"], edge["from_type"],
                    edge["to_id"], edge["to_type"], edge["type"],
                    json.dumps(edge.get("properties", {})), edge["created_at"],
                ),
            )
            imported_edge += 1

        engine._con.commit()

        # Rebuild FTS index for imported memories
        engine._con.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
        engine._con.commit()

        print(
            f"Project '{project}': "
            f"memories {imported_mem} imported / {skipped_mem} skipped, "
            f"entities {imported_ent} / {skipped_ent}, "
            f"edges {imported_edge} / {skipped_edge}"
        )


def cmd_setup(args: argparse.Namespace) -> None:
    """
    Patch .mcp.json in --project-dir and write a Claude Code hook script.

    Actions:
      1. Detect Python executable
      2. Patch or create .mcp.json (only the graphbase-memories key)
      3. Write graphbase-memories-hook.sh to ~/.claude/hooks/
      4. Create GRAPHBASE_DATA_DIR if missing

    --dry-run prints what would be done without making changes.
    """
    import json
    import os
    import pathlib
    import shutil
    import stat

    dry_run: bool = args.dry_run
    project_dir = pathlib.Path(args.project_dir).resolve()
    hook_dir = pathlib.Path(
        getattr(args, "hook_dir", None) or (pathlib.Path.home() / ".claude" / "hooks")
    ).resolve()

    python_exe = getattr(args, "python", None) or shutil.which("python3") or sys.executable

    def act(description: str, fn) -> None:
        if dry_run:
            print(f"  [DRY-RUN] {description}")
        else:
            fn()
            print(f"  [DONE]    {description}")

    print("graphbase-memories setup")
    print("─" * 44)
    print(f"  Python      : {python_exe}")
    print(f"  Project dir : {project_dir}")
    print(f"  Hook dir    : {hook_dir}")
    print()

    # 1. Patch .mcp.json
    mcp_json_path = project_dir / ".mcp.json"
    if mcp_json_path.exists():
        mcp_config = json.loads(mcp_json_path.read_text())
    else:
        mcp_config = {"mcpServers": {}}

    mcp_config.setdefault("mcpServers", {})
    mcp_config["mcpServers"]["graphbase-memories"] = {
        "type": "stdio",
        "command": python_exe,
        "args": ["-m", "graphbase_memories", "server"],
    }

    def write_mcp_json():
        mcp_json_path.write_text(json.dumps(mcp_config, indent=2) + "\n")

    act(f"Patch {mcp_json_path}", write_mcp_json)

    # 2. Write hook script
    hook_script_path = hook_dir / "graphbase-memories-hook.sh"
    hook_content = f"""#!/usr/bin/env bash
# graphbase-memories context injection hook
# Auto-generated by: graphbase-memories setup
# Injects a token-budgeted YAML context block at session start.
#
# Requires GRAPHBASE_PROJECT to be set (e.g. in Claude Code settings.json env block).
set -euo pipefail

PROJECT="${{GRAPHBASE_PROJECT:-}}"
if [ -z "$PROJECT" ]; then
  exit 0
fi

timeout 3 {python_exe} -m graphbase_memories inject --project "$PROJECT" || true
"""

    def write_hook():
        hook_dir.mkdir(parents=True, exist_ok=True)
        hook_script_path.write_text(hook_content)
        hook_script_path.chmod(hook_script_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    act(f"Write {hook_script_path}", write_hook)

    # 3. Create GRAPHBASE_DATA_DIR if missing
    from graphbase_memories.config import Config
    config = Config()
    data_dir = config.data_dir

    def create_data_dir():
        data_dir.mkdir(parents=True, exist_ok=True)

    if not data_dir.exists():
        act(f"Create data dir {data_dir}", create_data_dir)
    else:
        print(f"  [OK]      Data dir already exists: {data_dir}")

    print()
    print("  Setup complete.")
    if not dry_run:
        print(
            "\n  Next steps:\n"
            "  1. Set GRAPHBASE_PROJECT=<your-slug> in Claude Code settings.json env block\n"
            "  2. Register the hook in Claude Code settings.json:\n"
            f'     "hooks": {{"PreToolUse": [], "UserPromptSubmit": ["{hook_script_path}"]}}'
        )


def cmd_devtools(args: argparse.Namespace) -> None:
    """
    Launch the standalone HTTP DevTools UI for inspecting graphbase-memories.

    Serves a graph UI at http://localhost:<port>/graph/.

    Routes:
      GET /graph/*        → static UI files (from --static-dir or bundled static/)
      GET /api/memories   → live memories export (entries[] format, compatible with CTL UI)
      GET /api/graphbase  → live graph snapshot (nodes/links for the Episodic tab)
      GET /api/status     → project memory/entity counts

    The --static-dir flag lets you point at any directory containing index.html
    (e.g. claude/ctl/graph/ from the claude-code-agent-workflow project).
    If omitted, the bundled static/ directory in this package is used.
    """
    import pathlib
    from graphbase_memories.devtools import run

    static_dir = pathlib.Path(args.static_dir).resolve() if args.static_dir else None
    data_dir   = getattr(args, 'data_dir', None)

    try:
        run(
            project    = args.project,
            host       = args.host,
            port       = args.port,
            static_dir = static_dir,
            data_dir   = data_dir,
            open_browser = args.open_browser,
        )
    except FileNotFoundError as exc:
        print(f'[devtools] ERROR: {exc}', file=sys.stderr)
        sys.exit(1)


def server_main() -> None:
    """
    Entry point for `uvx graphbase-memories-mcp` (no subcommand needed).

    Equivalent to: python -m graphbase_memories server
    Invoked via:   uvx --from <path> graphbase-memories-mcp

    The `graphbase-memories-mcp` script name matches the MCP server name in
    Claude Code settings.json, making the registration intent unambiguous.
    """
    from graphbase_memories.server import mcp
    mcp.run(transport="stdio")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="graphbase-memories",
        description="Graph-backed coding agent memory MCP server",
    )
    sub = parser.add_subparsers(dest="command")

    # --- server subcommand ---
    p_server = sub.add_parser("server", help="Run MCP server (default: stdio transport)")
    p_server.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="Transport protocol (default: stdio)",
    )
    p_server.add_argument("--host", default="127.0.0.1", help="SSE bind host (default: 127.0.0.1)")
    p_server.add_argument("--port", type=int, default=8765, help="SSE port (default: 8765)")
    p_server.add_argument(
        "--devtools", action="store_true",
        help="Start the DevTools sidecar alongside the MCP server",
    )
    p_server.add_argument(
        "--devtools-project", default=None, dest="devtools_project",
        help="Project slug for the DevTools sidecar (default: resolve from env or active-context)",
    )
    p_server.add_argument(
        "--devtools-host", default="127.0.0.1", dest="devtools_host",
        help="DevTools bind host (default: 127.0.0.1)",
    )
    p_server.add_argument(
        "--devtools-port", type=int, default=3001, dest="devtools_port",
        help="DevTools port (default: 3001)",
    )
    p_server.add_argument(
        "--open-browser", action="store_true", dest="open_browser",
        help="Open the DevTools UI in a browser when DevTools is enabled",
    )

    # --- inject subcommand (used by Claude Code hooks) ---
    p_inject = sub.add_parser("inject", help="Output context YAML to stdout")
    p_inject.add_argument("--project", required=True, help="Project slug")
    p_inject.add_argument("--entity", default=None, help="Focus entity name")
    p_inject.add_argument("--max-tokens", type=int, default=500, dest="max_tokens")

    # --- inspect subcommand (developer use) ---
    p_inspect = sub.add_parser("inspect", help="List memories in a project")
    p_inspect.add_argument("--project", required=True, help="Project slug")
    p_inspect.add_argument("--limit", type=int, default=20)

    # --- doctor subcommand ---
    p_doctor = sub.add_parser("doctor", help="Health check: Python, fastmcp, data dir, WAL, schema")
    p_doctor.add_argument("--project", default=None, help="Project slug for per-project checks")

    # --- export subcommand ---
    p_export = sub.add_parser("export", help="Export project memories to JSON")
    p_export.add_argument("--project", required=True, help="Project slug")
    p_export.add_argument(
        "--output", default="-", metavar="FILE",
        help="Output file path (default: - for stdout)",
    )

    # --- import subcommand ---
    p_import = sub.add_parser("import", help="Import a JSON export file")
    p_import.add_argument("--file", required=True, help="Path to export JSON file")
    merge_group = p_import.add_mutually_exclusive_group()
    merge_group.add_argument(
        "--merge", action="store_true", default=True,
        help="Skip existing IDs (safe, idempotent — default)",
    )
    merge_group.add_argument(
        "--replace", action="store_true", default=False,
        help="Wipe project data before import (prompts for confirmation)",
    )

    # --- setup subcommand ---
    p_setup = sub.add_parser("setup", help="Patch .mcp.json and write hook script")
    p_setup.add_argument(
        "--project-dir", default=".", dest="project_dir",
        help="Directory where .mcp.json lives (default: current dir)",
    )
    p_setup.add_argument(
        "--hook-dir", default=None, dest="hook_dir",
        help="Directory for hook script (default: ~/.claude/hooks/)",
    )
    p_setup.add_argument(
        "--python", default=None,
        help="Python executable path (default: auto-detected)",
    )
    p_setup.add_argument(
        "--dry-run", action="store_true", dest="dry_run",
        help="Print actions without making changes",
    )

    # --- devtools subcommand ---
    p_devtools = sub.add_parser(
        "devtools",
        help="Launch standalone HTTP DevTools UI for inspecting memories",
    )
    p_devtools.add_argument("--project", required=True, help="Project slug to inspect")
    p_devtools.add_argument(
        "--host", default="127.0.0.1",
        help="HTTP bind host (default: 127.0.0.1)",
    )
    p_devtools.add_argument(
        "--port", type=int, default=3001,
        help="HTTP port (default: 3001)",
    )
    p_devtools.add_argument(
        "--static-dir", default=None, dest="static_dir",
        metavar="PATH",
        help="Path to directory with index.html (default: bundled static/)",
    )
    p_devtools.add_argument(
        "--data-dir", default=None, dest="data_dir",
        metavar="PATH",
        help="Override GRAPHBASE_DATA_DIR (default: ~/.graphbase)",
    )
    p_devtools.add_argument(
        "--open-browser", action="store_true", dest="open_browser",
        help="Open the DevTools UI in a browser after the server starts",
    )

    args = parser.parse_args()

    dispatch = {
        None:       cmd_server,
        "server":   cmd_server,
        "inject":   cmd_inject,
        "inspect":  cmd_inspect,
        "doctor":   cmd_doctor,
        "export":   cmd_export,
        "import":   cmd_import_,
        "setup":    cmd_setup,
        "devtools": cmd_devtools,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
