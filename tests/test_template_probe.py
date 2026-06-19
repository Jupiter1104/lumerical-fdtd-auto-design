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
        if with_file:
            self.__file__ = file_path


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
               getnamednumber, getversion, eval (restricted), getv.

    Forbidden and NOT implemented: save, run, runjobs, runanalysis, set,
    setnamed, delete, addrect, addcircle, add*, putv, importdataset.
    """

    def __init__(self, scenario="baseline"):
        self.calls = []
        self._scenario = scenario
        self._scope = "::"
        self._selected = []
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
                    "dimension": "3D", "mesh accuracy": 3,
                    "x min bc": "PML", "x max bc": "PML",
                    "y min bc": "periodic", "y max bc": "periodic",
                    "z min bc": "PML", "z max bc": "PML",
                    "simulation time": 5e-12,
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
                ("mesh", "Mesh", {}),
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
        return tree

    def _build_scripts(self):
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

    def getnumber(self):
        self.calls.append(("getnumber",))
        return len(self._selected)

    def get(self, prop, index):
        self.calls.append(("get", prop, index))
        name, obj_type, props = self._selected[index - 1]
        if prop == "name":
            return name
        elif prop == "type":
            return obj_type
        return props.get(prop, "")

    def getnamed(self, path, prop):
        self.calls.append(("getnamed", path, prop))
        found = self._find(path)

        if found is not None:
            _scope, _name, obj_type, props = found

            # Check script properties first
            if path in self._script_text and prop in self._script_text[path]:
                return self._script_text[path][prop]

            # Type property
            if prop == "type":
                return obj_type

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
