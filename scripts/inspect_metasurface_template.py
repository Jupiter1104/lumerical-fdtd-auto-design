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
            try:
                return str(getter())
            except Exception:
                pass
        try:
            self._fdtd.eval("__template_inspector_version=getversion;")
            return str(self._fdtd.getv("__template_inspector_version"))
        except Exception:
            return "unknown"

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


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    return value


def build_inventory(
    adapter: ReadOnlyFdtdAdapter,
    *,
    template: Path,
    profile: dict,
    logical_path: str,
    hostname: str,
    python_executable: str,
    code_commit: str,
) -> dict:
    stat = template.stat()
    errors = []
    known_checks = []

    version = adapter.get_version()
    for role in ("fdtd", "model", "analysis_group"):
        path = profile["known_objects"][role]
        try:
            count = adapter.get_named_count(path)
        except Exception as exc:
            count = None
            errors.append(
                {
                    "type": "property_unreadable",
                    "path": path,
                    "message": str(exc),
                }
            )
        status = "pass" if count == 1 else "fail"
        known_checks.append(
            {
                "role": role,
                "path": path,
                "count": count,
                "status": status,
            }
        )
        if count == 0:
            errors.append(
                {
                    "type": "object_missing",
                    "path": path,
                    "message": f"Required object is missing: {path}",
                }
            )
        elif count not in {None, 1}:
            errors.append(
                {
                    "type": "object_not_unique",
                    "path": path,
                    "message": f"Required object is not unique: {path}",
                }
            )

    for role in ("fdtd", "model", "analysis_group"):
        path = profile["known_objects"][role]
        if next(
            item for item in known_checks if item["role"] == role
        )["count"] != 1:
            continue
        try:
            adapter.get_named(path, "type")
        except Exception as exc:
            errors.append(
                {
                    "type": "property_unreadable",
                    "path": path,
                    "property": "type",
                    "message": str(exc),
                }
            )

    try:
        objects = _jsonable(adapter.inventory_objects())
    except Exception as exc:
        objects = []
        errors.append(
            {
                "type": "inventory_failed",
                "message": str(exc),
            }
        )

    inventory = {
        "inventory_version": INVENTORY_VERSION,
        "inventory_only": True,
        "status": "inventory_with_errors" if errors else "inventory",
        "inventory_fingerprint": "",
        "template": {
            "logical_path": logical_path,
            "absolute_path": str(template.resolve()),
            "sha256": file_sha256(template),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime,
                tz=timezone.utc,
            ).isoformat(),
        },
        "profile": profile,
        "inspector": {
            "checked_at": utc_now(),
            "hostname": hostname,
            "python_executable": python_executable,
            "lumerical_version": version,
            "code_commit": code_commit,
            "hide": True,
            "cleanup_state": "pending",
        },
        "known_object_checks": known_checks,
        "roles_to_discover": list(profile["roles_to_discover"]),
        "objects": objects,
        "errors": errors,
    }
    inventory["inventory_fingerprint"] = inventory_fingerprint(inventory)
    return inventory


def import_lumapi():
    candidate = (
        Path(sys.executable).resolve().parent.parent / "api" / "python"
    )
    if candidate.is_dir() and str(candidate) not in sys.path:
        sys.path.append(str(candidate))
    return importlib.import_module("lumapi")


def _failure_inventory(
    *,
    template: Path,
    error_type: str,
    message: str,
    hostname: str,
    python_executable: str,
    code_commit: str,
    cleanup_state: str,
) -> dict:
    inventory = {
        "inventory_version": INVENTORY_VERSION,
        "inventory_only": True,
        "status": "inventory_failed",
        "inventory_fingerprint": "",
        "template": {
            "logical_path": "templates/metasurface/base_model.fsp",
            "absolute_path": str(template.resolve()),
        },
        "inspector": {
            "checked_at": utc_now(),
            "hostname": hostname,
            "python_executable": python_executable,
            "lumerical_version": "unknown",
            "code_commit": code_commit,
            "hide": True,
            "cleanup_state": cleanup_state,
        },
        "known_object_checks": [],
        "roles_to_discover": [],
        "objects": [],
        "errors": [{"type": error_type, "message": message}],
    }
    inventory["inventory_fingerprint"] = inventory_fingerprint(inventory)
    return inventory


def run_inventory(
    *,
    template: Path,
    profile_path: Path,
    output: Path,
    fdtd_factory,
    hostname: str,
    python_executable: str,
    code_commit: str,
) -> int:
    if not template.is_file():
        atomic_write_json(
            output,
            _failure_inventory(
                template=template,
                error_type="template_not_found",
                message=f"Template not found: {template}",
                hostname=hostname,
                python_executable=python_executable,
                code_commit=code_commit,
                cleanup_state="not_started",
            ),
        )
        return 1

    try:
        profile = validate_inventory_profile(
            json.loads(profile_path.read_text(encoding="utf-8"))
        )
    except Exception as exc:
        atomic_write_json(
            output,
            _failure_inventory(
                template=template,
                error_type="profile_validation_error",
                message=str(exc),
                hostname=hostname,
                python_executable=python_executable,
                code_commit=code_commit,
                cleanup_state="not_started",
            ),
        )
        return 1

    fdtd = None
    adapter = None
    inventory = None
    try:
        fdtd = fdtd_factory(True)
        adapter = ReadOnlyFdtdAdapter(fdtd)
        adapter.load(str(template.resolve()))
        inventory = build_inventory(
            adapter,
            template=template,
            profile=profile,
            logical_path=profile["template_logical_path"],
            hostname=hostname,
            python_executable=python_executable,
            code_commit=code_commit,
        )
    except Exception as exc:
        inventory = _failure_inventory(
            template=template,
            error_type="template_open_failed",
            message=str(exc),
            hostname=hostname,
            python_executable=python_executable,
            code_commit=code_commit,
            cleanup_state="pending" if fdtd is not None else "not_started",
        )
    finally:
        if adapter is not None:
            try:
                adapter.close()
                inventory["inspector"]["cleanup_state"] = "closed"
            except Exception as exc:
                inventory["inspector"]["cleanup_state"] = "close_failed"
                inventory.setdefault("warnings", []).append(
                    {"type": "cleanup_failed", "message": str(exc)}
                )
        inventory["inventory_fingerprint"] = inventory_fingerprint(inventory)
        atomic_write_json(output, inventory)

    return 0 if inventory["status"] == "inventory" else 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only inventory for the metasurface FDTD template."
    )
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.inventory:
        print("Only --inventory is available in Stage A.", file=sys.stderr)
        return 2
    lumapi = import_lumapi()
    code = run_inventory(
        template=Path(args.template),
        profile_path=Path(args.profile),
        output=Path(args.output),
        fdtd_factory=lambda hide: lumapi.FDTD(hide=hide),
        hostname=socket.gethostname(),
        python_executable=sys.executable,
        code_commit=current_commit(),
    )
    print(f"Inventory: {args.output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
