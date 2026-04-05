"""
CLI entry point for graphbase-memories.

Subcommands:
    server   — Run MCP stdio server (default when no subcommand given)
    inject   — Output context YAML to stdout (called by Claude Code hooks)
    inspect  — List memories in a project (developer inspection)

Usage:
    python -m graphbase_memories              # MCP stdio server
    python -m graphbase_memories server       # MCP stdio server (explicit)
    python -m graphbase_memories inject --project <slug> [--entity <name>] [--max-tokens N]
    python -m graphbase_memories inspect --project <slug> [--limit N]

Environment variables (override via settings.json env block):
    GRAPHBASE_BACKEND    sqlite (default) | neo4j
    GRAPHBASE_DATA_DIR   ~/.graphbase-memories (default)
    GRAPHBASE_LOG_LEVEL  WARNING (default)

[B2 FIX] This dual-mode entry point allows hooks to call:
    python -m graphbase_memories inject --project X
without starting the full MCP stdio server.
"""

import argparse
import sys


def cmd_server(_args: argparse.Namespace) -> None:
    """Run the MCP stdio server."""
    from graphbase_memories.server import mcp
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
    sub.add_parser("server", help="Run MCP stdio server (default)")

    # --- inject subcommand (used by Claude Code hooks) ---
    p_inject = sub.add_parser("inject", help="Output context YAML to stdout")
    p_inject.add_argument("--project", required=True, help="Project slug")
    p_inject.add_argument("--entity", default=None, help="Focus entity name")
    p_inject.add_argument("--max-tokens", type=int, default=500, dest="max_tokens")

    # --- inspect subcommand (developer use) ---
    p_inspect = sub.add_parser("inspect", help="List memories in a project")
    p_inspect.add_argument("--project", required=True, help="Project slug")
    p_inspect.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    dispatch = {
        None:      cmd_server,
        "server":  cmd_server,
        "inject":  cmd_inject,
        "inspect": cmd_inspect,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
