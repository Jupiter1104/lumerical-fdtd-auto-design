from pathlib import Path

import pytest

from src.analysis_group_runtime import (
    AnalysisGroupInspector,
    AnalysisRuntimeError,
    LumapiBridge,
    SessionOperationGate,
)
from src.object_library_catalog import ObjectLibraryCatalog


class ProbeFdtd:
    def __init__(self):
        self.project = ["original"]
        self.saved = {}
        self.loaded = []
        self.selected = None
        self.properties = {"x span": 1e-6}
        self.layout = True
        self._model_file = "original.fsp"

    def layoutmode(self):
        return 1 if self.layout else 0

    def save(self, path):
        self.saved[str(path)] = list(self.project)
        self._model_file = str(path)

    def load(self, path):
        self.project = list(self.saved[str(path)])
        self.loaded.append(str(path))
        self._model_file = str(path)

    def newproject(self):
        self.project = []

    def addobject(self, script_id):
        self.project.append(script_id)
        self.selected = script_id

    def set(self, name, value):
        if name == "name":
            self.selected = value

    def queryuserprop(self, name):
        return {"name": ["x span"], "type": [2]}

    def queryanalysisprop(self, name):
        return {"name": ["make plots"], "type": [0]}

    def queryanalysisresult(self, name):
        return {"name": ["T"], "type": [0]}

    def getnamed(self, name, prop=None):
        return self.properties.get(prop)

    def querynamed(self, name):
        return "name\nx span"

    def ls(self):
        return list(self.project)


def ready_catalog(tmp_path):
    catalog = ObjectLibraryCatalog(tmp_path / "catalog")
    catalog.ensure(
        {
            "product": "FDTD",
            "solver_version": "2024 R2.4",
            "path_version_tag": "v242",
            "lumapi_sha256": "sha256:abc",
        },
        lambda: ["power_transmission_box"],
    )
    return catalog


def test_probe_restores_project_and_caches_schema(tmp_path):
    fdtd = ProbeFdtd()
    catalog = ready_catalog(tmp_path)
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd),
        catalog,
        tmp_path / "work",
        SessionOperationGate(),
    )

    result = inspector.inspect("power_transmission_box")

    assert result["status"] == "verified_analysis_group"
    assert result["analysis_results"] == [{"name": "T", "type_code": 0}]
    assert result["probe_evidence"]["restore_verified"] is True
    assert fdtd.project == ["original"]
    assert fdtd._model_file == "original.fsp"
    assert catalog.get_probe("power_transmission_box")["status"] == "verified_analysis_group"


def test_cached_verified_probe_does_not_insert_again(tmp_path):
    fdtd = ProbeFdtd()
    catalog = ready_catalog(tmp_path)
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd), catalog, tmp_path / "work", SessionOperationGate()
    )
    first = inspector.inspect("power_transmission_box")
    add_count = len([item for item in fdtd.saved])
    second = inspector.inspect("power_transmission_box")
    assert second == first
    assert len(fdtd.saved) == add_count


def test_restore_failure_stops_without_fallback(tmp_path):
    class BrokenRestore(ProbeFdtd):
        def load(self, path):
            raise RuntimeError("cannot restore")

    inspector = AnalysisGroupInspector(
        LumapiBridge(BrokenRestore()),
        ready_catalog(tmp_path),
        tmp_path / "work",
        SessionOperationGate(),
    )
    with pytest.raises(AnalysisRuntimeError) as exc:
        inspector.inspect("power_transmission_box")
    assert exc.value.error_type == "analysis_probe_restore_failed"


def test_probe_refuses_analysis_mode_without_switching_layout(tmp_path):
    fdtd = ProbeFdtd()
    fdtd.layout = False
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd),
        ready_catalog(tmp_path),
        tmp_path / "work",
        SessionOperationGate(),
    )
    with pytest.raises(AnalysisRuntimeError) as exc:
        inspector.inspect("power_transmission_box")
    assert exc.value.error_type == "analysis_probe_unavailable"
    assert fdtd.saved == {}


def test_probe_failed_is_not_retried_in_same_inspector_session(tmp_path):
    class BrokenProbe(ProbeFdtd):
        def __init__(self):
            super().__init__()
            self.query_calls = 0

        def queryuserprop(self, name):
            self.query_calls += 1
            raise RuntimeError("temporary query failure")

    fdtd = BrokenProbe()
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd),
        ready_catalog(tmp_path),
        tmp_path / "work",
        SessionOperationGate(),
    )
    first = inspector.inspect("power_transmission_box")
    second = inspector.inspect("power_transmission_box")
    assert first["status"] == "probe_failed"
    assert second == first
    assert fdtd.query_calls == 1


def test_probe_failed_can_retry_once_after_inspector_restart(tmp_path):
    class RecoveringProbe(ProbeFdtd):
        def __init__(self):
            super().__init__()
            self.fail = True

        def queryuserprop(self, name):
            if self.fail:
                raise RuntimeError("temporary query failure")
            return super().queryuserprop(name)

    fdtd = RecoveringProbe()
    catalog = ready_catalog(tmp_path)
    first = AnalysisGroupInspector(
        LumapiBridge(fdtd), catalog, tmp_path / "work1", SessionOperationGate()
    )
    assert first.inspect("power_transmission_box")["status"] == "probe_failed"
    fdtd.fail = False
    restarted = AnalysisGroupInspector(
        LumapiBridge(fdtd), catalog, tmp_path / "work2", SessionOperationGate()
    )
    assert (
        restarted.inspect("power_transmission_box")["status"]
        == "verified_analysis_group"
    )


def test_non_analysis_object_is_cached_without_retry(tmp_path):
    class StructureObject(ProbeFdtd):
        def queryanalysisprop(self, name):
            raise RuntimeError("not an analysis group")

    fdtd = StructureObject()
    inspector = AnalysisGroupInspector(
        LumapiBridge(fdtd),
        ready_catalog(tmp_path),
        tmp_path / "work",
        SessionOperationGate(),
    )
    first = inspector.inspect("power_transmission_box")
    second = inspector.inspect("power_transmission_box")
    assert first["status"] == "not_analysis_group"
    assert second == first


def test_operation_gate_allows_nested_probe_inside_recipe_build():
    gate = SessionOperationGate()
    with gate.acquire("recipe_build"):
        assert gate.active_kind == "recipe_build"
        with gate.acquire("analysis_probe"):
            assert gate.active_kind == "analysis_probe"
        assert gate.active_kind == "recipe_build"
    assert gate.active_kind is None


# ---------------------------------------------------------------------------
# Service-level tests (Task 6)
# ---------------------------------------------------------------------------

from src.analysis_group_runtime import AnalysisGroupService
from src.windows_fdtd_adapter import WindowsFdtdAdapter


class BuildFdtd(ProbeFdtd):
    def __init__(self):
        super().__init__()
        self.runsetup_calls = []

    def setnamed(self, name, prop, value):
        self.properties[prop] = value

    def select(self, name):
        self.selected = name

    def runsetup(self):
        self.runsetup_calls.append(self.selected)

    def delete(self):
        if self.selected in self.project:
            self.project.remove(self.selected)

    def eval(self, script):
        if script.startswith("addanalysisgroup"):
            self.project.append("custom")


def service(tmp_path, fdtd=None):
    raw = fdtd or BuildFdtd()
    catalog = ready_catalog(tmp_path)
    inspector = AnalysisGroupInspector(
        LumapiBridge(raw), catalog, tmp_path / "work", SessionOperationGate()
    )
    return AnalysisGroupService(
        adapter=WindowsFdtdAdapter(raw),
        bridge=LumapiBridge(raw),
        catalog=catalog,
        inspector=inspector,
    ), raw


def test_service_selects_probes_configures_and_verifies_builtin(tmp_path):
    runtime, fdtd = service(tmp_path)
    result = runtime.create({
        "name": "power_analysis",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "recipe_context": {
            "solver": {"x span": 3e-6},
            "monitors": [{"type": "power_monitor"}],
            "outputs": ["T"],
            "fom": {"result": "T"},
        },
        "parameter_overrides": {},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "properties": {},
        "dry_run": False,
    })

    assert result["source"] == "builtin"
    assert result["script_id"] == "power_transmission_box"
    assert result["parameters"]["applied"]["x span"] == 3e-6
    assert result["setup_verified"] is True
    assert result["physical_conclusion"] is False
    assert fdtd.runsetup_calls == ["power_analysis"]


def test_dry_run_never_executes_probe(tmp_path):
    runtime, fdtd = service(tmp_path)
    before = dict(fdtd.saved)
    result = runtime.create({
        "name": "power_analysis",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "recipe_context": {"outputs": ["T"]},
        "parameter_overrides": {},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "properties": {},
        "dry_run": True,
    })
    assert fdtd.saved == before
    assert result["probe_required"] is True


def test_low_confidence_falls_back_to_custom(tmp_path):
    runtime, _ = service(tmp_path)
    result = runtime.create({
        "name": "unknown_analysis",
        "analysis_intent": {"kind": "unknown", "outputs": []},
        "recipe_context": {},
        "parameter_overrides": {},
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "",
        "properties": {},
        "dry_run": False,
    })
    assert result["source"] == "custom"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "no_high_confidence_match"


def test_require_builtin_rejects_low_confidence(tmp_path):
    runtime, _ = service(tmp_path)
    with pytest.raises(AnalysisRuntimeError) as exc:
        runtime.create({
            "name": "required",
            "analysis_intent": {"kind": "unknown", "outputs": []},
            "recipe_context": {},
            "parameter_overrides": {},
            "prefer_builtin": False,
            "require_builtin": True,
            "script_id": "",
            "properties": {},
            "dry_run": False,
        })
    assert exc.value.error_type == "builtin_analysis_group_no_high_confidence_match"


# ---------------------------------------------------------------------------
# Autonomous analysis group acceptance test (Task 9)
# ---------------------------------------------------------------------------

import importlib
import sys


@pytest.fixture
def server_module():
    sys.modules.pop("rpc_server", None)
    return importlib.import_module("rpc_server")


@pytest.fixture
def fake_backend_for_acceptance():
    from test_fdtd_20_step_fake_lumapi import FakeFdtdBackend

    return FakeFdtdBackend()


def test_autonomous_builtin_analysis_group_flow(
    server_module, fake_backend_for_acceptance, tmp_path
):
    """Prove the full autonomous selection flow through the HTTP route.

    intent -> enumerate -> shortlist -> probe -> configure -> runsetup -> readback
    """
    from src.analysis_group_runtime import (
        AnalysisGroupInspector,
        AnalysisGroupService,
        LumapiBridge,
        SessionOperationGate,
    )
    from src.object_library_catalog import ObjectLibraryCatalog
    from src.windows_fdtd_adapter import WindowsFdtdAdapter

    backend = fake_backend_for_acceptance

    catalog = ObjectLibraryCatalog(tmp_path / "catalog")
    catalog.ensure(
        {
            "product": "FDTD",
            "solver_version": "2024 R2.4",
            "path_version_tag": "v242",
            "lumapi_sha256": "sha256:fake",
        },
        backend.addobject,
    )
    bridge = LumapiBridge(backend)
    service = AnalysisGroupService(
        WindowsFdtdAdapter(backend),
        bridge,
        catalog,
        AnalysisGroupInspector(
            bridge, catalog, tmp_path / "probe", SessionOperationGate()
        ),
    )
    app = server_module.create_app(
        backend=backend,
        object_library_catalog=catalog,
        analysis_group_service=service,
    )
    response = app.test_client().post(
        "/analysis-groups",
        json={
            "name": "power_analysis",
            "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
            "recipe_context": {
                "solver": {"x span": 3e-6},
                "monitors": [{"type": "power_monitor"}],
                "outputs": ["T"],
                "fom": {"result": "T"},
            },
            "prefer_builtin": True,
            "parameter_overrides": {},
            "properties": {},
        },
    )
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["source"] == "builtin"
    assert payload["script_id"] == "power_transmission_box"
    assert payload["parameters"]["verification"]["x span"]["matched"] is True
    assert backend.runsetup_calls == ["power_analysis"]


# ═══════════════════════════════════════════════════════════════════════════
# LumapiBridge dynamic backend resolution (P0 fix)
# ═══════════════════════════════════════════════════════════════════════════


class LaterFdtd:
    """A backend that only appears after the bridge is constructed."""

    def layoutmode(self):
        return 1

    def ls(self):
        return []


class SecondFdtd:
    """A different backend to test replacement."""

    def layoutmode(self):
        return 0  # Different return to prove we are calling the new one

    def ls(self):
        return []


def test_bridge_resolves_backend_that_appears_after_construction():
    """Bridge created when owner.fdtd=None must use the backend after it is assigned."""
    owner = type("Owner", (), {"fdtd": None})()
    bridge = LumapiBridge(owner)

    # Before fdtd is assigned, calling any lumapi method should raise
    with pytest.raises(AnalysisRuntimeError) as exc:
        bridge.is_layout_mode()
    assert exc.value.error_type == "analysis_probe_failed"

    # Assign the backend after bridge construction
    owner.fdtd = LaterFdtd()

    # Now the bridge must dynamically resolve to the new backend
    assert bridge.is_layout_mode() is True


def test_bridge_resolves_backend_that_is_replaced():
    """When owner.fdtd is replaced, the bridge must use the replacement."""
    owner = type("Owner", (), {"fdtd": LaterFdtd()})()
    bridge = LumapiBridge(owner)
    assert bridge.is_layout_mode() is True

    # Replace with a different backend
    owner.fdtd = SecondFdtd()
    assert bridge.is_layout_mode() is False  # SecondFdtd.layoutmode returns 0


def test_bridge_handles_owner_without_fdtd_attribute():
    """Bridge wraps an owner that has NO fdtd attribute (raw adapter/backend directly)."""
    backend = LaterFdtd()
    bridge = LumapiBridge(backend)
    assert bridge.is_layout_mode() is True


def test_bridge_raises_session_not_active_when_no_backend():
    """When owner has no fdtd and owner itself lacks lumapi methods, raise clear error."""
    owner = type("Owner", (), {})()  # No fdtd, no layoutmode
    bridge = LumapiBridge(owner)
    with pytest.raises(AnalysisRuntimeError) as exc:
        bridge.call("layoutmode")
    assert exc.value.error_type == "analysis_probe_failed"
