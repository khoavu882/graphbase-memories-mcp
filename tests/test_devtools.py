from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import io
import types
from uuid import uuid4

from graphbase_memories.devtools import (
    _GraphAccess,
    _browser_url,
    _open_browser,
    _resolve_static_dir,
    build_server,
    run,
)
from graphbase_memories.graph.engine import Edge, MemoryNode

PROJECT = "test"


def _memory(*, title: str, type: str = "decision", content: str = "content") -> MemoryNode:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return MemoryNode(
        id=str(uuid4()),
        project=PROJECT,
        type=type,
        title=title,
        content=content,
        tags=["tag"],
        created_at=now,
        updated_at=now,
        valid_until=None,
        is_deleted=False,
    )


def test_graph_access_memories_payload_uses_provider_engine(engine):
    engine.store_memory_with_entities(_memory(title="Decision One"), ["svc-a"])

    payload = _GraphAccess().memories_payload(PROJECT)

    assert payload["project"] == PROJECT
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["title"] == "Decision One"
    assert payload["entries"][0]["key"] == "decision/decision-one"


def test_graph_access_graph_payload_returns_nodes_and_links(engine):
    first = _memory(title="Decision One")
    second = _memory(title="Decision Two", type="pattern")
    engine.store_memory_with_entities(first, ["svc-a"])
    engine.store_memory_with_entities(second, ["svc-a"])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    engine.store_edge(
        Edge(
            id=str(uuid4()),
            from_id=first.id,
            from_type="memory",
            to_id=second.id,
            to_type="memory",
            type="RELATES_TO",
            properties={},
            created_at=now,
        )
    )

    status, payload = _GraphAccess().graph_payload(PROJECT)

    assert status == 200
    assert payload["project"] == PROJECT
    assert payload["total_memories"] == 2
    assert len([n for n in payload["nodes"] if n["node_type"] == "memory"]) == 2
    assert any(link["type"] == "RELATES_TO" for link in payload["links"])


def test_graph_access_status_payload_uses_engine_reads(engine):
    engine.store_memory_with_entities(_memory(title="Latest Decision"), ["svc-a", "svc-b"])

    payload = _GraphAccess().status_payload(PROJECT)

    assert payload["project"] == PROJECT
    assert payload["memories"] == 1
    assert payload["entities"] == 2
    assert payload["latest_title"] == "Latest Decision"
    assert payload["latest_at"] is not None


def test_resolve_static_dir_uses_bundled_assets():
    static_dir = _resolve_static_dir(None)

    assert static_dir.name == "static"
    assert (static_dir / "index.html").exists()


def test_build_server_keeps_instance_scoped_config():
    static_dir = Path("src/graphbase_memories/devtools/static").resolve()

    first = build_server("project-one", host="127.0.0.1", port=0, static_dir=static_dir)
    second = build_server("project-two", host="127.0.0.1", port=0, static_dir=static_dir)
    try:
        assert first.app.project == "project-one"
        assert second.app.project == "project-two"
        assert first.app.static_dir == static_dir
        assert second.app.static_dir == static_dir
        assert first.server_address[0] == "127.0.0.1"
        assert second.server_address[0] == "127.0.0.1"
    finally:
        first.server_close()
        second.server_close()


def test_browser_url_uses_loopback_for_wildcard_host():
    assert _browser_url("0.0.0.0", 3001) == "http://127.0.0.1:3001/graph/"
    assert _browser_url("", 3001) == "http://127.0.0.1:3001/graph/"
    assert _browser_url("127.0.0.1", 3001) == "http://127.0.0.1:3001/graph/"


def test_open_browser_failure_is_best_effort(monkeypatch):
    stderr = io.StringIO()

    def raising_open(_url: str):
        raise RuntimeError("no browser")

    monkeypatch.setattr("webbrowser.open_new_tab", raising_open)

    result = _open_browser("http://127.0.0.1:3001/graph/", stderr=stderr)

    assert result is False
    assert "browser open failed" in stderr.getvalue()


def test_run_uses_actual_bound_port_for_browser(monkeypatch):
    calls: list[str] = []
    stream = io.StringIO()
    static_dir = Path("src/graphbase_memories/devtools/static").resolve()

    class FakeServer:
        def __init__(self):
            self.app = types.SimpleNamespace(static_dir=static_dir)
            self.server_address = ("127.0.0.1", 45678)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            return None

    monkeypatch.setattr(
        "graphbase_memories.devtools.build_server",
        lambda **_kwargs: FakeServer(),
    )
    monkeypatch.setattr(
        "graphbase_memories.devtools._open_browser",
        lambda url, stderr=None: calls.append(url) or True,
    )

    run(project="proj", host="127.0.0.1", port=0, open_browser=True, log_stream=stream)

    assert calls == ["http://127.0.0.1:45678/graph/"]
    assert "http://127.0.0.1:45678/graph/" in stream.getvalue()
