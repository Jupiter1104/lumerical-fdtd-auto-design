"""Targeted read-only probe for the controlled metasurface template (Stage B0)."""

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

from src.template_probe import (
    PROBE_VERSION,
    atomic_write_json,
    file_sha256,
    probe_fingerprint,
    probe_installation_identity,
    validate_probe_installation,
)


DEFAULT_TEMPLATE = ROOT / "templates" / "metasurface" / "base_model.fsp"
DEFAULT_OUTPUT = (
    ROOT / "templates" / "metasurface" / "base_model.probe.json"
)

# Inventory fingerprint from Stage A (fixed, not recomputed)
STAGE_A_INVENTORY_FINGERPRINT = (
    "d3b37899e2b753c9fb2b93981f9c3026d0f69243858ac8ea7abb918379f3d1f2"
)


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


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return value


class ProbeAdapter:
    """Targeted read-only probe adapter for v242 lumapi."""

    def __init__(self, fdtd):
        self._fdtd = fdtd

    @staticmethod
    def public_operations():
        return (
            "load", "get_version", "get_named_count", "get_named",
            "enumerate_scopes", "enumerate_objects_recursive",
            "probe_identically_named_objects",
            "probe_structure_candidates",
            "probe_fdtd_configuration", "probe_mesh_configuration",
            "probe_model_parameters", "probe_source_strategy",
            "probe_monitors", "probe_analysis_group",
            "close",
        )

    # --- Basic read-only operations ---

    def load(self, path: str) -> None:
        self._fdtd.load(path)

    def get_version(self) -> str:
        getter = getattr(self._fdtd, "getversion", None)
        if callable(getter):
            try:
                return str(getter())
            except Exception:
                pass
        try:
            self._fdtd.eval("__probe_version_var=getversion;")
            return str(self._fdtd.getv("__probe_version_var"))
        except Exception:
            return "unknown"

    def get_named_count(self, path: str) -> int:
        return int(self._fdtd.getnamednumber(path))

    def get_named(self, path: str, prop: str):
        return self._fdtd.getnamed(path, prop)

    def close(self) -> None:
        self._fdtd.close()

    # --- Scope & object enumeration ---

    def enumerate_scopes(self, scopes: list) -> dict:
        """Count objects in each scope without full property reads."""
        result = {}
        for scope in scopes:
            try:
                self._fdtd.groupscope(scope)
                self._fdtd.selectall()
                count = int(self._fdtd.getnumber())
                result[scope] = {"object_count": count, "reachable": True}
            except Exception as exc:
                result[scope] = {
                    "object_count": 0,
                    "reachable": False,
                    "error": str(exc),
                }
        self._fdtd.groupscope("::")
        return result

    def enumerate_objects_recursive(self, scopes: list) -> list:
        """Enumerate objects in listed scopes with type, scope, and name."""
        objects = []
        for scope in scopes:
            try:
                self._fdtd.groupscope(scope)
                self._fdtd.selectall()
                count = int(self._fdtd.getnumber())
                for i in range(1, count + 1):
                    name = str(self._fdtd.get("name", i))
                    obj_type = str(self._fdtd.get("type", i))
                    if scope == "::":
                        path = "::" + name
                    else:
                        path = scope + "::" + name
                    objects.append({
                        "path": path,
                        "type": obj_type,
                        "scope": scope,
                        "name": name,
                    })
            except Exception:
                pass
        self._fdtd.groupscope("::")
        return objects

    def probe_identically_named_objects(self) -> list:
        """Find objects with same name in different scopes.

        Reads a stable set of properties from each and records
        evidence-based conclusions.
        """
        objects = self.enumerate_objects_recursive(["::", "::model"])
        by_name = {}
        for obj in objects:
            by_name.setdefault(obj["name"], []).append(obj)

        evidence = []
        stable_properties = [
            "type", "material", "x", "y", "z",
            "x span", "y span", "z span",
        ]
        for name, entries in by_name.items():
            if len(entries) < 2:
                continue
            comparison = {
                "name": name,
                "paths": [e["path"] for e in entries],
                "property_comparison": {},
            }
            all_match = True
            for prop in stable_properties:
                values = {}
                for entry in entries:
                    try:
                        values[entry["path"]] = _jsonable(
                            self._fdtd.getnamed(entry["path"], prop)
                        )
                    except Exception as exc:
                        values[entry["path"]] = {"error": str(exc)}
                        all_match = False
                comparison["property_comparison"][prop] = values
                unique = set(
                    json.dumps(v, sort_keys=True, default=str)
                    for v in values.values()
                )
                if len(unique) > 1:
                    all_match = False
            comparison["conclusion"] = (
                "possible_alias_or_identical"
                if all_match
                else "independent_objects"
            )
            evidence.append(comparison)
        return evidence


def import_lumapi():
    candidate = (
        Path(sys.executable).resolve().parent.parent / "api" / "python"
    )
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.append(str(candidate))
    return importlib.import_module("lumapi")
