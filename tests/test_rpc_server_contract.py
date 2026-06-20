import importlib
import sys
import threading
from pathlib import Path

import pytest


@pytest.fixture
def server_module():
    sys.modules.pop("rpc_server", None)
    return importlib.import_module("rpc_server")


@pytest.fixture
def fake_session(server_module):
    class FakeSession:
        def __init__(self):
            self.calls = []
            self.connected = True

        @property
        def is_connected(self):
            return self.connected

        def status(self):
            return {"connected": self.connected, "version": "v242", "model_file": None}

        def start(self, hide=False):
            self.calls.append(("start", {"hide": hide}))
            return {"version": "v242", "hide": hide, "message": "started"}

        def close(self):
            self.calls.append(("close", {}))
            self.connected = False
            return {"message": "closed"}

        def save(self, file_path=None):
            self.calls.append(("save", {"file_path": file_path}))
            return {"saved_to": file_path or "fdtd_project.fsp"}

        def load(self, file_path):
            self.calls.append(("load", {"file_path": file_path}))
            return {"loaded": file_path}

        def eval(self, cmd):
            self.calls.append(("eval", {"cmd": cmd}))
            return {"result": "ok"}

        def getv(self, name):
            self.calls.append(("getv", {"name": name}))
            return {"value": 1}

        def setv(self, name, value):
            self.calls.append(("setv", {"name": name, "value": value}))
            return {"message": "set"}

        def run(self):
            self.calls.append(("run", {}))
            return {"message": "completed"}

        def getresult(self, monitor, attribute):
            self.calls.append(
                ("getresult", {"monitor": monitor, "attribute": attribute})
            )
            return {"data": [1.0]}

        def getelectric(self, monitor):
            self.calls.append(("getelectric", {"monitor": monitor}))
            return {"data": [2.0]}

        def addfdtd(self, **kwargs):
            self.calls.append(("addfdtd", kwargs))
            return {"message": "region added"}

        def addrect(self, **kwargs):
            self.calls.append(("addrect", kwargs))
            return {"message": "rectangle added"}

        def addcircle(self, **kwargs):
            self.calls.append(("addcircle", kwargs))
            return {"message": "circle added"}

    return FakeSession()


@pytest.fixture
def client(server_module, fake_session):
    app = server_module.create_app(fake_session)
    app.config.update(TESTING=True)
    return app.test_client()


def test_import_does_not_load_lumapi(server_module):
    assert "lumapi" not in sys.modules
    assert "ansys.lumerical.core" not in sys.modules


def test_health_uses_v1_envelope(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "api_version": "v1",
        "server": "fdtd-rpc-server",
        "connected": True,
    }


@pytest.mark.parametrize(
    ("path", "body", "expected_call"),
    [
        ("/session/start", {"hide": True}, ("start", {"hide": True})),
        ("/session/close", {}, ("close", {})),
        ("/model/save", {"file_path": "a.fsp"}, ("save", {"file_path": "a.fsp"})),
        ("/model/load", {"file_path": "a.fsp"}, ("load", {"file_path": "a.fsp"})),
        ("/debug/eval", {"cmd": "?getversion;"}, ("eval", {"cmd": "?getversion;"})),
        ("/debug/getv", {"name": "x"}, ("getv", {"name": "x"})),
        ("/debug/setv", {"name": "x", "value": 2}, ("setv", {"name": "x", "value": 2})),
        ("/simulation/run", {}, ("run", {})),
        (
            "/simulation/result",
            {"monitor": "m", "attribute": "T"},
            ("getresult", {"monitor": "m", "attribute": "T"}),
        ),
        (
            "/simulation/electric",
            {"monitor": "m"},
            ("getelectric", {"monitor": "m"}),
        ),
        (
            "/geometry/fdtd-region",
            {"dimension": "3D"},
            ("addfdtd", {"dimension": "3D"}),
        ),
        (
            "/geometry/rectangle",
            {"name": "wg"},
            ("addrect", {"name": "wg"}),
        ),
        (
            "/geometry/circle",
            {"name": "ring"},
            ("addcircle", {"name": "ring"}),
        ),
    ],
)
def test_v1_routes_dispatch_to_session(client, fake_session, path, body, expected_call):
    response = client.post(path, json=body)

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert fake_session.calls[-1] == expected_call


@pytest.mark.parametrize(
    ("path", "body", "message"),
    [
        ("/model/load", {}, "file_path is required."),
        ("/debug/eval", {}, "cmd is required."),
        ("/debug/getv", {}, "name is required."),
        ("/debug/setv", {}, "name is required."),
        ("/simulation/result", {"monitor": "m"}, "attribute is required."),
    ],
)
def test_validation_errors_are_structured(client, path, body, message):
    response = client.post(path, json=body)

    assert response.status_code == 400
    assert response.get_json() == {
        "ok": False,
        "error": {
            "type": "validation_error",
            "message": message,
            "details": {},
        },
    }


def test_no_active_session_returns_conflict(server_module):
    manager = server_module.SessionManager()
    manager._fdtd = None
    app = server_module.create_app(manager)

    response = app.test_client().post("/simulation/run", json={})

    assert response.status_code == 409
    assert response.get_json()["error"]["type"] == "session_not_active"


def test_duplicate_session_start_returns_conflict(server_module):
    manager = server_module.SessionManager()
    manager._fdtd = object()
    app = server_module.create_app(manager)

    response = app.test_client().post("/session/start", json={})

    assert response.status_code == 409
    assert response.get_json()["error"]["type"] == "session_already_active"
    manager._fdtd = None


def test_raw_lumapi_version_fallback(server_module):
    class RawFdtd:
        def __init__(self):
            self.commands = []

        def eval(self, command):
            self.commands.append(command)

        def getv(self, name):
            assert name == "__rpc_version"
            return "2024 R2.3"

    fdtd = RawFdtd()

    assert server_module.SessionManager._get_version(fdtd) == "2024 R2.3"
    assert fdtd.commands == ["__rpc_version=getversion;"]


def test_version_probe_failure_does_not_break_session_start(
    server_module, monkeypatch
):
    class RawFdtd:
        def eval(self, command):
            raise RuntimeError("unsupported")

        def close(self):
            pass

    class FakeLumapi:
        @staticmethod
        def FDTD(hide=False):
            return RawFdtd()

    manager = server_module.SessionManager()
    manager._fdtd = None
    monkeypatch.setattr(server_module, "_import_lumapi", lambda: FakeLumapi)

    result = manager.start(hide=True)

    assert result["version"] == "unknown"
    assert manager.is_connected is True
    manager.close()


def test_session_close_detaches_when_backend_close_hangs(
    server_module, monkeypatch
):
    close_started = threading.Event()
    release_close = threading.Event()

    class HangingFdtd:
        def close(self):
            close_started.set()
            release_close.wait()

    monkeypatch.setattr(server_module, "FDTD_CLOSE_TIMEOUT_SECONDS", 0.01)
    manager = server_module.SessionManager()
    manager._fdtd = HangingFdtd()
    manager._model_file = "active.fsp"

    try:
        result = manager.close()

        assert close_started.wait(timeout=1.0)
        assert result["close_state"] == "timed_out"
        assert result["message"] == "FDTD session detached; backend close did not confirm."
        assert manager.is_connected is False
        assert manager.status() == {
            "connected": False,
            "version": None,
            "model_file": None,
            "object_library": {"status": "unavailable"},
        }
    finally:
        release_close.set()


def test_missing_model_file_returns_not_found(server_module, tmp_path):
    manager = server_module.SessionManager()
    manager._fdtd = object()
    app = server_module.create_app(manager)

    response = app.test_client().post(
        "/model/load", json={"file_path": str(tmp_path / "missing.fsp")}
    )

    assert response.status_code == 404
    assert response.get_json()["error"]["type"] == "file_not_found"
    manager._fdtd = None


def test_unhandled_backend_exception_returns_internal_error(server_module, fake_session):
    def fail():
        raise RuntimeError("backend exploded")

    fake_session.run = fail
    app = server_module.create_app(fake_session)

    response = app.test_client().post("/simulation/run", json={})

    assert response.status_code == 500
    assert response.get_json()["error"]["type"] == "internal_error"


@pytest.mark.parametrize(
    ("legacy", "replacement", "body"),
    [
        ("/session/stop", "/session/close", {}),
        ("/file/save", "/model/save", {"file_path": "a.fsp"}),
        ("/file/load", "/model/load", {"file_path": "a.fsp"}),
        ("/eval", "/debug/eval", {"cmd": "?getversion;"}),
        ("/getv", "/debug/getv", {"name": "x"}),
        ("/setv", "/debug/setv", {"name": "x", "value": 2}),
        ("/sim/run", "/simulation/run", {}),
        (
            "/sim/getresult",
            "/simulation/result",
            {"monitor": "m", "attribute": "T"},
        ),
        ("/sim/getelectric", "/simulation/electric", {"monitor": "m"}),
        ("/geom/addfdtd", "/geometry/fdtd-region", {"dimension": "3D"}),
        ("/geom/addrect", "/geometry/rectangle", {"name": "wg"}),
        ("/geom/addcircle", "/geometry/circle", {"name": "ring"}),
    ],
)
def test_legacy_routes_are_thin_deprecated_aliases(
    client, legacy, replacement, body
):
    response = client.post(legacy, json=body)
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["meta"] == {
        "deprecated_route": legacy,
        "use_instead": replacement,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Recipe build route tests
# ═══════════════════════════════════════════════════════════════════════════

MINIMAL_RECIPE = {
    "schema_version": "1.0",
    "parameters": {
        "pillar_radius": {
            "type": "float",
            "default": 100e-9,
            "min": 50e-9,
            "max": 200e-9,
            "unit": "m",
            "source_ref": {"locator": "model::pillar_radius"},
        }
    },
    "assumptions": [
        {"parameter": "pillar_radius", "reason": "Typical value for NIR metasurface"}
    ],
    "materials": [
        {"name": "SiO2", "type": "dielectric", "properties": {"index": 1.45}}
    ],
    "geometry": [
        {
            "type": "rectangle",
            "name": "pillar",
            "properties": {"x_span": "${pillar_radius} * 2"},
        }
    ],
}


def test_recipe_build_requires_approval(server_module, fake_session):
    """POST /recipes/build with approved=false returns approval_required."""
    from src.device_recipe import compile_recipe

    app = server_module.create_app(fake_session)
    app.config.update(TESTING=True)
    client = app.test_client()

    compile_result = compile_recipe(MINIMAL_RECIPE)
    assert compile_result["ok"] is True

    response = client.post(
        "/recipes/build",
        json={
            "recipe": MINIMAL_RECIPE,
            "compile_fingerprint": compile_result["compile_fingerprint"],
            "output_fsp": "C:\\Users\\me\\device.fsp",
            "approved": False,
        },
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["type"] == "approval_required"


def test_recipe_build_rejects_fingerprint_mismatch(server_module, fake_session):
    """POST /recipes/build with wrong fingerprint returns compile_fingerprint_mismatch."""
    from src.device_recipe import compile_recipe

    app = server_module.create_app(fake_session)
    app.config.update(TESTING=True)
    client = app.test_client()

    compile_result = compile_recipe(MINIMAL_RECIPE)
    assert compile_result["ok"] is True

    response = client.post(
        "/recipes/build",
        json={
            "recipe": MINIMAL_RECIPE,
            "compile_fingerprint": "sha256:deadbeef",
            "output_fsp": "C:\\Users\\me\\device.fsp",
            "approved": True,
        },
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["error"]["type"] == "compile_fingerprint_mismatch"


def test_recipe_build_saves_fsp_on_valid_recipe(server_module, fake_session):
    """POST /recipes/build with correct fingerprint + approved saves .fsp."""
    from src.device_recipe import compile_recipe

    app = server_module.create_app(fake_session)
    app.config.update(TESTING=True)
    client = app.test_client()

    compile_result = compile_recipe(MINIMAL_RECIPE)
    assert compile_result["ok"] is True

    output_path = "C:\\Users\\me\\device.fsp"

    response = client.post(
        "/recipes/build",
        json={
            "recipe": MINIMAL_RECIPE,
            "compile_fingerprint": compile_result["compile_fingerprint"],
            "output_fsp": output_path,
            "approved": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["model_path"] == output_path
    assert "objects" in payload
    assert "log" in payload
    assert isinstance(payload["objects"], list)

    # Verify session.save was called with the output path
    save_calls = [c for c in fake_session.calls if c[0] == "save"]
    assert len(save_calls) == 1
    assert save_calls[0][1]["file_path"] == output_path


# ═══════════════════════════════════════════════════════════════════════════
# Object library catalog tests (Task 2)
# ═══════════════════════════════════════════════════════════════════════════


def test_session_start_enumerates_object_library_once(
    server_module, monkeypatch, tmp_path
):
    from src.object_library_catalog import ObjectLibraryCatalog

    class RawFdtd:
        def __init__(self):
            self.addobject_calls = 0

        def getversion(self):
            return "2024 R2.4"

        def addobject(self):
            self.addobject_calls += 1
            return ["power_box", "farfield_box"]

        def close(self):
            pass

    raw = RawFdtd()

    class FakeLumapi:
        __file__ = None

        @staticmethod
        def FDTD(hide=False):
            return raw

    manager = server_module.SessionManager()
    manager._fdtd = None
    manager.configure_object_library(ObjectLibraryCatalog(tmp_path))
    monkeypatch.setattr(server_module, "_import_lumapi", lambda: FakeLumapi)

    result = manager.start(hide=True)

    assert raw.addobject_calls == 1
    assert result["object_library"]["status"] in {"ready", "identity_unstable"}
    assert result["object_library"]["script_id_count"] == 2
    assert manager.status()["object_library"]["script_id_count"] == 2
    manager.close()


def test_catalog_enumeration_failure_keeps_session_active(
    server_module, monkeypatch, tmp_path
):
    from src.object_library_catalog import ObjectLibraryCatalog

    class RawFdtd:
        def getversion(self):
            return "2024 R2.4"

        def addobject(self):
            raise RuntimeError("library unavailable")

        def close(self):
            pass

    class FakeLumapi:
        __file__ = None

        @staticmethod
        def FDTD(hide=False):
            return RawFdtd()

    manager = server_module.SessionManager()
    manager._fdtd = None
    manager.configure_object_library(ObjectLibraryCatalog(tmp_path))
    monkeypatch.setattr(server_module, "_import_lumapi", lambda: FakeLumapi)

    result = manager.start()

    assert manager.is_connected is True
    assert result["object_library"]["status"] == "unavailable"
    assert (
        result["object_library"]["enumeration_error"]["type"]
        == "object_library_enumeration_failed"
    )
    manager.close()
