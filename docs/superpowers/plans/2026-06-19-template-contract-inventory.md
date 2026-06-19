# Template Contract Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify the cross-platform template-contract primitives plus a Windows-only, read-only Lumerical inventory tool, then produce the real `base_model.inventory.json` required to write the strict contract/real-run implementation plan.

**Architecture:** Add a pure-Python `src/template_contract.py` module for stable JSON, hashing, atomic JSON and inventory-profile validation. Add a Windows Lumerical inspector whose lumapi access is isolated behind a read-only adapter and whose first supported mode is inventory only. Stop after the real Windows inventory is collected; do not invent strict object paths, generate a verified contract, change the RPC real guard, or run a simulation in this plan.

**Tech Stack:** Python 3.9-compatible standard library, raw Lumerical v242 `lumapi`, PowerShell/CMD wrapper, pytest, existing Windows Git pull workflow.

---

## Scope Guard

- This is Stage A only: infrastructure plus real Windows inventory.
- Do not create `template-inspection-profile.json` in this plan.
- Do not generate `status="verified"` contracts.
- Do not modify `/jobs/start`, MCP real approval, `JobStore`, or `NativeSweepRunner`.
- Do not run `run`, `runjobs`, `runanalysis`, `save`, `set`, `setnamed`, `add*`, or `delete`.
- Do not modify `base_model.fsp`.
- Do not launch a real sweep.
- The user has approved one read-only FDTD template inspection. That approval does not authorize real solving.
- After Task 8, stop and report the inventory. A new design-derived Stage B plan must use the actual inventory paths.

## File Map

- Create `src/template_contract.py`
  - Stable JSON, SHA-256 helpers, atomic JSON writes, inventory profile validation, runtime metadata and inventory fingerprinting.
- Create `tests/test_template_contract.py`
  - Pure helper and schema tests.
- Create `templates/metasurface/template-inventory-profile.json`
  - Git-managed profile containing only currently known paths and roles to discover.
- Modify `.gitignore`
  - Ignore generated inventory and contract JSON while keeping profile JSON tracked.
- Create `scripts/inspect_metasurface_template.py`
  - Windows-only CLI, lazy lumapi import, read-only adapter, inventory orchestration and failure diagnostics.
- Create `tests/test_template_inspector.py`
  - Fake-lumapi and forbidden-call tests.
- Create `scripts/windows/inspect_metasurface_template.bat`
  - Fixed Windows entry point using the v242 Python executable.
- Modify `templates/metasurface/README.md`
  - Document install → inventory and the no-solve guarantee.
- Modify `docs/WINDOWS_RUNBOOK.md`
  - Document exact Windows commands and expected inventory artifact.
- Modify `SOP.md`
  - Add the Stage A stop gate.
- Modify `DEV_LOG.md`
  - Record offline verification, Windows sync and inventory result.

---

## Task 1: Add template-contract pure helpers

**Files:**
- Create: `src/template_contract.py`
- Create: `tests/test_template_contract.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_template_contract.py`:

```python
import hashlib
import json

import pytest

from src.template_contract import (
    atomic_write_json,
    file_sha256,
    inventory_fingerprint,
    stable_json,
    validate_inventory_profile,
)


def valid_inventory_profile():
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


def test_stable_json_is_deterministic_and_rejects_nan():
    assert stable_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    with pytest.raises(ValueError):
        stable_json({"value": float("nan")})


def test_file_sha256_reads_file_bytes(tmp_path):
    path = tmp_path / "base_model.fsp"
    path.write_bytes(b"template")

    assert file_sha256(path) == hashlib.sha256(b"template").hexdigest()


def test_atomic_write_json_replaces_target(tmp_path):
    path = tmp_path / "inventory.json"
    atomic_write_json(path, {"ok": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
    assert not path.with_suffix(".json.tmp").exists()


def test_inventory_profile_accepts_only_exact_schema():
    profile = valid_inventory_profile()

    assert validate_inventory_profile(profile) == profile

    profile["unknown"] = True
    with pytest.raises(ValueError, match="unknown"):
        validate_inventory_profile(profile)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda profile: profile.update({"mode": "contract"}),
        lambda profile: profile.update({"profile_version": "1.0"}),
        lambda profile: profile["known_objects"].pop("fdtd"),
        lambda profile: profile.update({"roles_to_discover": []}),
        lambda profile: profile["roles_to_discover"].append("source"),
    ],
)
def test_inventory_profile_rejects_invalid_values(mutation):
    profile = valid_inventory_profile()
    mutation(profile)

    with pytest.raises(ValueError):
        validate_inventory_profile(profile)


def test_inventory_fingerprint_excludes_its_own_field():
    inventory = {
        "inventory_version": "0.1",
        "inventory_fingerprint": "old",
        "template": {"sha256": "abc"},
        "objects": [],
    }

    first = inventory_fingerprint(inventory)
    inventory["inventory_fingerprint"] = "different"

    assert inventory_fingerprint(inventory) == first
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_contract.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'src.template_contract'`.

- [ ] **Step 3: Implement the minimal pure module**

Create `src/template_contract.py`:

```python
"""Cross-platform helpers for FDTD template inventory and contracts."""

import hashlib
import json
import os
from pathlib import Path


INVENTORY_PROFILE_VERSION = "0.1"
INVENTORY_VERSION = "0.1"
INVENTORY_PROFILE_KEYS = {
    "profile_version",
    "mode",
    "template_logical_path",
    "known_objects",
    "roles_to_discover",
}
KNOWN_OBJECT_ROLES = {"fdtd", "model", "analysis_group"}
DISCOVERY_ROLES = {"pillar", "substrate", "source", "monitors"}


def stable_json(value: dict) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path, value: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(target))


def _require_exact_keys(value: dict, expected: set, label: str) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown:
        raise ValueError(f"{label} contains unknown keys: {sorted(unknown)}")
    if missing:
        raise ValueError(f"{label} is missing keys: {sorted(missing)}")


def validate_inventory_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("Inventory profile must be an object.")
    _require_exact_keys(
        profile,
        INVENTORY_PROFILE_KEYS,
        "Inventory profile",
    )
    if profile["profile_version"] != INVENTORY_PROFILE_VERSION:
        raise ValueError("Unsupported inventory profile version.")
    if profile["mode"] != "inventory":
        raise ValueError("Inventory profile mode must be inventory.")
    logical_path = profile["template_logical_path"]
    if (
        not isinstance(logical_path, str)
        or logical_path != "templates/metasurface/base_model.fsp"
    ):
        raise ValueError("Inventory template path must be the controlled path.")

    known = profile["known_objects"]
    if not isinstance(known, dict):
        raise ValueError("known_objects must be an object.")
    _require_exact_keys(known, KNOWN_OBJECT_ROLES, "known_objects")
    if known != {
        "fdtd": "FDTD",
        "model": "::model",
        "analysis_group": "::model::s_params",
    }:
        raise ValueError("known_objects does not match the controlled baseline.")

    roles = profile["roles_to_discover"]
    if (
        not isinstance(roles, list)
        or set(roles) != DISCOVERY_ROLES
        or len(roles) != len(DISCOVERY_ROLES)
    ):
        raise ValueError("roles_to_discover must list each required role once.")
    return profile


def inventory_fingerprint(inventory: dict) -> str:
    payload = dict(inventory)
    payload.pop("inventory_fingerprint", None)
    return hashlib.sha256(
        stable_json(payload).encode("utf-8")
    ).hexdigest()
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/template_contract.py tests/test_template_contract.py
git commit -m "feat: add template inventory helpers"
```

---

## Task 2: Add the controlled inventory profile and runtime ignores

**Files:**
- Create: `templates/metasurface/template-inventory-profile.json`
- Modify: `.gitignore`
- Modify: `tests/test_template_contract.py`

- [ ] **Step 1: Write failing repository-contract tests**

Append to `tests/test_template_contract.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_repository_inventory_profile_matches_schema():
    profile_path = (
        ROOT
        / "templates"
        / "metasurface"
        / "template-inventory-profile.json"
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    assert validate_inventory_profile(profile) == profile


def test_runtime_inventory_and_contract_are_ignored():
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "templates/metasurface/base_model.inventory.json" in ignore_text
    assert "templates/metasurface/base_model.contract.json" in ignore_text
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_repository_inventory_profile_matches_schema \
  tests/test_template_contract.py::test_runtime_inventory_and_contract_are_ignored \
  -q
```

Expected: failures because the profile and explicit ignore rules do not exist.

- [ ] **Step 3: Add the inventory profile**

Create `templates/metasurface/template-inventory-profile.json`:

```json
{
  "profile_version": "0.1",
  "mode": "inventory",
  "template_logical_path": "templates/metasurface/base_model.fsp",
  "known_objects": {
    "fdtd": "FDTD",
    "model": "::model",
    "analysis_group": "::model::s_params"
  },
  "roles_to_discover": [
    "pillar",
    "substrate",
    "source",
    "monitors"
  ]
}
```

- [ ] **Step 4: Add explicit runtime ignore rules**

Append to `.gitignore`:

```gitignore
# Metasurface template inspection runtime artifacts
templates/metasurface/base_model.inventory.json
templates/metasurface/base_model.contract.json
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add .gitignore templates/metasurface/template-inventory-profile.json tests/test_template_contract.py
git commit -m "chore: add template inventory profile"
```

---

## Task 3: Add a read-only Lumerical adapter

**Files:**
- Create: `scripts/inspect_metasurface_template.py`
- Create: `tests/test_template_inspector.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_template_inspector.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_inspector.py -q
```

Expected: collection fails because the inspector script does not exist.

- [ ] **Step 3: Implement the adapter and fixed inventory script**

Create `scripts/inspect_metasurface_template.py` with this initial content:

```python
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
```

Do not yet implement CLI execution in this task.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_inspector.py -q
```

Expected: all three adapter tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add scripts/inspect_metasurface_template.py tests/test_template_inspector.py
git commit -m "feat: add read-only template inspector adapter"
```

---

## Task 4: Build inventory records with fail-closed diagnostics

**Files:**
- Modify: `scripts/inspect_metasurface_template.py`
- Modify: `tests/test_template_inspector.py`

- [ ] **Step 1: Add failing inventory-builder tests**

Append to `tests/test_template_inspector.py`:

```python
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
```

- [ ] **Step 2: Run new tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_inspector.py -q
```

Expected: failures because `build_inventory` does not exist.

- [ ] **Step 3: Implement inventory building**

Append to `scripts/inspect_metasurface_template.py`:

```python
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
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_inspector.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add scripts/inspect_metasurface_template.py tests/test_template_inspector.py
git commit -m "feat: build template inventory records"
```

---

## Task 5: Add the Windows inventory CLI and failure artifact

**Files:**
- Modify: `scripts/inspect_metasurface_template.py`
- Modify: `tests/test_template_inspector.py`

- [ ] **Step 1: Add failing CLI tests**

Append to `tests/test_template_inspector.py`:

```python
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
```

- [ ] **Step 2: Run new tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_inspector.py -q
```

Expected: failures because `run_inventory` does not exist.

- [ ] **Step 3: Implement `run_inventory` and CLI**

Append to `scripts/inspect_metasurface_template.py`:

```python
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
```

- [ ] **Step 4: Run focused tests and CLI help**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_inspector.py -q
.venv/bin/python scripts/inspect_metasurface_template.py --help
```

Expected: tests pass; help exits `0` without importing lumapi.

- [ ] **Step 5: Commit Task 5**

```bash
git add scripts/inspect_metasurface_template.py tests/test_template_inspector.py
git commit -m "feat: add template inventory cli"
```

---

## Task 6: Add the Windows batch entry point

**Files:**
- Create: `scripts/windows/inspect_metasurface_template.bat`
- Create: `tests/test_template_inspector_windows_entry.py`

- [ ] **Step 1: Write a failing batch contract test**

Create `tests/test_template_inspector_windows_entry.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_windows_inventory_entry_uses_lumerical_python_and_read_only_mode():
    text = (
        ROOT
        / "scripts"
        / "windows"
        / "inspect_metasurface_template.bat"
    ).read_text(encoding="utf-8")

    assert r"F:\Program Files\Lumerical\v242\python\python.exe" in text
    assert "scripts\\inspect_metasurface_template.py" in text
    assert "--inventory" in text
    assert "base_model.fsp" in text
    assert "base_model.inventory.json" in text
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_inspector_windows_entry.py -q
```

Expected: failure because the batch file does not exist.

- [ ] **Step 3: Add the batch entry point**

Create `scripts/windows/inspect_metasurface_template.bat`:

```bat
@echo off
setlocal
cd /d "%~dp0\..\.."

set "FDTD_PYTHON=F:\Program Files\Lumerical\v242\python\python.exe"
set "TEMPLATE=templates\metasurface\base_model.fsp"
set "PROFILE=templates\metasurface\template-inventory-profile.json"
set "OUTPUT=templates\metasurface\base_model.inventory.json"

if not exist "%FDTD_PYTHON%" (
  echo [ERROR] Lumerical Python not found: %FDTD_PYTHON%
  pause
  exit /b 1
)

"%FDTD_PYTHON%" scripts\inspect_metasurface_template.py --inventory ^
  --template "%TEMPLATE%" ^
  --profile "%PROFILE%" ^
  --output "%OUTPUT%"

set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
```

- [ ] **Step 4: Run the batch contract test**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_inspector_windows_entry.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit Task 6**

```bash
git add scripts/windows/inspect_metasurface_template.bat tests/test_template_inspector_windows_entry.py
git commit -m "chore: add windows template inventory entry"
```

---

## Task 7: Document the Stage A workflow and stop gate

**Files:**
- Modify: `templates/metasurface/README.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Modify: `SOP.md`
- Modify: `README.md`
- Modify: `DEV_LOG.md`

- [ ] **Step 1: Update the template README**

Add:

```markdown
## Read-only inventory

After installing the template, run:

```cmd
scripts\windows\inspect_metasurface_template.bat
```

This opens the template with `hide=True` using Lumerical v242 Python and writes
`base_model.inventory.json`. It must not solve, modify, or save the `.fsp`.
Inventory is discovery evidence only and cannot authorize a real run.
```

- [ ] **Step 2: Update the Windows runbook**

Add the exact sequence:

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
scripts\windows\inspect_metasurface_template.bat
type templates\metasurface\base_model.inventory.json
```

Document success criteria:

- `inventory_only=true`
- `status=inventory`
- Lumerical version is present
- known objects each have `count=1`
- object list is non-empty
- cleanup state is `closed`
- no real job is created

- [ ] **Step 3: Update SOP and README**

In `SOP.md`, add:

```text
install -> inventory -> stop -> review inventory -> commit strict profile
```

Explicitly state that Stage A ends after inventory review.

In `README.md`, change the current next step to:

```text
实现并运行 Windows 只读 inventory；根据真实对象路径编写 strict profile。
```

- [ ] **Step 4: Add a DEV_LOG entry**

Append:

```markdown
## 2026-06-19 - Template Contract Stage A

- 目标：建立纯 Python 指纹工具和 Windows 只读模板 inventory。
- 安全边界：只读打开模板；不求解、不修改、不保存；inventory 不能批准 real。
- 实现：
  - 新增 `src/template_contract.py` 的稳定 JSON、SHA-256、原子写入和 inventory profile 校验。
  - 新增受控 inventory profile、只读 Lumerical adapter、inventory CLI 和 Windows `.bat` 入口。
  - runtime inventory/contract JSON 被 Git 忽略。
- Windows inventory：尚未执行；等待离线验证和 Windows 同步。
```

- [ ] **Step 5: Run documentation scans**

Run:

```bash
rg -n "inventory|只读|不能批准 real|不求解|strict profile" \
  README.md SOP.md docs/WINDOWS_RUNBOOK.md \
  templates/metasurface/README.md DEV_LOG.md
```

Expected: all documents agree on the Stage A stop gate.

- [ ] **Step 6: Commit Task 7**

```bash
git add README.md SOP.md DEV_LOG.md docs/WINDOWS_RUNBOOK.md templates/metasurface/README.md
git commit -m "docs: document template inventory workflow"
```

---

## Task 8: Offline verification and push

**Files:**
- Modify only if verification finds a Stage A defect.

- [ ] **Step 1: Run compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exit `0`.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. Copy the final summary line into `DEV_LOG.md`.

- [ ] **Step 3: Scan for forbidden inspector operations**

Run:

```bash
! rg -n "\\.(run|runjobs|runanalysis|save|set|setnamed|delete)\\(" \
  scripts/inspect_metasurface_template.py
```

Expected: no matches.

Run:

```bash
! rg -n "\\b(addrect|addcircle|addfdtd|addmesh|addplane|addpower)\\b" \
  scripts/inspect_metasurface_template.py
```

Expected: no matches.

- [ ] **Step 4: Verify no runtime artifacts or FSP files are tracked**

Run:

```bash
git ls-files \
  "templates/metasurface/base_model.inventory.json" \
  "templates/metasurface/base_model.contract.json" \
  "*.fsp"
```

Expected: no output.

- [ ] **Step 5: Record final offline verification**

Update the Stage A `DEV_LOG.md` entry with the exact pytest result, then:

```bash
git add DEV_LOG.md
git commit -m "docs: record template inventory verification"
```

- [ ] **Step 6: Push Stage A**

Run:

```bash
git push origin main
```

Expected: remote `main` advances to the final Stage A commit.

---

## Task 9: Windows sync and approved read-only inventory

**Files:**
- Runtime output only: `templates/metasurface/base_model.inventory.json`
- Modify after collection: `DEV_LOG.md`

This task uses the user's explicit approval to open the template read-only. It does not authorize a solve.

- [ ] **Step 1: Synchronize the Windows clone**

On Windows, from a local CMD or the already approved Windows control path:

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
git status --short
git pull --ff-only
git rev-parse --short HEAD
```

Expected:

- worktree clean before pull;
- HEAD equals pushed Stage A HEAD.

- [ ] **Step 2: Run the inventory once**

Run locally on Windows:

```cmd
scripts\windows\inspect_metasurface_template.bat
```

Expected:

- FDTD may open hidden and briefly consume a license;
- no simulation is run;
- command exits `0`;
- `templates\metasurface\base_model.inventory.json` exists.

- [ ] **Step 3: Read and verify the inventory**

Read the JSON and verify:

```text
inventory_only == true
status == "inventory"
template.logical_path == "templates/metasurface/base_model.fsp"
template.sha256 is a 64-character SHA-256
inspector.lumerical_version is not "unknown"
inspector.cleanup_state == "closed"
known_object_checks all have count == 1 and status == "pass"
objects is non-empty
errors is empty
```

If any condition fails, stop. Do not create a strict profile by guessing.

- [ ] **Step 4: Collect the runtime inventory for review**

Transfer or read the inventory through an approved read-only channel. Do not commit the runtime file.

Produce a review summary containing:

- template SHA-256;
- inventory fingerprint;
- Lumerical version;
- code commit;
- known object checks;
- full object paths and types;
- candidate paths for pillar, substrate, source and monitors;
- cleanup state;
- errors and warnings.

- [ ] **Step 5: Update DEV_LOG after inventory**

Record:

- Windows HEAD;
- inventory status;
- template SHA;
- inventory fingerprint;
- Lumerical version;
- cleanup state;
- whether the four roles can be bound unambiguously.

Commit and push only the documentation update:

```bash
git add DEV_LOG.md
git commit -m "docs: record windows template inventory"
git push origin main
```

- [ ] **Step 6: Stop at the mandatory checkpoint**

Do not implement the strict profile, contract generation, RPC guard, or real run yet.

Return the inventory review to the user and Codex. The next plan must use the exact discovered object paths and v242 property names to cover:

1. strict contract profile;
2. verified contract generation;
3. MCP four-fingerprint approval;
4. Windows RPC preflight;
5. manifest audit fields;
6. separate real 2×2 approval and execution.
