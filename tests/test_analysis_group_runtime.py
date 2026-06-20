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
