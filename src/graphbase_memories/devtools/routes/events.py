"""SSE heartbeat endpoint — real-time Neo4j connectivity status stream."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from neo4j import AsyncDriver

router = APIRouter(tags=["events"])

HEARTBEAT_INTERVAL = 5  # seconds


async def _heartbeat_generator(driver: AsyncDriver) -> AsyncIterator[str]:
    """Yield SSE-formatted heartbeat events every HEARTBEAT_INTERVAL seconds."""
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
            "tool_count": 20,  # updated to dynamic count in W-B
            "ts": datetime.now(UTC).isoformat(),
        }
        if error:
            payload["error"] = error

        yield f"event: heartbeat\ndata: {json.dumps(payload)}\n\n"
        await asyncio.sleep(HEARTBEAT_INTERVAL)


@router.get("/events")
async def sse_heartbeat():
    """Stream Neo4j heartbeat events via Server-Sent Events."""
    from graphbase_memories.devtools.server import _get_driver as _gd

    driver = _gd()
    return StreamingResponse(
        _heartbeat_generator(driver),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
