import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.rpc_client.client import RpcClient


@pytest.fixture
def fake_http_server():
    state = {
        "requests": [],
        "status": 200,
        "payload": {"ok": True},
        "raw_body": None,
        "delay": 0,
        "download": b"result-bytes",
    }

    class Handler(BaseHTTPRequestHandler):
        def _respond(self):
            if state["delay"]:
                time.sleep(state["delay"])
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            state["requests"].append(
                {
                    "method": self.command,
                    "path": self.path,
                    "json": json.loads(body) if body else None,
                }
            )

            if self.path.startswith("/results/") and state["status"] == 200:
                content = state["download"]
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

            raw = state["raw_body"]
            if raw is None:
                raw = json.dumps(state["payload"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        do_GET = _respond
        do_POST = _respond

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    ("method_name", "args", "expected_method", "expected_path", "expected_json"),
    [
        ("health", (), "GET", "/health", None),
        ("status", (), "GET", "/status", None),
        ("session_start", (True,), "POST", "/session/start", {"hide": True}),
        ("session_close", (), "POST", "/session/close", {}),
        ("file_save", ("a.fsp",), "POST", "/model/save", {"file_path": "a.fsp"}),
        ("file_load", ("a.fsp",), "POST", "/model/load", {"file_path": "a.fsp"}),
        ("eval", ("?getversion;",), "POST", "/debug/eval", {"cmd": "?getversion;"}),
        ("getv", ("x",), "POST", "/debug/getv", {"name": "x"}),
        ("setv", ("x", 2), "POST", "/debug/setv", {"name": "x", "value": 2}),
        ("run", (), "POST", "/simulation/run", {}),
        (
            "getresult",
            ("m", "T"),
            "POST",
            "/simulation/result",
            {"monitor": "m", "attribute": "T"},
        ),
        (
            "getelectric",
            ("m",),
            "POST",
            "/simulation/electric",
            {"monitor": "m"},
        ),
        (
            "addfdtd",
            ({"dimension": "3D"},),
            "POST",
            "/geometry/fdtd-region",
            {"dimension": "3D"},
        ),
        (
            "addrect",
            ({"name": "wg"},),
            "POST",
            "/geometry/rectangle",
            {"name": "wg"},
        ),
        (
            "addcircle",
            ({"name": "ring"},),
            "POST",
            "/geometry/circle",
            {"name": "ring"},
        ),
    ],
)
def test_client_uses_v1_routes(
    fake_http_server,
    method_name,
    args,
    expected_method,
    expected_path,
    expected_json,
):
    state, base_url = fake_http_server
    client = RpcClient(base_url)

    response = getattr(client, method_name)(*args)

    assert response == {"ok": True}
    assert state["requests"][-1] == {
        "method": expected_method,
        "path": expected_path,
        "json": expected_json,
    }


@pytest.mark.parametrize(
    ("status", "error_type"),
    [(400, "validation_error"), (409, "session_not_active"), (500, "internal_error")],
)
def test_client_preserves_structured_http_errors(
    fake_http_server, status, error_type
):
    state, base_url = fake_http_server
    state["status"] = status
    state["payload"] = {
        "ok": False,
        "error": {"type": error_type, "message": "failed", "details": {}},
    }

    response = RpcClient(base_url).run()

    assert response == state["payload"]


def test_client_reports_connection_error():
    client = RpcClient("http://127.0.0.1:1", timeout=0.05)

    response = client.health()

    assert response["ok"] is False
    assert response["error"]["type"] == "connection_error"


def test_client_reports_timeout_as_unknown_remote_state(fake_http_server):
    state, base_url = fake_http_server
    state["delay"] = 0.2
    client = RpcClient(base_url, timeout=0.02)

    response = client.run()

    assert response["ok"] is False
    assert response["error"]["type"] == "timeout"
    assert response["error"]["details"]["remote_state"] == "unknown"


def test_client_reports_invalid_json_response(fake_http_server):
    state, base_url = fake_http_server
    state["raw_body"] = b"not-json"

    response = RpcClient(base_url).health()

    assert response["ok"] is False
    assert response["error"]["type"] == "invalid_response"


def test_results_download_writes_file(fake_http_server, tmp_path):
    state, base_url = fake_http_server
    target = tmp_path / "result.mat"

    response = RpcClient(base_url).results_download("results/result.mat", str(target))

    assert response["ok"] is True
    assert Path(response["saved_to"]).read_bytes() == state["download"]
    assert state["requests"][-1]["path"] == "/results/results/result.mat"


def test_results_download_preserves_404_error(fake_http_server, tmp_path):
    state, base_url = fake_http_server
    state["status"] = 404
    state["payload"] = {
        "ok": False,
        "error": {
            "type": "file_not_found",
            "message": "missing",
            "details": {},
        },
    }

    response = RpcClient(base_url).results_download(
        "results/missing.mat", str(tmp_path / "missing.mat")
    )

    assert response == state["payload"]
