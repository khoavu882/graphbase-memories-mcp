from __future__ import annotations

import argparse
import io
import types

import pytest

import graphbase_memories.__main__ as mainmod


def test_resolve_devtools_project_prefers_explicit(monkeypatch):
    monkeypatch.setenv("GRAPHBASE_PROJECT", "env-project")
    monkeypatch.setattr(mainmod, "_read_active_context_project", lambda: "ctx-project")

    resolved = mainmod._resolve_devtools_project("explicit-project")

    assert resolved.project == "explicit-project"
    assert resolved.source == "--devtools-project"


def test_resolve_devtools_project_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("GRAPHBASE_PROJECT", "env-project")
    monkeypatch.setattr(mainmod, "_read_active_context_project", lambda: "ctx-project")

    resolved = mainmod._resolve_devtools_project(None)

    assert resolved.project == "env-project"
    assert resolved.source == "GRAPHBASE_PROJECT"


def test_resolve_devtools_project_falls_back_to_active_context(monkeypatch):
    monkeypatch.delenv("GRAPHBASE_PROJECT", raising=False)
    monkeypatch.setattr(mainmod, "_read_active_context_project", lambda: "ctx-project")

    resolved = mainmod._resolve_devtools_project(None)

    assert resolved.project == "ctx-project"
    assert resolved.source == "active-context"


def test_cmd_server_rejects_open_browser_without_devtools(monkeypatch, capsys):
    monkeypatch.setitem(
        __import__("sys").modules,
        "graphbase_memories.server",
        types.SimpleNamespace(mcp=types.SimpleNamespace(run=lambda **_: None)),
    )

    with pytest.raises(SystemExit) as exc:
        mainmod.cmd_server(
            argparse.Namespace(
                transport="stdio",
                devtools=False,
                open_browser=True,
            )
        )

    assert exc.value.code == 2
    assert "--open-browser requires --devtools" in capsys.readouterr().err


def test_start_devtools_sidecar_warns_when_project_unresolved(monkeypatch):
    stderr = io.StringIO()
    monkeypatch.setattr(mainmod, "_resolve_devtools_project", lambda _explicit: mainmod._ResolvedProject(None, None))
    monkeypatch.setattr(mainmod.sys, "stderr", stderr)

    thread = mainmod._start_devtools_sidecar(
        argparse.Namespace(
            devtools_project=None,
            devtools_host="127.0.0.1",
            devtools_port=3001,
            open_browser=False,
        )
    )

    assert thread is None
    assert "DevTools disabled: no project resolved" in stderr.getvalue()


def test_start_devtools_sidecar_starts_daemon_thread(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs):
        calls.append(kwargs)

    fake_devtools = types.SimpleNamespace(run=fake_run)
    monkeypatch.setitem(__import__("sys").modules, "graphbase_memories.devtools", fake_devtools)
    monkeypatch.setattr(
        mainmod,
        "_resolve_devtools_project",
        lambda _explicit: mainmod._ResolvedProject("resolved-project", "--devtools-project"),
    )

    class ImmediateThread:
        def __init__(self, *, target, name, daemon):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False

        def start(self):
            self.started = True
            self.target()

    monkeypatch.setattr(mainmod.threading, "Thread", ImmediateThread)

    thread = mainmod._start_devtools_sidecar(
        argparse.Namespace(
            devtools_project="resolved-project",
            devtools_host="127.0.0.1",
            devtools_port=3555,
            open_browser=True,
        )
    )

    assert thread is not None
    assert thread.daemon is True
    assert calls == [
        {
            "project": "resolved-project",
            "host": "127.0.0.1",
            "port": 3555,
            "open_browser": True,
            "log_stream": mainmod.sys.stderr,
        }
    ]
