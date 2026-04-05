"""
graphbase_memories.devtools — Standalone HTTP DevTools server.

Serves a graph UI for inspecting graphbase-memories projects.

Routes:
  GET  /                     → redirect to /graph/
  GET  /graph/               → index.html from static_dir
  GET  /graph/<file>         → static file from static_dir
  GET  /api/memories         → live memories export (entries[] format)
  GET  /api/graphbase        → live graph snapshot (nodes/links format)
  GET  /api/status           → project summary

Usage (CLI):
  python -m graphbase_memories devtools --project <slug> [--port 3001] [--static-dir <path>]
"""

from __future__ import annotations

import json
import os
import pathlib
import queue
import re
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer, ThreadingMixIn
from typing import Any, Optional, TextIO, cast

# ── ANSI stripping ────────────────────────────────────────────────────────────

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mKHABCDEFGJSTsulhn]')

def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub('', s)


# ── MIME types ─────────────────────────────────────────────────────────────────

_MIME = {
    '.html': 'text/html; charset=utf-8',
    '.css':  'text/css; charset=utf-8',
    '.js':   'application/javascript; charset=utf-8',
    '.json': 'application/json',
    '.svg':  'image/svg+xml',
    '.ico':  'image/x-icon',
    '.png':  'image/png',
}

def _mime_for(path: pathlib.Path) -> str:
    return _MIME.get(path.suffix.lower(), 'application/octet-stream')


@dataclass
class _GraphAccess:
    """
    Read adapter for DevTools endpoints.

    Default path uses the shared provider so the inspector follows the active
    backend selection. When a DevTools-specific data-dir override is supplied,
    we instantiate that backend class directly because the provider singleton
    has no per-call config override yet.
    """

    data_dir: Optional[str] = None

    def _engine(self, project: str):
        if self.data_dir is None:
            from graphbase_memories._provider import get_engine

            return get_engine(project)

        from graphbase_memories._provider import _load_backend_class
        from graphbase_memories.config import Config

        config = Config(data_dir=pathlib.Path(self.data_dir).expanduser())
        backend_cls = _load_backend_class(config.backend)
        return backend_cls(config, project)

    def memories_payload(self, project: str) -> dict[str, Any]:
        import datetime

        engine = self._engine(project)
        memories = engine.list_memories(project, limit=500)

        entries = []
        for m in memories:
            slug = re.sub(r'[^a-z0-9]+', '-', m.title.lower()).strip('-')
            key = f"{m.type}/{slug}"
            entries.append({
                'key':         key,
                'id':          m.id,
                'type':        m.type,
                'title':       m.title,
                'tags':        m.tags,
                'modified_at': m.updated_at,
                'size_bytes':  len(m.content.encode('utf-8')),
                'content':     m.content,
            })

        return {
            'generated': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'project':   project,
            'entries':   entries,
        }

    def graph_payload(self, project: str) -> tuple[int, dict[str, Any]]:
        from graphbase_memories.graph.sqlite_engine import SCHEMA_VERSION

        engine = self._engine(project)
        db_version = engine.schema_version()
        if db_version != SCHEMA_VERSION:
            return 409, {
                'error': (
                    f'Schema version mismatch: DB={db_version}, code={SCHEMA_VERSION}. '
                    'Upgrade graphbase-memories-mcp or point GRAPHBASE_DATA_DIR at a fresh directory.'
                )
            }

        data = engine.get_graph_data(project, limit=200)

        nodes = []
        for m in data.memories:
            nodes.append({
                'id':         m.id,
                'label':      m.title,
                'node_type':  'memory',
                'type':       m.type,
                'tags':       m.tags,
                'updated_at': m.updated_at,
                'is_expired': m.is_expired,
            })

        seen: set[str] = set()
        for e in data.entities:
            if e.id in seen:
                continue
            seen.add(e.id)
            nodes.append({
                'id':        e.id,
                'label':     e.name,
                'node_type': 'entity',
                'type':      e.type,
            })

        all_ids = {n['id'] for n in nodes}
        links = [
            {'source': edge.from_id, 'target': edge.to_id, 'type': edge.type}
            for edge in data.edges
            if edge.from_id in all_ids and edge.to_id in all_ids
        ]

        return 200, {
            'project':        project,
            'total_memories': data.total_memories,
            'generated_at':   data.generated_at,
            'nodes':          nodes,
            'links':          links,
        }

    def status_payload(self, project: str) -> dict[str, Any]:
        engine = self._engine(project)
        latest = engine.list_memories(project, limit=1)
        entities = engine.get_related_entities(project)
        graph_data = engine.get_graph_data(project, limit=1)

        return {
            'project':       project,
            'memories':      graph_data.total_memories,
            'entities':      len(entities),
            'latest_title':  latest[0].title if latest else None,
            'latest_at':     latest[0].updated_at if latest else None,
        }


@dataclass(frozen=True)
class _DevtoolsConfig:
    project: str
    static_dir: pathlib.Path
    graph_access: _GraphAccess


class _DevtoolsServerProtocol:
    app: _DevtoolsConfig


def _resolve_static_dir(static_dir: Optional[pathlib.Path]) -> pathlib.Path:
    if static_dir is not None:
        resolved = pathlib.Path(static_dir).resolve()
    else:
        pkg_static = pathlib.Path(__file__).parent / 'static'
        if not pkg_static.is_dir():
            raise FileNotFoundError(
                f'No static directory found at {pkg_static}. '
                'Pass --static-dir <path> to point at a graph UI directory.'
            )
        resolved = pkg_static

    if not (resolved / 'index.html').exists():
        raise FileNotFoundError(
            f'index.html not found in static dir: {resolved}. '
            'Pass --static-dir <path> pointing to a directory containing index.html.'
        )
    return resolved


def _browser_url(host: str, port: int) -> str:
    browser_host = host if host not in {'', '0.0.0.0'} else '127.0.0.1'
    return f'http://{browser_host}:{port}/graph/'


def _open_browser(url: str, stderr: TextIO | None = None) -> bool:
    stream = stderr if stderr is not None else sys.stderr
    try:
        return bool(webbrowser.open_new_tab(url))
    except Exception as exc:  # noqa: BLE001
        print(f'[graphbase devtools] browser open failed: {exc}', file=stream, flush=True)
        return False


# ── HTTP handler ──────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):

    @property
    def _app(self) -> _DevtoolsConfig:
        return cast(_DevtoolsServerProtocol, self.server).app

    def log_message(self, fmt, *args):
        pass  # suppress per-request stdout noise

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split('?')[0]

        if path in ('/', ''):
            self._redirect('/graph/')
        elif path in ('/graph', '/graph/'):
            self._serve_static(self._app.static_dir / 'index.html')
        elif path.startswith('/graph/'):
            rel = path[len('/graph/'):]
            self._serve_static(self._app.static_dir / rel)
        elif path == '/api/memories':
            self._handle_api_memories()
        elif path == '/api/graphbase':
            project_slug = _parse_project_qs(self.path)
            self._handle_api_graphbase(project_slug)
        elif path == '/api/status':
            self._handle_api_status()
        else:
            self.send_error(404, 'Not found')

    # ── Static serving ────────────────────────────────────────────────────────

    def _redirect(self, location: str):
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()

    def _serve_static(self, path: pathlib.Path):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, f'Not found: {path.name}')
            return
        except OSError as exc:
            self.send_error(500, str(exc))
            return
        self.send_response(200)
        self.send_header('Content-Type', _mime_for(path))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def _json_response(self, code: int, obj):
        body = json.dumps(obj).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json_error(self, code: int, message: str):
        self._json_response(code, {'error': message})

    # ── /api/memories ─────────────────────────────────────────────────────────

    def _handle_api_memories(self):
        """Live graphbase-memories export in CTL entries[] format."""
        project = _parse_project_qs(self.path) or self._app.project

        try:
            self._json_response(200, self._app.graph_access.memories_payload(project))
        except Exception as exc:
            self._json_error(500, str(exc))

    # ── /api/graphbase ────────────────────────────────────────────────────────

    def _handle_api_graphbase(self, project: str):
        """Live graph snapshot — nodes/links format for the Episodic tab."""
        project = project or self._app.project

        try:
            status, payload = self._app.graph_access.graph_payload(project)
            self._json_response(status, payload)
        except Exception as exc:
            self._json_error(500, str(exc))

    # ── /api/status ───────────────────────────────────────────────────────────

    def _handle_api_status(self):
        """Project summary: memory count, entity count, latest memory."""
        project = _parse_project_qs(self.path) or self._app.project

        try:
            self._json_response(200, self._app.graph_access.status_payload(project))
        except Exception as exc:
            self._json_error(500, str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_project_qs(raw_path: str) -> str:
    """Extract ?project=<slug> from a raw request path, or return ''."""
    if '?' not in raw_path:
        return ''
    qs = raw_path.split('?', 1)[1]
    for pair in qs.split('&'):
        if pair.startswith('project='):
            return pair[len('project='):]
    return ''


# ── Threaded server ───────────────────────────────────────────────────────────

class _ThreadedServer(ThreadingMixIn, TCPServer):
    allow_reuse_address = True
    daemon_threads = True


# ── Public entry point ────────────────────────────────────────────────────────

def build_server(
    project: str,
    host: str = '127.0.0.1',
    port: int = 3001,
    static_dir: Optional[pathlib.Path] = None,
    data_dir: Optional[str] = None,
) -> _ThreadedServer:
    """Build a configured DevTools server without starting the serve loop."""
    server = _ThreadedServer((host, port), _Handler)
    server.app = _DevtoolsConfig(
        project=project,
        static_dir=_resolve_static_dir(static_dir),
        graph_access=_GraphAccess(data_dir),
    )
    return server


def run(
    project: str,
    host: str = '127.0.0.1',
    port: int = 3001,
    static_dir: Optional[pathlib.Path] = None,
    data_dir: Optional[str] = None,
    open_browser: bool = False,
    log_stream: TextIO | None = None,
) -> None:
    """Start the devtools HTTP server. Blocks until KeyboardInterrupt."""
    stream = log_stream if log_stream is not None else sys.stdout
    server = build_server(
        project=project,
        host=host,
        port=port,
        static_dir=static_dir,
        data_dir=data_dir,
    )
    bound_port = int(server.server_address[1])
    url = _browser_url(host, bound_port)
    print(
        f'[graphbase devtools] {url}'
        f'  project={project!r}  static={server.app.static_dir}',
        file=stream,
        flush=True,
    )
    if open_browser:
        _open_browser(url, stderr=stream)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[graphbase devtools] shutting down', file=stream, flush=True)
    finally:
        server.server_close()
