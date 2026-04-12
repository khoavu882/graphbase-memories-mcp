"""
Integration: devtools SSE heartbeat generator against live Neo4j.
Tests _heartbeat_generator directly without going through HTTP.
"""

from __future__ import annotations

import json

from conftest import TEST_DB  # noqa: F401 — confirms conftest is loaded


async def test_heartbeat_emits_event_string(driver):
    """A single heartbeat yields a properly formatted SSE string."""
    from graphbase_memories.devtools.routes.events import _heartbeat_generator

    gen = _heartbeat_generator(driver)
    chunk = await gen.__anext__()

    assert chunk.startswith("event: heartbeat\n")
    assert "data: " in chunk
    assert chunk.endswith("\n\n")


async def test_heartbeat_payload_structure(driver):
    """Heartbeat payload contains expected keys when Neo4j is connected."""
    from graphbase_memories.devtools.routes.events import _heartbeat_generator

    gen = _heartbeat_generator(driver)
    chunk = await gen.__anext__()

    data_line = next(ln for ln in chunk.splitlines() if ln.startswith("data: "))
    payload = json.loads(data_line[len("data: ") :])

    assert payload["neo4j_connected"] is True
    assert payload["status"] == "ok"
    assert isinstance(payload["tool_count"], int)
    assert "ts" in payload


async def test_heartbeat_multiple_yields(driver):
    """Generator yields at least two consecutive SSE events."""
    import types

    import graphbase_memories.devtools.routes.events as events_module
    from graphbase_memories.devtools.routes.events import _heartbeat_generator

    real_asyncio = events_module.asyncio

    async def instant_sleep(_):
        pass  # no-op — skip real 5s wait

    # Use SimpleNamespace so instant_sleep is a plain attr, not a bound method
    events_module.asyncio = types.SimpleNamespace(sleep=instant_sleep)

    try:
        gen = _heartbeat_generator(driver)
        chunk1 = await gen.__anext__()  # first yield (before any sleep)
        chunk2 = await gen.__anext__()  # sleep (instant) → second yield
        await gen.aclose()
    finally:
        events_module.asyncio = real_asyncio

    assert chunk1.startswith("event: heartbeat\n")
    assert chunk2.startswith("event: heartbeat\n")
