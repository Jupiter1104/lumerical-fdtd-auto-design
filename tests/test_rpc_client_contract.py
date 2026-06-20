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

            if (
                self.path.startswith("/results/")
                and state["status"] == 200
                and any(
                    self.path.endswith(ext)
                    for ext in (".mat", ".fsp", ".ldf", ".txt", ".json", ".h5", ".dat")
                )
            ):
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
        ("jobs_plan", ({"mode": "mock"},), "POST", "/jobs/plan", {"mode": "mock"}),
        ("jobs_start", ({"mode": "mock"},), "POST", "/jobs/start", {"mode": "mock"}),
        ("jobs_get", ("job_1",), "GET", "/jobs/job_1", None),
        ("jobs_tasks", ("job_1",), "GET", "/jobs/job_1/tasks", None),
        (
            "jobs_resume",
            ("job_1", {"mode": "mock"}),
            "POST",
            "/jobs/job_1/resume",
            {"mode": "mock"},
        ),
        # --- v1 typed API: project management ---
        ("project_new", ("new_device", True), "POST", "/project/new", {"name": "new_device", "discard_unsaved": True}),
        ("project_status", (), "GET", "/project/status", None),
        ("project_load", ("test.fsp",), "POST", "/project/load", {"file_path": "test.fsp"}),
        ("project_save", ("test.fsp",), "POST", "/project/save", {"file_path": "test.fsp"}),
        # --- v1 typed API: model ---
        ("switch_to_layout", (), "POST", "/model/layout", {}),
        # --- v1 typed API: objects ---
        ("object_create", ("rectangle", "rect_1", {"x span": 1e-6}, True), "POST", "/objects", {"object_type": "rectangle", "name": "rect_1", "properties": {"x span": 1e-6}, "dry_run": True}),
        ("object_get", ("rect_1", None), "GET", "/objects/rect_1", None),
        ("object_list", (), "GET", "/objects", None),
        ("object_update", ("rect_1", {"x span": 2e-6}), "POST", "/objects/rect_1/update", {"x span": 2e-6}),
        ("object_copy", ("rect_1", "rect_2"), "POST", "/objects/rect_1/copy", {"new_name": "rect_2"}),
        ("object_rename", ("rect_1", "wg"), "POST", "/objects/rect_1/rename", {"new_name": "wg"}),
        ("object_delete", ("rect_1",), "POST", "/objects/rect_1/delete", {}),
        ("group_update", ({"updates": []},), "POST", "/objects/group-update", {"updates": []}),
        # --- v1 typed API: materials ---
        ("material_list", (), "GET", "/materials", None),
        ("material_create", ({"name": "Si", "index": 3.5},), "POST", "/materials/create", {"name": "Si", "index": 3.5}),
        ("material_get", ("Si",), "GET", "/materials/Si", None),
        ("material_update", ("Si", {"index": 4.0}), "POST", "/materials/Si/update", {"index": 4.0}),
        ("material_assign", ({"material": "Si", "objects": ["rect_1"]},), "POST", "/materials/assign", {"material": "Si", "objects": ["rect_1"]}),
        ("material_fit_diagnose", ({"material": "Si"},), "POST", "/materials/fit-diagnose", {"material": "Si"}),
        # --- v1 typed API: solver ---
        ("solver_get", (), "GET", "/solver", None),
        ("solver_update", ({"mesh_accuracy": 3},), "POST", "/solver/update", {"mesh_accuracy": 3}),
        ("mesh_diagnose", (), "GET", "/solver/mesh-diagnose", None),
        ("resource_estimate", (), "GET", "/solver/resource-estimate", None),
        # --- v1 typed API: sources ---
        ("source_create", ("plane_source", "src", {"wavelength start": 1.5e-6}, True), "POST", "/sources", {"source_type": "plane_source", "name": "src", "properties": {"wavelength start": 1.5e-6}, "dry_run": True}),
        ("source_get", ("src",), "GET", "/sources/src", None),
        ("source_update", ("src", {"wavelength": 1.55e-6}), "POST", "/sources/src/update", {"wavelength": 1.55e-6}),
        # --- v1 typed API: monitors ---
        ("monitor_create", ("power_monitor", "mon", {"frequency points": 5}, True), "POST", "/monitors", {"monitor_type": "power_monitor", "name": "mon", "properties": {"frequency points": 5}, "dry_run": True}),
        ("monitor_get", ("mon",), "GET", "/monitors/mon", None),
        ("monitor_update", ("mon", {"frequency points": 10}), "POST", "/monitors/mon/update", {"frequency points": 10}),
        # --- v1 typed API: analysis groups ---
        ("analysis_group_create", ("ag", {"script": "T=1;"}, True), "POST", "/analysis-groups", {"name": "ag", "properties": {"script": "T=1;"}, "dry_run": True, "prefer_builtin": False, "require_builtin": False, "script_id": "", "analysis_intent": {}, "recipe_context": {}, "parameter_overrides": {}}),
        ("analysis_group_create", ("ag", {}, True, True, False, "power_transmission_box"), "POST", "/analysis-groups", {"name": "ag", "properties": {}, "dry_run": True, "prefer_builtin": True, "require_builtin": False, "script_id": "power_transmission_box", "analysis_intent": {}, "recipe_context": {}, "parameter_overrides": {}}),
        (
            "analysis_group_create",
            (
                "ag",
                {},
                True,
                True,
                False,
                "",
                {"kind": "transmission", "outputs": ["T"]},
                {"outputs": ["T"]},
                {"x span": 2e-6},
            ),
            "POST",
            "/analysis-groups",
            {
                "name": "ag",
                "properties": {},
                "dry_run": True,
                "prefer_builtin": True,
                "require_builtin": False,
                "script_id": "",
                "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
                "recipe_context": {"outputs": ["T"]},
                "parameter_overrides": {"x span": 2e-6},
            },
        ),
        ("analysis_group_get", ("ag",), "GET", "/analysis-groups/ag", None),
        ("analysis_group_update", ("ag", {"script": "T=0.5;"}), "POST", "/analysis-groups/ag/update", {"script": "T=0.5;"}),
        # --- v1 typed API: results ---
        ("result_list", (), "GET", "/results", None),
        ("result_read", ("mon", "T"), "GET", "/results/mon/T", None),
        ("result_describe", ("mon",), "GET", "/results/mon/describe", None),
        # --- v1 typed API: recipe build ---
        (
            "recipe_build",
            ({"schema_version": "1.0"}, "sha256:abc", "C:\\Users\\me\\device.fsp", True),
            "POST",
            "/recipes/build",
            {
                "recipe": {"schema_version": "1.0"},
                "compile_fingerprint": "sha256:abc",
                "output_fsp": "C:\\Users\\me\\device.fsp",
                "approved": True,
            },
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
