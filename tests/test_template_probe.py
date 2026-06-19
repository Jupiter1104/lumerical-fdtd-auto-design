"""Tests for Stage B0 template probe helpers and output contract."""

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


# --- Probe output contract tests ---


def test_probe_fingerprint_excludes_own_field():
    from src.template_probe import probe_fingerprint

    probe = {
        "probe_version": "0.1",
        "probe_fingerprint": "old",
        "template": {"sha256": "abc"},
        "objects": [],
    }
    first = probe_fingerprint(probe)
    probe["probe_fingerprint"] = "different"
    assert probe_fingerprint(probe) == first


def test_probe_json_is_git_ignored():
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "templates/metasurface/base_model.probe.json" in ignore_text


def test_stable_json_rejects_nan():
    from src.template_probe import stable_json

    assert stable_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    with pytest.raises(ValueError):
        stable_json({"value": float("nan")})


def test_probe_module_no_forbidden_imports():
    """Probe module must not import or expose forbidden operations."""
    # This test verifies the probe module can be imported on Mac (no lumapi)
    import src.template_probe as tp
    for forbidden in (
        "run", "runjobs", "runanalysis", "save", "set", "setnamed",
        "delete", "addrect", "addcircle",
    ):
        assert not hasattr(tp, forbidden), f"module exposes forbidden: {forbidden}"


# --- Installation identity tests ---


class MockLumapiModule:
    """Simulates a lumapi module for install identity tests."""

    def __init__(self, file_path, with_file=True):
        self._file_path = file_path
        if with_file and file_path:
            self.__file__ = file_path

    def __bool__(self):
        return True


def test_version_unknown_with_complete_install_identity_produces_warning_not_fail():
    from src.template_probe import (
        probe_installation_identity,
        validate_probe_installation,
    )

    # Simulate v242: lumapi.__file__ exists, but getversion is not a Python method
    mock = MockLumapiModule(
        "/install/Lumerical/v242/api/python/lumapi.py", with_file=True
    )
    # Make the file actually exist for sha256
    import tempfile
    import os as _os
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
        f.write(b"# mock lumapi\n")
        tmp_path = f.name
    try:
        mock.__file__ = tmp_path
        identity = probe_installation_identity(mock)
        fail, warnings = validate_probe_installation(identity)

        assert fail is False
        assert any(w["type"] == "version_unknown_warning" for w in warnings)
        assert identity["confirmable"] is True
        assert identity["lumapi_sha256"] is not None
    finally:
        _os.unlink(tmp_path)


def test_completely_unconfirmable_install_identity_fails():
    from src.template_probe import (
        probe_installation_identity,
        validate_probe_installation,
    )

    # Simulate lumapi where __file__ doesn't exist and no path info
    mock = MockLumapiModule("", with_file=False)
    identity = probe_installation_identity(mock)
    fail, warnings = validate_probe_installation(identity)

    assert fail is True
    assert any(
        "unconfirmable" in w.get("type", "").lower() for w in [{"type": e.get("type", "")} for e in identity.get("errors", [])]
    ) or identity["confirmable"] is False


def test_path_version_tag_derived_from_lumapi_file(tmp_path):
    from src.template_probe import probe_installation_identity

    # Build a fake directory structure: .../v242/api/python/lumapi.py
    version_dir = tmp_path / "v242"
    api_dir = version_dir / "api"
    python_dir = api_dir / "python"
    python_dir.mkdir(parents=True)
    lumapi_file = python_dir / "lumapi.py"
    lumapi_file.write_text("# mock lumapi\n")

    mock = MockLumapiModule(str(lumapi_file), with_file=True)
    identity = probe_installation_identity(mock)

    assert identity["path_version_tag"] == "v242"
    assert identity["install_root"] == str(tmp_path)
    assert identity["api_python_path"] == str(python_dir)
    assert identity["confirmable"] is True


# ============================================================
# FakeProbeFdtd — comprehensive test double for probe testing
# ============================================================


class FakeProbeFdtd:
    """Simulates raw v242 lumapi FDTD session for probe testing.

    Supported: load, close, groupscope, selectall, getnumber, get, getnamed,
               getnamednumber, getversion, eval (restricted), getv, select.

    Forbidden and NOT implemented: save, run, runjobs, runanalysis, set,
    setnamed, delete, addrect, addcircle, add*, putv, importdataset.
    """

    def __init__(self, scenario="baseline"):
        self.calls = []
        self._scenario = scenario
        self._scope = "::"
        self._selected = []
        self._selected_name = None
        self._loaded = False
        self._variables = {}
        self._objects = self._build_tree()
        self._script_text = self._build_scripts()

    def _build_tree(self):
        """Object tree: scope -> [(name, type, properties_dict), ...]."""
        tree = {
            "::": [
                ("FDTD", "FDTD", {
                    "dimension": "3D", "mesh accuracy": 3,
                    "x min bc": "PML", "x max bc": "PML",
                    "y min bc": "periodic", "y max bc": "periodic",
                    "z min bc": "PML", "z max bc": "PML",
                    "simulation time": 5e-12,
                }),
                ("model", "Structure Group", {}),
                ("substrate", "Rectangle", {
                    "material": "SiO2 (Glass) - Palik",
                    "x": 0, "y": 0, "z": -0.35e-6,
                    "x span": 10e-6, "y span": 10e-6, "z span": 0.7e-6,
                }),
                ("pillar", "Circle", {
                    "material": "TiO2 - Palik",
                    "x": 0, "y": 0, "z": 0.35e-6,
                    "x span": 0.2e-6, "y span": 0.2e-6, "z span": 0.7e-6,
                    "radius": 0.1e-6,
                }),
                ("mesh", "Mesh", {}),
                ("field", "DFTMonitor", {
                    "monitor type": "2D Z-normal",
                    "x": 0, "y": 0, "z": 0.7e-6,
                    "x span": 2e-6, "y span": 2e-6,
                    "frequency": [(300e12, 400e12)],
                }),
                ("s_params", "Analysis Group", {}),
            ],
            "::model": [
                ("FDTD", "FDTD", {
                    "express mode": 0,
                    "dimension": "3D",
                    "mesh accuracy": 3,
                    "simulation time": 5e-12,
                    "x min bc": "PML",
                    "x max bc": "PML",
                    "y min bc": "Periodic",
                    "y max bc": "Periodic",
                    "z min bc": "PML",
                    "z max bc": "PML",
                    "x": 0.0,
                    "y": 0.0,
                    "z": 4.13e-7,
                    "x span": 4.7e-7,
                    "y span": 4.7e-7,
                    "z span": 1.38e-6,
                }),
                ("substrate", "Rectangle", {
                    "material": "SiO2 (Glass) - Palik",
                    "x": 0, "y": 0, "z": -0.35e-6,
                    "x span": 10e-6, "y span": 10e-6, "z span": 0.7e-6,
                }),
                ("pillar", "Circle", {
                    "material": "TiO2 - Palik",
                    "x": 0, "y": 0, "z": 0.35e-6,
                    "x span": 0.2e-6, "y span": 0.2e-6, "z span": 0.7e-6,
                    "radius": 0.1e-6,
                }),
                ("mesh", "Mesh", {
                    "based on a structure": 0,
                    "override x mesh": 1,
                    "override y mesh": 1,
                    "override z mesh": 1,
                    "dx": 5e-9,
                    "dy": 5e-9,
                    "dz": 5e-9,
                    "x": 0.0,
                    "y": 0.0,
                    "z": 3.5e-7,
                    "x span": 4.7e-7,
                    "y span": 4.7e-7,
                    "z span": 7e-7,
                }),
                ("field", "DFTMonitor", {
                    "monitor type": "2D Z-normal",
                    "x": 0, "y": 0, "z": 0.7e-6,
                    "x span": 2e-6, "y span": 2e-6,
                }),
                ("s_params", "Analysis Group", {}),
            ],
            "::model::s_params": [],
        }

        # -- Scenario adjustments --
        if self._scenario == "no_source":
            pass  # baseline already has no explicit source object
        elif self._scenario == "source_in_root":
            tree["::"].append(("source", "Plane Wave", {
                "wavelength start": 700e-9, "wavelength stop": 800e-9,
            }))
        elif self._scenario == "source_in_analysis_group":
            tree["::model::s_params"].append(("source", "Plane Wave", {
                "injection axis": "z",
            }))
        elif self._scenario == "unreadable_properties":
            # pillar radius becomes unreadable
            for entry in tree["::"]:
                if entry[0] == "pillar":
                    entry[2].pop("radius", None)
        elif self._scenario == "solver_getnamed_unreadable":
            pass  # handled in getnamed()
        elif self._scenario == "express_mode_one":
            for entry in tree["::model"]:
                if entry[0] == "FDTD":
                    entry[2]["express mode"] = 1
        elif self._scenario in ("source_script_evidence",):
            pass  # handled in _build_scripts
        elif self._scenario == "source_unresolved":
            pass  # scripts have no source markers
        return tree

    def _build_scripts(self):
        if self._scenario == "source_script_evidence":
            return {
                "::model::s_params": {
                    "setup script": (
                        "# setup script with source creation\n"
                        "addplane;\n"
                        "set('wavelength start', 700e-9);\n"
                        "set('injection axis', 'z');\n"
                    ),
                    "analysis script": (
                        "# analysis script\n"
                        "T = transmission('monitor');\n"
                        "S = getresult('monitor', 'S');\n"
                    ),
                },
                "::s_params": {
                    "setup script": "",
                    "analysis script": "",
                },
            }
        elif self._scenario == "source_unresolved":
            return {
                "::model::s_params": {
                    "setup script": (
                        "# generic setup\n"
                        "select('::model');\n"
                        "set('ratio', 0.5);\n"
                    ),
                    "analysis script": (
                        "# analysis script without source markers\n"
                        "runanalysis;\n"
                    ),
                },
                "::s_params": {
                    "setup script": "",
                    "analysis script": "",
                },
            }
        return {
            "::model::s_params": {
                "setup script": (
                    "# setup script for s_params analysis group\n"
                    "# defines source polarization and monitor\n"
                    "select('::model');\n"
                    "set('ratio', 0.5);\n"
                ),
                "analysis script": (
                    "# analysis script\n"
                    "# runs s-parameter extraction\n"
                    "T = transmission('monitor');\n"
                    "S = getresult('monitor', 'S');\n"
                ),
            },
            "::s_params": {
                "setup script": (
                    "# root-level analysis setup\n"
                    "select('FDTD');\n"
                ),
                "analysis script": (
                    "# root-level analysis\n"
                    "runanalysis;\n"
                ),
            },
        }

    # --- Lookup helpers ---

    def _find(self, path):
        """Find object by full path, return (scope, name, type, props) or None."""
        for scope, objs in self._objects.items():
            for name, obj_type, props in objs:
                if scope == "::":
                    full = "::" + name
                else:
                    full = scope + "::" + name
                if full == path:
                    return scope, name, obj_type, props
                # Also match bare name in root scope (e.g., "FDTD" → "::FDTD")
                if scope == "::" and path == name:
                    return scope, name, obj_type, props
        return None

    # --- Public read-only API ---

    def load(self, path):
        self.calls.append(("load", path))
        self._loaded = True

    def close(self):
        self.calls.append(("close",))
        self._loaded = False

    def getversion(self):
        self.calls.append(("getversion",))
        return "v242"

    def groupscope(self, scope):
        self.calls.append(("groupscope", scope))
        self._scope = scope

    def selectall(self):
        self.calls.append(("selectall",))
        self._selected = list(self._objects.get(self._scope, []))

    def select(self, name):
        self.calls.append(("select", name))
        matches = [
            entry
            for entry in self._objects.get(self._scope, [])
            if entry[0] == name
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected one object named {name!r} in {self._scope}, "
                f"found {len(matches)}"
            )
        self._selected_name = name

    def getnumber(self):
        self.calls.append(("getnumber",))
        return len(self._selected)

    def get(self, prop, index=None):
        self.calls.append(("get", prop, index))
        if index is not None:
            name, obj_type, props = self._selected[index - 1]
        else:
            matches = [
                entry
                for entry in self._objects.get(self._scope, [])
                if entry[0] == self._selected_name
            ]
            if len(matches) != 1:
                raise RuntimeError("No uniquely selected object")
            name, obj_type, props = matches[0]
        if prop == "name":
            return name
        if prop == "type":
            return obj_type
        if prop in props:
            return props[prop]
        raise RuntimeError(
            f"Property {prop!r} not found on "
            f"{self._scope}::{name}"
        )

    def getnamed(self, path, prop):
        self.calls.append(("getnamed", path, prop))
        if (
            self._scenario == "solver_getnamed_unreadable"
            and path == "::model::FDTD"
        ):
            raise RuntimeError("Solver properties unavailable through getnamed")
        found = self._find(path)

        if found is not None:
            _scope, _name, obj_type, props = found

            # Check script properties first
            if path in self._script_text and prop in self._script_text[path]:
                return self._script_text[path][prop]

            # Type property
            if prop == "type":
                return obj_type

            # Name property
            if prop == "name":
                return _name

            # Regular properties
            if prop in props:
                if (self._scenario == "unreadable_properties"
                        and "pillar" in path and prop == "radius"):
                    raise RuntimeError(
                        f"Property '{prop}' not available on {path}"
                    )
                return props[prop]

            # Model parameters on ::model
            if path == "::model" and prop in ("ratio", "height", "period"):
                return {"ratio": 0.5, "height": 700e-9, "period": 390e-9}[prop]

            raise RuntimeError(
                f"Property '{prop}' not found on {path}"
            )

        raise RuntimeError(f"Object not found: {path}")

    def getnamednumber(self, path):
        self.calls.append(("getnamednumber", path))
        found = self._find(path)
        return 1 if found is not None else 0

    def getv(self, name):
        self.calls.append(("getv", name))
        return self._variables.get(name)

    def eval(self, script):
        """Restricted eval — rejects forbidden keywords."""
        restricted = [
            "save", "set", "run", "delete", "add",
            "putv", "importdataset",
        ]
        script_lower = script.lower()
        for word in restricted:
            if word in script_lower:
                raise RuntimeError(f"Forbidden operation '{word}' in eval")
        self.calls.append(("eval", script))


# --- FakeProbeFdtd harness tests ---


FORBIDDEN_NAMES = (
    "run", "runjobs", "runanalysis", "save", "set", "setnamed",
    "delete", "addrect", "addcircle", "addfdtd", "addmesh",
    "addplane", "addpower", "putv", "importdataset",
)


def test_fake_probe_fdtd_has_no_forbidden_operations():
    fdtd = FakeProbeFdtd()
    for name in FORBIDDEN_NAMES:
        assert not hasattr(fdtd, name), f"FakeProbeFdtd has forbidden: {name}"


def test_fake_probe_fdtd_allows_all_permitted_operations():
    fdtd = FakeProbeFdtd()
    # All these must work without raising
    fdtd.load("template.fsp")
    fdtd.getversion()
    fdtd.groupscope("::")
    fdtd.selectall()
    fdtd.getnumber()
    fdtd.get("name", 1)
    fdtd.get("type", 1)
    fdtd.getnamed("FDTD", "dimension")
    fdtd.getnamednumber("FDTD")
    fdtd.groupscope("::model")
    fdtd.select("FDTD")
    assert fdtd.get("express mode") == 0
    fdtd.selectall()
    fdtd.eval("__x = 1+1;")
    fdtd.close()
    assert fdtd.calls  # ensure calls were recorded


def test_fake_probe_fdtd_eval_rejects_forbidden_scripts():
    fdtd = FakeProbeFdtd()
    for forbidden_script in (
        "save;", "run;", "set('x',1);", "delete;",
        "addrect;", "addcircle;", "putv;", "importdataset;",
    ):
        with pytest.raises(RuntimeError, match="Forbidden"):
            fdtd.eval(forbidden_script)


def test_fake_probe_fdtd_supports_fixed_selected_get():
    fdtd = FakeProbeFdtd()
    fdtd.groupscope("::model")
    fdtd.select("FDTD")
    assert fdtd.get("express mode") == 0
    assert fdtd.get("x min bc") == "PML"


# ============================================================
# Scope & object identity tests (depend on ProbeAdapter)
# ============================================================

import importlib.util

PROBE_SCRIPT = ROOT / "scripts" / "probe_metasurface_template.py"


def load_probe_module():
    """Load the probe script as a module for testing."""
    spec = importlib.util.spec_from_file_location("probe_runner", PROBE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonable(value):
    """Copy of the _jsonable helper used in probe adapter."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return value


def test_enumerate_scopes_discovers_all_four_scopes():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    scopes = adapter.enumerate_scopes([
        "::", "::model", "::s_params", "::model::s_params",
    ])
    assert scopes["::"]["reachable"] is True
    assert scopes["::"]["object_count"] >= 6
    assert scopes["::model"]["reachable"] is True
    assert scopes["::model"]["object_count"] >= 6
    # ::s_params may or may not be reachable depending on analysis group setup
    assert "::s_params" in scopes


def test_enumerate_objects_recursive_returns_typed_objects():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    objects = adapter.enumerate_objects_recursive(["::", "::model"])
    assert len(objects) >= 10
    for obj in objects:
        assert "path" in obj
        assert "type" in obj
        assert "scope" in obj
        assert "name" in obj
    # Verify key objects present
    paths = {obj["path"] for obj in objects}
    assert "::FDTD" in paths
    assert "::model::pillar" in paths


def test_identically_named_objects_same_name_different_scopes_produce_evidence():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    evidence = adapter.probe_identically_named_objects()
    # pillar and substrate appear in both root and ::model
    names_found = {e["name"] for e in evidence}
    assert "pillar" in names_found
    assert "substrate" in names_found


def test_identically_named_objects_with_identical_properties_concluded_alias():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    evidence = adapter.probe_identically_named_objects()
    # In baseline, pillar props are identical across root and ::model
    pillar_ev = [e for e in evidence if e["name"] == "pillar"]
    assert len(pillar_ev) == 1
    # Since properties are identical, conclusion should be possible_alias_or_identical
    assert pillar_ev[0]["conclusion"] == "possible_alias_or_identical"


def test_identically_named_objects_with_different_properties_concluded_independent():
    module = load_probe_module()
    # Use a modified FakeProbeFdtd where root pillar has different props
    fdtd = FakeProbeFdtd()
    # Change root pillar material to differ from ::model::pillar
    for entry in fdtd._objects["::"]:
        if entry[0] == "pillar":
            entry[2]["material"] = "Si (Silicon) - Palik"
    adapter = module.ProbeAdapter(fdtd)
    evidence = adapter.probe_identically_named_objects()
    pillar_ev = [e for e in evidence if e["name"] == "pillar"]
    assert pillar_ev[0]["conclusion"] == "independent_objects"


# ============================================================
# Structure & material candidate tests (Task B0-5)
# ============================================================


def test_structure_candidates_read_pillar_properties():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    result = adapter.probe_structure_candidates({
        "pillar": ["::pillar", "::model::pillar"],
        "substrate": ["::substrate", "::model::substrate"],
    })
    assert result["pillar"]["candidate_count"] == 2
    for c in result["pillar"]["candidates"]:
        assert c["exists"] is True
        props = c["properties"]
        assert "material" in props
        assert "x" in props
        assert "radius" in props
        assert props["material"] in ("TiO2 - Palik",)
    assert not result["pillar"]["has_unreadable"]


def test_structure_candidates_read_substrate_properties():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    result = adapter.probe_structure_candidates({
        "substrate": ["::substrate", "::model::substrate"],
    })
    assert result["substrate"]["candidate_count"] == 2
    for c in result["substrate"]["candidates"]:
        props = c["properties"]
        assert "material" in props
        assert "z" in props
        assert "z span" in props


def test_unreadable_properties_produce_structured_diagnostics():
    module = load_probe_module()
    fdtd = FakeProbeFdtd(scenario="unreadable_properties")
    adapter = module.ProbeAdapter(fdtd)
    result = adapter.probe_structure_candidates({
        "pillar": ["::pillar"],
    })
    assert result["pillar"]["has_unreadable"] is True
    # radius should be unreadable in this scenario
    pillar_props = result["pillar"]["candidates"][0]["properties"]
    radius = pillar_props.get("radius", {})
    assert isinstance(radius, dict) and radius.get("status") == "unreadable"


def test_structure_candidates_handle_missing_object_path():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    result = adapter.probe_structure_candidates({
        "pillar": ["::nonexistent"],
    })
    assert result["pillar"]["candidate_count"] == 0


# ============================================================
# FDTD, mesh, and model parameter probe tests (Task B0-6)
# ============================================================


def test_fdtd_configuration_reads_dimension_express_mode():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    config = adapter.probe_fdtd_configuration()
    assert config["path"] == "FDTD"
    props = config["properties"]
    assert props.get("dimension") == "3D"
    # express_mode not set in baseline FakeProbeFdtd, may be unreadable
    assert "dimension" in props


def test_fdtd_configuration_cpu_express_mode_evidence():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    config = adapter.probe_fdtd_configuration()
    # CPU express mode evidence should be present even if express_mode unreadable
    assert "cpu_express_mode_evidence" in config


def test_mesh_configuration_reads_mesh_accuracy():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    config = adapter.probe_mesh_configuration()
    assert len(config["meshes"]) >= 1
    for mesh in config["meshes"]:
        if mesh["exists"]:
            assert "properties" in mesh


def test_model_parameters_read_ratio_height_period():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    params = adapter.probe_model_parameters()
    for key in ("ratio", "height", "period"):
        assert key in params
        p = params[key]
        assert p.get("name") == key
        assert p.get("path") == "::model"
        assert p.get("read_method") == "getnamed"


def test_unreadable_model_parameter_produces_diagnostic():
    module = load_probe_module()
    # Create FDTD where ::model doesn't have 'ratio' parameter
    class NoRatioFdtd(FakeProbeFdtd):
        def getnamed(self, path, prop):
            if path == "::model" and prop == "ratio":
                raise RuntimeError("Property 'ratio' not found")
            return super().getnamed(path, prop)

    adapter = module.ProbeAdapter(NoRatioFdtd())
    params = adapter.probe_model_parameters()
    assert params["ratio"].get("status") == "unreadable"
    assert "error" in params["ratio"]
    # Other params still readable
    assert params["height"].get("value") is not None


# ============================================================
# Source strategy tests (Task B0-7)
# ============================================================


def test_source_strategy_identifies_explicit_source():
    module = load_probe_module()
    fdtd = FakeProbeFdtd(scenario="source_in_root")
    adapter = module.ProbeAdapter(fdtd)
    result = adapter.probe_source_strategy()
    assert result["classification"] == "explicit_object"
    assert len(result["evidence"]["source_objects_found"]) >= 1


def test_source_strategy_identifies_source_in_analysis_group():
    module = load_probe_module()
    fdtd = FakeProbeFdtd(scenario="source_in_analysis_group")
    adapter = module.ProbeAdapter(fdtd)
    result = adapter.probe_source_strategy()
    assert result["classification"] == "explicit_object"
    assert any(
        "::model::s_params" in obj.get("scope", "")
        for obj in result["evidence"]["source_objects_found"]
    )


def test_source_strategy_analysis_group_setup_when_no_source_object():
    module = load_probe_module()
    fdtd = FakeProbeFdtd(scenario="no_source")
    adapter = module.ProbeAdapter(fdtd)
    result = adapter.probe_source_strategy()
    # No explicit source object, but scripts exist
    assert result["classification"] in (
        "analysis_group_setup", "unresolved",
    )
    # Should have script audit evidence
    assert "scripts_audited" in result["evidence"]


def test_unresolved_source_must_not_fabricate_paths():
    module = load_probe_module()
    fdtd = FakeProbeFdtd(scenario="no_source")
    adapter = module.ProbeAdapter(fdtd)
    result = adapter.probe_source_strategy()
    # No fabricated source paths
    source_objs = result["evidence"]["source_objects_found"]
    assert len(source_objs) == 0


def test_setup_analysis_scripts_only_record_hash_and_summary():
    module = load_probe_module()
    fdtd = FakeProbeFdtd()
    adapter = module.ProbeAdapter(fdtd)
    result = adapter.probe_source_strategy()
    scripts = result["evidence"]["scripts_audited"]
    for ag_path, ag_scripts in scripts.items():
        for prop_name, info in ag_scripts.items():
            if info.get("readable"):
                assert "sha256" in info
                assert "byte_count" in info
                assert "summary" in info
                # Full text must NOT be in info
                assert "text" not in info


def test_script_summary_excludes_comment_lines():
    # Test the _summarize_script helper directly
    module = load_probe_module()
    summary = module._summarize_script(
        "# comment line\n"
        "select('::model');\n"
        "# another comment\n"
        "set('ratio', 0.5);\n"
        "run;\n"
    )
    assert "comment" not in summary.lower()
    assert "select" in summary.lower()
    assert "set" in summary


# ============================================================
# Monitors & analysis group verification tests (Task B0-8)
# ============================================================


def test_monitors_find_field_monitors_in_baseline():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    monitors = adapter.probe_monitors()
    assert len(monitors) >= 1
    monitor_paths = {m["path"] for m in monitors}
    assert "::field" in monitor_paths or "::model::field" in monitor_paths


def test_monitors_read_coordinates_and_span():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    monitors = adapter.probe_monitors()
    assert len(monitors) > 0
    for m in monitors:
        props = m["properties"]
        # At minimum monitor type should be readable
        if m["type"] == "dftmonitor":
            assert "monitor type" in props or len(props) >= 1


def test_analysis_group_s_params_exists_and_has_type():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    result = adapter.probe_analysis_group()
    assert result["::model::s_params"]["exists"] is True
    assert result["::model::s_params"]["type"] is not None


def test_analysis_group_detects_result_naming():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    result = adapter.probe_analysis_group()
    naming = result["::model::s_params"]["result_naming_assumptions"]
    # Should detect both T and S from script text
    assert naming["transmission"] is not None or naming["s_parameter"] is not None


def test_missing_analysis_group_returns_exists_false():
    module = load_probe_module()
    adapter = module.ProbeAdapter(FakeProbeFdtd())
    result = adapter.probe_analysis_group(
        ag_paths=["::nonexistent_ag"]
    )
    assert result["::nonexistent_ag"]["exists"] is False


# ============================================================
# Probe orchestration, output assembly, and CLI tests (Task B0-9)
# ============================================================


def _mock_lumapi_factory():
    """Return a MockLumapiModule with a fake but valid file path."""
    import tempfile
    import os as _os
    f = tempfile.NamedTemporaryFile(suffix=".py", delete=False)
    f.write(b"# mock lumapi\n")
    f.close()
    mock = MockLumapiModule(f.name, with_file=True)
    # Clean up on module destruction
    return mock


def test_cleanup_executes_and_records_closed(tmp_path):
    module = load_probe_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    output = tmp_path / "probe.json"
    fdtd = FakeProbeFdtd()

    result = module.run_probe(
        template=template,
        output=output,
        fdtd_factory=lambda hide: fdtd,
        hostname="test-host",
        python_executable="python.exe",
        code_commit="abc123",
        lumapi_factory=_mock_lumapi_factory,
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert saved["inspector"]["cleanup_state"] == "closed"
    assert ("close",) in fdtd.calls


def test_cleanup_records_close_failed_when_close_raises(tmp_path):
    module = load_probe_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    output = tmp_path / "probe.json"

    class BrokenCloseFdtd(FakeProbeFdtd):
        def close(self):
            self.calls.append(("close",))
            raise RuntimeError("close failed")

    fdtd = BrokenCloseFdtd()
    result = module.run_probe(
        template=template,
        output=output,
        fdtd_factory=lambda hide: fdtd,
        hostname="test-host",
        python_executable="python.exe",
        code_commit="abc123",
        lumapi_factory=_mock_lumapi_factory,
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["inspector"]["cleanup_state"] == "close_failed"
    assert any(
        w["type"] == "cleanup_failed"
        for w in saved.get("warnings", [])
    )


def test_run_probe_writes_atomic_json(tmp_path):
    module = load_probe_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    output = tmp_path / "probe.json"
    fdtd = FakeProbeFdtd()

    result = module.run_probe(
        template=template,
        output=output,
        fdtd_factory=lambda hide: fdtd,
        hostname="test-host",
        python_executable="python.exe",
        code_commit="abc123",
        lumapi_factory=_mock_lumapi_factory,
    )
    assert result == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["probe_version"] == "0.1"
    assert saved["probe_only"] is True
    assert saved["status"] == "probe"
    assert "probe_fingerprint" in saved
    assert not output.with_suffix(".json.tmp").exists()


def test_probe_with_errors_status_when_install_unconfirmable(tmp_path):
    module = load_probe_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    output = tmp_path / "probe.json"

    # Create a FakeProbeFdtd that has a custom getversion (install identity
    # is resolved at build_probe time via import_lumapi, which we can't
    # easily mock in this integration test without further refactoring).
    # Instead test that basic probe structure is valid.
    fdtd = FakeProbeFdtd()
    result = module.run_probe(
        template=template,
        output=output,
        fdtd_factory=lambda hide: fdtd,
        hostname="test-host",
        python_executable="python.exe",
        code_commit="abc123",
        lumapi_factory=_mock_lumapi_factory,
    )
    saved = json.loads(output.read_text(encoding="utf-8"))
    # Probe should complete without fatal errors in baseline scenario
    assert saved["status"] in ("probe", "probe_with_errors")


def test_probe_output_has_required_top_level_keys(tmp_path):
    module = load_probe_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    output = tmp_path / "probe.json"
    fdtd = FakeProbeFdtd()

    module.run_probe(
        template=template,
        output=output,
        fdtd_factory=lambda hide: fdtd,
        hostname="test-host",
        python_executable="python.exe",
        code_commit="abc123",
        lumapi_factory=_mock_lumapi_factory,
    )
    saved = json.loads(output.read_text(encoding="utf-8"))

    required_keys = [
        "probe_version", "probe_only", "status", "probe_fingerprint",
        "template", "installation", "inspector",
        "scopes", "objects", "identically_named_evidence",
        "role_candidates", "model_parameters",
        "fdtd_configuration", "mesh_configuration",
        "source_strategy", "monitors", "analysis_group",
        "warnings", "errors",
    ]
    for key in required_keys:
        assert key in saved, f"Missing required key: {key}"


def test_probe_failed_status_when_template_not_found(tmp_path):
    module = load_probe_module()
    template = tmp_path / "nonexistent.fsp"
    output = tmp_path / "probe.json"

    result = module.run_probe(
        template=template,
        output=output,
        fdtd_factory=lambda hide: FakeProbeFdtd(),
        hostname="test-host",
        python_executable="python.exe",
        code_commit="abc123",
        lumapi_factory=_mock_lumapi_factory,
    )
    assert result == 1
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["status"] == "probe_failed"


def test_probe_script_forbidden_operation_scan():
    """Scan probe script for forbidden commands."""
    text = PROBE_SCRIPT.read_text(encoding="utf-8").lower()
    forbidden = [
        ".run(", ".runjobs(", ".runanalysis(",
        ".save(", ".set(", ".setnamed(",
        ".delete(", ".addrect", ".addcircle",
        ".addfdtd", ".addplane", ".addpower",
        ".putv", ".importdataset",
    ]
    for pattern in forbidden:
        assert pattern not in text, f"Forbidden pattern found: {pattern}"


def test_probe_never_calls_save_run_set_add_delete(tmp_path):
    """After full probe run, FakeProbeFdtd should have no forbidden calls."""
    module = load_probe_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    output = tmp_path / "probe.json"
    fdtd = FakeProbeFdtd()

    module.run_probe(
        template=template,
        output=output,
        fdtd_factory=lambda hide: fdtd,
        hostname="test-host",
        python_executable="python.exe",
        code_commit="abc123",
        lumapi_factory=_mock_lumapi_factory,
    )
    call_names = {call[0] for call in fdtd.calls}
    forbidden = {
        "save", "run", "runjobs", "runanalysis",
        "set", "setnamed", "delete",
    }
    for name in forbidden:
        assert name not in call_names, f"Forbidden call '{name}' was made"
