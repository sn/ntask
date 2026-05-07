from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote

import pytest

from ntask._remote.http import HTTPBackend


class _DictHandler(BaseHTTPRequestHandler):
    """HTTP handler backed by a server-level dict. Verbose silence."""

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # suppress default access log

    def do_HEAD(self):
        path = unquote(self.path)
        if path in self.server.store:  # type: ignore[attr-defined]
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        path = unquote(self.path)
        if path in self.server.store:  # type: ignore[attr-defined]
            data = self.server.store[path]  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        # Optional auth check
        expected = getattr(self.server, "expected_auth", None)  # type: ignore[attr-defined]
        if expected is not None:
            got = self.headers.get("Authorization")
            if got != expected:
                self.send_response(401)
                self.end_headers()
                return
        # Optional forced failure
        if getattr(self.server, "fail_puts", False):  # type: ignore[attr-defined]
            self.send_response(403)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        path = unquote(self.path)
        self.server.store[path] = data  # type: ignore[attr-defined]
        self.send_response(204)
        self.end_headers()


def _start_server():
    srv = HTTPServer(("127.0.0.1", 0), _DictHandler)
    srv.store = {}  # type: ignore[attr-defined]
    srv.expected_auth = None  # type: ignore[attr-defined]
    srv.fail_puts = False  # type: ignore[attr-defined]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, t


@pytest.fixture
def http_server():
    srv, _t = _start_server()
    try:
        yield srv
    finally:
        srv.shutdown()


def test_http_roundtrip_entry(http_server):
    host, port = http_server.server_address
    backend = HTTPBackend(base_url=f"http://{host}:{port}")

    assert backend.has_entry("build", "abc") is False
    assert backend.get_entry("build", "abc") is None

    backend.put_entry("build", "abc", {"v": 1})
    assert backend.has_entry("build", "abc") is True
    assert backend.get_entry("build", "abc") == {"v": 1}


def test_http_missing_entry_returns_none(http_server):
    host, port = http_server.server_address
    backend = HTTPBackend(base_url=f"http://{host}:{port}")
    assert backend.get_entry("foo", "bar") is None


def test_http_raises_on_non_200_put(http_server):
    http_server.fail_puts = True
    host, port = http_server.server_address
    backend = HTTPBackend(base_url=f"http://{host}:{port}")
    with pytest.raises(RuntimeError):
        backend.put_entry("build", "abc", {"v": 1})


def test_http_output_roundtrip(http_server, tmp_path: Path):
    host, port = http_server.server_address
    backend = HTTPBackend(base_url=f"http://{host}:{port}")

    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_bytes(b"hello")

    backend.put_output("h1", src)
    assert backend.has_output("h1") is True

    dest = tmp_path / "dest"
    backend.get_output("h1", dest)
    assert (dest / "f.txt").read_bytes() == b"hello"


def test_http_auth_header_attached(http_server):
    http_server.expected_auth = "Bearer SECRET"
    host, port = http_server.server_address
    backend = HTTPBackend(base_url=f"http://{host}:{port}", auth_header="Bearer SECRET")

    backend.put_entry("build", "abc", {"v": 1})
    assert backend.get_entry("build", "abc") == {"v": 1}

    # Wrong token → PUT fails
    backend2 = HTTPBackend(base_url=f"http://{host}:{port}", auth_header="Bearer WRONG")
    with pytest.raises(RuntimeError):
        backend2.put_entry("build", "xyz", {"v": 2})
