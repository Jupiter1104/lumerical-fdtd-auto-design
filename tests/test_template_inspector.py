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
