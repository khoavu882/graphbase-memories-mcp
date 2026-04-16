"""SSE heartbeat endpoint — real-time Neo4j connectivity status stream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from neo4j import AsyncDriver

from graphbase_memories.devtools.deps import DriverDep

router = APIRouter(tags=["events"])

HEARTBEAT_INTERVAL = 5  # seconds


async def _heartbeat_generator(driver: AsyncDriver) -> AsyncIterator[str]:
    """Yield SSE-formatted heartbeat events every HEARTBEAT_INTERVAL seconds."""
    from graphbase_memories.mcp.server import mcp

    tools = await mcp.list_tools()
    tool_count = len(tools)

    while True:
        try:
            await driver.verify_connectivity()
            connected = True
            error = None
        except Exception as exc:
            connected = False
            error = str(exc)

        payload: dict = {
            "status": "ok" if connected else "degraded",
            "neo4j_connected": connected,
            "tool_count": tool_count,
            "ts": datetime.now(UTC).isoformat(),
        }
        if error:
            payload["error"] = error

        yield f"event: heartbeat\ndata: {json.dumps(payload)}\n\n"
        await asyncio.sleep(HEARTBEAT_INTERVAL)


@router.get("/events")
async def sse_heartbeat(driver: DriverDep):
    """Stream Neo4j heartbeat events via Server-Sent Events."""
    return StreamingResponse(
        _heartbeat_generator(driver),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
