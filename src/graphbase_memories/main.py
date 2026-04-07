"""
CLI entry point — typer app with three subcommands:
  serve    → start stdio MCP server (primary mode for agent use)
  devtools → start HTTP inspection server
  hygiene  → run hygiene cycle and print report
"""

from __future__ import annotations

import asyncio

import typer

app = typer.Typer(help="graphbase-memories-mcp — graph-backed MCP memory server")


@app.command("serve")
def serve() -> None:
    """Start the MCP stdio server. Used by AI agents via MCP protocol."""
    from graphbase_memories.mcp.server import mcp

    mcp.run(transport="stdio")


@app.command("devtools")
def devtools(
    port: int = typer.Option(8765, help="HTTP port for the devtools inspection server"),
    host: str = typer.Option("127.0.0.1", help="Bind host"),
) -> None:
    """Start the HTTP devtools server for human memory inspection."""
    import uvicorn

    uvicorn.run(
        "graphbase_memories.devtools.server:app",
        host=host,
        port=port,
        reload=False,
    )


@app.command("hygiene")
def hygiene(
    project_id: str | None = typer.Option(
        None, "--project-id", "-p", help="Project ID to check (omit for global)"
    ),
    scope: str = typer.Option("global", "--scope", "-s", help="Scope: global, project, focus"),
) -> None:
    """Run the memory hygiene cycle and print the HygieneReport as JSON."""
    from graphbase_memories.config import settings
    from graphbase_memories.engines.hygiene import run as run_hygiene

    async def _run() -> None:
        # Minimal lifespan usage for CLI
        from neo4j import AsyncGraphDatabase

        from graphbase_memories.graph.driver import SCHEMA_DDL, split_statements

        driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
            max_connection_pool_size=settings.neo4j_max_pool_size,
        )
        try:
            await driver.verify_connectivity()
            async with driver.session(database=settings.neo4j_database) as session:
                for stmt in split_statements(SCHEMA_DDL):
                    await session.run(stmt)
            report = await run_hygiene(project_id, scope, driver, settings.neo4j_database)
            typer.echo(report.model_dump_json(indent=2))
        finally:
            await driver.close()

    asyncio.run(_run())


if __name__ == "__main__":
    app()
