import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "inspect_metasurface_template.py"


def load_inspector_module():
    spec = importlib.util.spec_from_file_location("template_inspector", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeFdtd:
    def __init__(self):
        self.calls = []
        self.counts = {
            "FDTD": 1,
            "::model": 1,
            "::model::s_params": 1,
        }
        self.properties = {
            ("FDTD", "type"): "FDTD",
            ("::model", "type"): "Structure Group",
            ("::model::s_params", "type"): "Analysis Group",
        }

    def load(self, path):
        self.calls.append(("load", path))

    def getversion(self):
        self.calls.append(("getversion",))
        return "v242"

    def getnamednumber(self, path):
        self.calls.append(("getnamednumber", path))
        return self.counts.get(path, 0)

    def getnamed(self, path, prop):
        self.calls.append(("getnamed", path, prop))
        return self.properties[(path, prop)]

    def eval(self, script):
        self.calls.append(("eval", script))

    def getv(self, name):
        self.calls.append(("getv", name))
        values = {
            "__template_inventory_paths": [
                "::FDTD",
                "::model",
                "::model::s_params",
                "::model::pillar",
                "::model::substrate",
                "::model::source",
                "::model::monitor",
            ],
            "__template_inventory_types": [
                "FDTD",
                "Structure Group",
                "Analysis Group",
                "Circle",
                "Rectangle",
                "Plane Wave",
                "Power Monitor",
            ],
        }
        return values[name]

    def close(self):
        self.calls.append(("close",))


def test_read_only_adapter_exposes_only_approved_operations():
    module = load_inspector_module()
    adapter = module.ReadOnlyFdtdAdapter(FakeFdtd())

    assert set(adapter.public_operations()) == {
        "load",
        "get_version",
        "get_named_count",
        "get_named",
        "inventory_objects",
        "close",
    }
    for forbidden in (
        "run",
        "runjobs",
        "runanalysis",
        "save",
        "set",
        "setnamed",
        "addrect",
        "delete",
    ):
        assert not hasattr(adapter, forbidden)


def test_adapter_records_only_read_calls():
    module = load_inspector_module()
    fdtd = FakeFdtd()
    adapter = module.ReadOnlyFdtdAdapter(fdtd)

    adapter.load("base_model.fsp")
    adapter.get_version()
    adapter.get_named_count("FDTD")
    adapter.get_named("FDTD", "type")
    adapter.inventory_objects()
    adapter.close()

    names = [call[0] for call in fdtd.calls]
    assert set(names) <= {
        "load",
        "getversion",
        "getnamednumber",
        "getnamed",
        "eval",
        "getv",
        "close",
    }


def test_inventory_script_text_contains_no_forbidden_commands():
    module = load_inspector_module()
    text = module.INVENTORY_SCRIPT.lower()

    for forbidden in (
        "run;",
        "runjobs",
        "runanalysis",
        "save(",
        "set(",
        "setnamed",
        "addrect",
        "addcircle",
        "delete",
    ):
        assert forbidden not in text


import hashlib
import json


def inventory_profile():
    return {
        "profile_version": "0.1",
        "mode": "inventory",
        "template_logical_path": "templates/metasurface/base_model.fsp",
        "known_objects": {
            "fdtd": "FDTD",
            "model": "::model",
            "analysis_group": "::model::s_params",
        },
        "roles_to_discover": [
            "pillar",
            "substrate",
            "source",
            "monitors",
        ],
    }


def test_build_inventory_records_template_environment_and_objects(tmp_path):
    module = load_inspector_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    fdtd = FakeFdtd()

    inventory = module.build_inventory(
        module.ReadOnlyFdtdAdapter(fdtd),
        template=template,
        profile=inventory_profile(),
        logical_path="templates/metasurface/base_model.fsp",
        hostname="win-test",
        python_executable="F:/Lumerical/python.exe",
        code_commit="abc123",
    )

    assert inventory["inventory_version"] == "0.1"
    assert inventory["inventory_only"] is True
    assert inventory["status"] == "inventory"
    assert inventory["template"]["sha256"] == hashlib.sha256(
        b"template"
    ).hexdigest()
    assert inventory["inspector"]["hostname"] == "win-test"
    assert inventory["inspector"]["lumerical_version"] == "v242"
    assert inventory["known_object_checks"] == [
        {
            "role": "fdtd",
            "path": "FDTD",
            "count": 1,
            "status": "pass",
        },
        {
            "role": "model",
            "path": "::model",
            "count": 1,
            "status": "pass",
        },
        {
            "role": "analysis_group",
            "path": "::model::s_params",
            "count": 1,
            "status": "pass",
        },
    ]
    assert any(
        item["path"] == "::model::pillar"
        for item in inventory["objects"]
    )
    assert inventory["errors"] == []
    assert inventory["inventory_fingerprint"]


def test_build_inventory_records_missing_known_object(tmp_path):
    module = load_inspector_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    fdtd = FakeFdtd()
    fdtd.counts["::model::s_params"] = 0

    inventory = module.build_inventory(
        module.ReadOnlyFdtdAdapter(fdtd),
        template=template,
        profile=inventory_profile(),
        logical_path="templates/metasurface/base_model.fsp",
        hostname="win-test",
        python_executable="python.exe",
        code_commit="abc123",
    )

    assert inventory["status"] == "inventory_with_errors"
    assert inventory["errors"][0]["type"] == "object_missing"


def test_build_inventory_records_property_read_errors(tmp_path):
    module = load_inspector_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    fdtd = FakeFdtd()
    del fdtd.properties[("FDTD", "type")]

    inventory = module.build_inventory(
        module.ReadOnlyFdtdAdapter(fdtd),
        template=template,
        profile=inventory_profile(),
        logical_path="templates/metasurface/base_model.fsp",
        hostname="win-test",
        python_executable="python.exe",
        code_commit="abc123",
    )

    assert inventory["status"] == "inventory_with_errors"
    assert any(
        error["type"] == "property_unreadable"
        for error in inventory["errors"]
    )


def test_run_inventory_writes_atomic_json_and_closes(tmp_path):
    module = load_inspector_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(inventory_profile()),
        encoding="utf-8",
    )
    output = tmp_path / "inventory.json"
    fdtd = FakeFdtd()

    result = module.run_inventory(
        template=template,
        profile_path=profile_path,
        output=output,
        fdtd_factory=lambda hide: fdtd,
        hostname="win-test",
        python_executable="python.exe",
        code_commit="abc123",
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert saved["status"] == "inventory"
    assert saved["inspector"]["cleanup_state"] == "closed"
    assert ("close",) in fdtd.calls


def test_run_inventory_writes_failure_json_when_open_fails(tmp_path):
    module = load_inspector_module()
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(inventory_profile()),
        encoding="utf-8",
    )
    output = tmp_path / "inventory.json"

    class BrokenFdtd(FakeFdtd):
        def load(self, path):
            raise RuntimeError("cannot open template")

    result = module.run_inventory(
        template=template,
        profile_path=profile_path,
        output=output,
        fdtd_factory=lambda hide: BrokenFdtd(),
        hostname="win-test",
        python_executable="python.exe",
        code_commit="abc123",
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert result == 1
    assert saved["status"] == "inventory_failed"
    assert saved["errors"][0]["type"] == "template_open_failed"
