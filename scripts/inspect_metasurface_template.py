"""Read-only Windows inspector for the controlled metasurface template."""

import argparse
import importlib
import json
import os
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.template_contract import (
    INVENTORY_VERSION,
    atomic_write_json,
    file_sha256,
    inventory_fingerprint,
    validate_inventory_profile,
)


DEFAULT_TEMPLATE = ROOT / "templates" / "metasurface" / "base_model.fsp"
DEFAULT_PROFILE = (
    ROOT
    / "templates"
    / "metasurface"
    / "template-inventory-profile.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "templates"
    / "metasurface"
    / "base_model.inventory.json"
)

# This script must remain read-only. It enumerates direct objects at root and
# inside ::model. The controlled metasurface template keeps all sweep-relevant
# structures, sources and monitors in one of those two scopes.
INVENTORY_SCRIPT = """
__template_inventory_paths = cell(0);
__template_inventory_types = cell(0);
__template_inventory_count = 0;

groupscope("::");
selectall;
__root_count = getnumber;
for (__i = 1:__root_count) {
    __template_inventory_count = __template_inventory_count + 1;
    __name = get("name", __i);
    __template_inventory_paths{__template_inventory_count} = "::" + __name;
    __template_inventory_types{__template_inventory_count} = get("type", __i);
}

groupscope("::model");
selectall;
__model_count = getnumber;
for (__i = 1:__model_count) {
    __template_inventory_count = __template_inventory_count + 1;
    __name = get("name", __i);
    __template_inventory_paths{__template_inventory_count} = "::model::" + __name;
    __template_inventory_types{__template_inventory_count} = get("type", __i);
}

groupscope("::");
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


class ReadOnlyFdtdAdapter:
    def __init__(self, fdtd):
        self._fdtd = fdtd

    @staticmethod
    def public_operations():
        return (
            "load",
            "get_version",
            "get_named_count",
            "get_named",
            "inventory_objects",
            "close",
        )

    def load(self, path: str) -> None:
        self._fdtd.load(path)

    def get_version(self) -> str:
        getter = getattr(self._fdtd, "getversion", None)
        if callable(getter):
            return str(getter())
        self._fdtd.eval("__template_inspector_version=getversion;")
        return str(self._fdtd.getv("__template_inspector_version"))

    def get_named_count(self, path: str) -> int:
        return int(self._fdtd.getnamednumber(path))

    def get_named(self, path: str, prop: str):
        return self._fdtd.getnamed(path, prop)

    def inventory_objects(self):
        self._fdtd.eval(INVENTORY_SCRIPT)
        paths = self._fdtd.getv("__template_inventory_paths")
        types = self._fdtd.getv("__template_inventory_types")
        path_values = paths.tolist() if hasattr(paths, "tolist") else list(paths)
        type_values = types.tolist() if hasattr(types, "tolist") else list(types)
        return [
            {"path": str(path), "type": str(object_type)}
            for path, object_type in zip(path_values, type_values)
        ]

    def close(self) -> None:
        self._fdtd.close()


def import_lumapi():
    candidate = (
        Path(sys.executable).resolve().parent.parent / "api" / "python"
    )
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.append(str(candidate))
    return importlib.import_module("lumapi")
