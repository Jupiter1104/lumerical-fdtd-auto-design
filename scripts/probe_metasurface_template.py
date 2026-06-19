"""Targeted read-only probe for the controlled metasurface template (Stage B0)."""

import argparse
import hashlib
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
            unreadable_paths = set()
            different_readable_value = False
            for prop in stable_properties:
                values = {}
                readable_values = {}
                for entry in entries:
                    try:
                        value = _jsonable(
                            self._fdtd.getnamed(entry["path"], prop)
                        )
                        values[entry["path"]] = {
                            "status": "readable",
                            "value": value,
                        }
                        readable_values[entry["path"]] = value
                    except Exception as exc:
                        unreadable_paths.add(entry["path"])
                        values[entry["path"]] = {
                            "status": "unreadable",
                            "error": str(exc),
                        }
                comparison["property_comparison"][prop] = values
                if len(readable_values) == len(entries):
                    from src.template_probe import stable_json as _sj
                    encoded = {
                        _sj({"value": v})
                        for v in readable_values.values()
                    }
                    if len(encoded) > 1:
                        different_readable_value = True
            comparison["unreadable_paths"] = sorted(unreadable_paths)
            if unreadable_paths:
                comparison["conclusion"] = "unresolved_scope_alias"
            elif different_readable_value:
                comparison["conclusion"] = "independent_objects"
            else:
                comparison["conclusion"] = "possible_alias_or_identical"
            evidence.append(comparison)
        return evidence


    # --- Structure & material candidates ---

    def probe_structure_candidates(self, role_paths: dict) -> dict:
        """Read pillar and substrate candidate properties.

        role_paths: {"pillar": ["::pillar", ...], "substrate": [...]}
        """
        PROPERTY_MAP = {
            "pillar": [
                "type", "name", "material",
                "x", "y", "z",
                "x span", "y span", "z span",
                "radius",
            ],
            "substrate": [
                "type", "name", "material",
                "x", "y", "z",
                "x span", "y span", "z span",
            ],
        }
        results = {}
        for role, paths in role_paths.items():
            candidates = []
            has_unreadable = False
            for path in paths:
                try:
                    count = self._fdtd.getnamednumber(path)
                except Exception:
                    count = 0
                if count == 0:
                    continue
                candidate = {"path": path, "exists": True, "properties": {}}
                for prop in PROPERTY_MAP.get(role, []):
                    try:
                        candidate["properties"][prop] = _jsonable(
                            self._fdtd.getnamed(path, prop)
                        )
                    except Exception as exc:
                        candidate["properties"][prop] = {
                            "status": "unreadable",
                            "error": str(exc),
                        }
                        has_unreadable = True
                candidates.append(candidate)
            results[role] = {
                "candidate_count": len(candidates),
                "candidates": candidates,
                "has_unreadable": has_unreadable,
            }
        return results

    # --- FDTD configuration ---

    def probe_fdtd_configuration(self, fdtd_path: str = "FDTD") -> dict:
        """Read FDTD solver configuration without modifying."""
        properties = {
            "type": "type",
            "dimension": "dimension",
            "express_mode": "express mode",
            "simulation_time": "simulation time",
        }
        result = {"path": fdtd_path, "properties": {}}
        for key, prop_name in properties.items():
            try:
                result["properties"][key] = _jsonable(
                    self._fdtd.getnamed(fdtd_path, prop_name)
                )
            except Exception as exc:
                result["properties"][key] = {
                    "status": "unreadable", "error": str(exc),
                }
        # Evidence-based CPU/express_mode check
        em = result["properties"].get("express_mode", {})
        if isinstance(em, (int, float)):
            result["cpu_express_mode_evidence"] = {
                "express_mode_value": int(em),
                "cpu_confirmed": em == 0,
                "note": (
                    "express_mode=0 confirms CPU resource"
                    if em == 0
                    else f"express_mode={int(em)} unexpected for CPU (0)"
                ),
            }
        else:
            result["cpu_express_mode_evidence"] = {
                "express_mode_value": None,
                "cpu_confirmed": False,
                "note": "express mode could not be read; CPU resource unconfirmed",
            }
        return result

    # --- Mesh configuration ---

    def probe_mesh_configuration(self, mesh_paths=None) -> dict:
        """Read mesh accuracy from candidate mesh objects."""
        if mesh_paths is None:
            mesh_paths = ["::mesh", "::model::mesh"]
        result = {"meshes": []}
        for path in mesh_paths:
            mesh_entry = {"path": path, "exists": False, "properties": {}}
            try:
                count = self._fdtd.getnamednumber(path)
            except Exception:
                count = 0
            if count == 0:
                result["meshes"].append(mesh_entry)
                continue
            mesh_entry["exists"] = True
            for prop in ["mesh accuracy", "type"]:
                try:
                    mesh_entry["properties"][prop] = _jsonable(
                        self._fdtd.getnamed(path, prop)
                    )
                except Exception as exc:
                    mesh_entry["properties"][prop] = {
                        "status": "unreadable", "error": str(exc),
                    }
            result["meshes"].append(mesh_entry)
        return result

    # --- Model parameters ---

    def probe_model_parameters(self, model_path: str = "::model") -> dict:
        """Read sweep-critical model parameters: ratio, height, period."""
        params = {}
        for param_name in ("ratio", "height", "period"):
            try:
                value = self._fdtd.getnamed(model_path, param_name)
                params[param_name] = {
                    "name": param_name,
                    "value": _jsonable(value),
                    "type": type(value).__name__,
                    "read_method": "getnamed",
                    "path": model_path,
                }
            except Exception as exc:
                params[param_name] = {
                    "name": param_name,
                    "status": "unreadable",
                    "error": str(exc),
                    "read_method": "getnamed",
                    "path": model_path,
                }
        return params

    # --- Source strategy ---

    def _read_script_text_safely(self, path: str, script_property: str) -> dict:
        """Read script text from analysis group, return hash/size only."""
        try:
            text = str(self._fdtd.getnamed(path, script_property))
            byte_count = len(text.encode("utf-8"))
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return {
                "property": script_property,
                "path": path,
                "readable": True,
                "sha256": sha,
                "byte_count": byte_count,
                "summary": _summarize_script(text),
            }
        except Exception as exc:
            return {
                "property": script_property,
                "path": path,
                "readable": False,
                "error": str(exc),
            }

    def probe_source_strategy(self) -> dict:
        """Classify source configuration strategy.

        Returns dict with classification and evidence.
        Classification: explicit_object | analysis_group_setup |
                        global_source | unresolved
        """
        # 1. Search all scopes for source-type objects
        source_objects = []
        source_keywords = ("source", "plane", "gaussian", "mode", "dipole")
        for scope in ["::", "::model", "::model::s_params"]:
            try:
                self._fdtd.groupscope(scope)
                self._fdtd.selectall()
                count = int(self._fdtd.getnumber())
                for i in range(1, count + 1):
                    obj_type = str(self._fdtd.get("type", i)).lower()
                    if any(kw in obj_type for kw in source_keywords):
                        name = str(self._fdtd.get("name", i))
                        if scope == "::":
                            path = "::" + name
                        else:
                            path = scope + "::" + name
                        source_objects.append({
                            "path": path,
                            "type": obj_type,
                            "scope": scope,
                        })
            except Exception:
                pass
        self._fdtd.groupscope("::")

        # 2. Read setup/analysis scripts from analysis groups
        scripts = {}
        for ag_path in ["::s_params", "::model::s_params"]:
            for script_prop in ["setup script", "analysis script"]:
                result = self._read_script_text_safely(ag_path, script_prop)
                scripts.setdefault(ag_path, {})[script_prop] = result

        # 3. Classify
        classification = "unresolved"
        evidence = {
            "source_objects_found": source_objects,
            "scripts_audited": scripts,
        }

        if source_objects:
            classification = "explicit_object"
            evidence["primary_source"] = source_objects[0]
        else:
            # Check scripts for source-related keywords
            source_in_script = False
            for ag_path, ag_scripts in scripts.items():
                for prop, info in ag_scripts.items():
                    if info.get("readable"):
                        summary = info.get("summary", "").lower()
                        if any(
                            kw in summary for kw in source_keywords
                        ):
                            source_in_script = True
            if source_in_script:
                classification = "analysis_group_setup"
            elif scripts:
                classification = "analysis_group_setup"
                evidence["note"] = (
                    "No source object found in tree and no source keyword "
                    "detected in script summaries. Source may be configured "
                    "deep in setup script."
                )

        return {"classification": classification, "evidence": evidence}

    # --- Monitors ---

    def probe_monitors(self) -> list:
        """Enumerate field/power monitor candidates across scopes."""
        monitors = []
        monitor_keywords = ("monitor", "dft", "time")
        for scope in ["::", "::model", "::model::s_params"]:
            try:
                self._fdtd.groupscope(scope)
                self._fdtd.selectall()
                count = int(self._fdtd.getnumber())
                for i in range(1, count + 1):
                    obj_type = str(self._fdtd.get("type", i)).lower()
                    if any(kw in obj_type for kw in monitor_keywords):
                        name = str(self._fdtd.get("name", i))
                        if scope == "::":
                            path = "::" + name
                        else:
                            path = scope + "::" + name
                        monitor = {
                            "path": path,
                            "type": obj_type,
                            "scope": scope,
                            "properties": {},
                        }
                        for prop in (
                            "monitor type", "x", "y", "z",
                            "x span", "y span", "z span",
                            "frequency", "wavelength", "frequency points",
                        ):
                            try:
                                monitor["properties"][prop] = _jsonable(
                                    self._fdtd.getnamed(path, prop)
                                )
                            except Exception:
                                pass
                        monitors.append(monitor)
            except Exception:
                pass
        self._fdtd.groupscope("::")
        return monitors

    # --- Analysis group ---

    def probe_analysis_group(self, ag_paths=None) -> dict:
        """Verify analysis group paths and result naming assumptions."""
        if ag_paths is None:
            ag_paths = ["::s_params", "::model::s_params"]
        result = {}
        for path in ag_paths:
            ag = {"path": path, "exists": False, "type": None}
            try:
                count = self._fdtd.getnamednumber(path)
            except Exception:
                count = 0
            if count == 0:
                result[path] = ag
                continue
            ag["exists"] = True
            try:
                ag["type"] = str(self._fdtd.getnamed(path, "type"))
            except Exception:
                pass

            result_naming = {"transmission": None, "s_parameter": None}
            for prop_name in ["setup script", "analysis script"]:
                try:
                    text = str(self._fdtd.getnamed(path, prop_name))
                    text_lower = text.lower()
                    if (
                        '"t"' in text_lower
                        or "'t'" in text_lower
                        or "transmission" in text_lower
                    ):
                        result_naming["transmission"] = {
                            "assumed_name": "T", "found_in": prop_name,
                        }
                    if (
                        '"s"' in text_lower
                        or "'s'" in text_lower
                        or "s21" in text_lower
                        or "s-parameter" in text_lower
                    ):
                        result_naming["s_parameter"] = {
                            "assumed_name": "S", "found_in": prop_name,
                        }
                    if "s21_gn" in text_lower or "S21_Gn" in text:
                        result_naming["s_parameter"] = {
                            "assumed_name": "S21_Gn", "found_in": prop_name,
                        }
                except Exception:
                    pass
            ag["result_naming_assumptions"] = result_naming
            result[path] = ag
        return result


def _summarize_script(text: str) -> str:
    """Extract minimal summary: first 3 non-empty, non-comment lines."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped[:100])
        if len(lines) >= 3:
            break
    return "; ".join(lines)[:200]


def import_lumapi():
    diagnostics = prepare_lumapi_environment()
    module = importlib.import_module("lumapi")
    return module, diagnostics


# ================================================================
# Probe orchestration and output assembly
# ================================================================


def _failure_probe(
    *,
    template: Path,
    error_type: str,
    message: str,
    hostname: str,
    python_executable: str,
    code_commit: str,
    cleanup_state: str,
) -> dict:
    """Minimal probe output for failure before template load."""
    probe = {
        "probe_version": PROBE_VERSION,
        "probe_only": True,
        "status": "probe_failed",
        "probe_fingerprint": "",
        "template": {
            "logical_path": "templates/metasurface/base_model.fsp",
            "absolute_path": str(template.resolve()),
        },
        "installation": {},
        "inspector": {
            "probe_at": utc_now(),
            "hostname": hostname,
            "python_executable": python_executable,
            "code_commit": code_commit,
            "cleanup_state": cleanup_state,
        },
        "scopes": {},
        "objects": [],
        "identically_named_evidence": [],
        "role_candidates": {},
        "model_parameters": {},
        "fdtd_configuration": {},
        "mesh_configuration": {},
        "source_strategy": {},
        "monitors": [],
        "analysis_group": {},
        "warnings": [],
        "errors": [{"type": error_type, "message": message}],
    }
    probe["probe_fingerprint"] = probe_fingerprint(probe)
    return probe


def build_probe(
    adapter: ProbeAdapter,
    *,
    template: Path,
    hostname: str,
    python_executable: str,
    code_commit: str,
    lumapi_module=None,
    env_diagnostics=None,
) -> dict:
    """Assemble complete probe JSON from all sub-probes."""
    errors = []
    warnings = []

    # 1. Template identity
    stat = template.stat()
    template_id = {
        "logical_path": "templates/metasurface/base_model.fsp",
        "absolute_path": str(template.resolve()),
        "sha256": file_sha256(template),
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
    }

    # 2. Installation identity
    if lumapi_module is None:
        lumapi_module = import_lumapi()
    install_id = probe_installation_identity(lumapi_module)
    install_id["environment_preparation"] = (
        env_diagnostics if env_diagnostics else {}
    )
    fail_install, install_warnings = validate_probe_installation(install_id)
    warnings.extend(install_warnings)
    if fail_install:
        errors.append({
            "type": "install_identity_failed",
            "message": "Installation identity unconfirmable",
        })

    # 3. Scope enumeration
    scopes = adapter.enumerate_scopes([
        "::", "::model", "::s_params", "::model::s_params",
    ])

    # 4. Full object enumeration
    objects = adapter.enumerate_objects_recursive([
        "::", "::model", "::model::s_params",
    ])

    # 5. Identically-named object evidence
    identicals = adapter.probe_identically_named_objects()

    # 6. Role candidates
    role_candidates = {}
    try:
        role_candidates["structure"] = adapter.probe_structure_candidates({
            "pillar": ["::pillar", "::model::pillar"],
            "substrate": ["::substrate", "::model::substrate"],
        })
    except Exception as exc:
        errors.append({
            "type": "structure_probe_failed", "message": str(exc),
        })

    # 7. FDTD
    try:
        fdtd_config = adapter.probe_fdtd_configuration()
    except Exception as exc:
        fdtd_config = {"error": str(exc)}
        errors.append({
            "type": "fdtd_probe_failed", "message": str(exc),
        })

    # 8. Mesh
    try:
        mesh_config = adapter.probe_mesh_configuration()
    except Exception as exc:
        mesh_config = {"error": str(exc)}
        errors.append({
            "type": "mesh_probe_failed", "message": str(exc),
        })

    # 9. Model parameters
    try:
        model_params = adapter.probe_model_parameters()
    except Exception as exc:
        model_params = {"error": str(exc)}
        errors.append({
            "type": "model_params_probe_failed", "message": str(exc),
        })

    # 10. Source strategy
    try:
        source = adapter.probe_source_strategy()
    except Exception as exc:
        source = {"classification": "probe_error", "error": str(exc)}
        errors.append({
            "type": "source_strategy_probe_failed", "message": str(exc),
        })

    # 11. Monitors
    try:
        monitors = adapter.probe_monitors()
    except Exception as exc:
        monitors = []
        errors.append({
            "type": "monitors_probe_failed", "message": str(exc),
        })

    # 12. Analysis group
    try:
        analysis_group = adapter.probe_analysis_group()
    except Exception as exc:
        analysis_group = {}
        errors.append({
            "type": "analysis_probe_failed", "message": str(exc),
        })

    # Determine status
    if fail_install:
        status = "probe_failed"
    elif errors:
        status = "probe_with_errors"
    else:
        status = "probe"

    probe = {
        "probe_version": PROBE_VERSION,
        "probe_only": True,
        "status": status,
        "probe_fingerprint": "",
        "template": template_id,
        "inventory_fingerprint": {
            "stage_a": STAGE_A_INVENTORY_FINGERPRINT,
        },
        "installation": install_id,
        "inspector": {
            "probe_at": utc_now(),
            "hostname": hostname,
            "python_executable": python_executable,
            "code_commit": code_commit,
            "cleanup_state": "pending",
        },
        "scopes": scopes,
        "objects": objects,
        "identically_named_evidence": identicals,
        "role_candidates": role_candidates,
        "model_parameters": model_params,
        "fdtd_configuration": fdtd_config,
        "mesh_configuration": mesh_config,
        "source_strategy": source,
        "monitors": monitors,
        "analysis_group": analysis_group,
        "warnings": warnings,
        "errors": errors,
    }
    probe["probe_fingerprint"] = probe_fingerprint(probe)
    return probe


def run_probe(
    *,
    template: Path,
    output: Path,
    fdtd_factory,
    hostname: str,
    python_executable: str,
    code_commit: str,
    lumapi_factory=None,
) -> int:
    """Main probe runner with cleanup."""
    if not template.is_file():
        atomic_write_json(
            output,
            _failure_probe(
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

    fdtd = None
    adapter = None
    probe = None
    try:
        fdtd = fdtd_factory(True)
        adapter = ProbeAdapter(fdtd)
        adapter.load(str(template.resolve()))
        lumapi_module = None
        env_diagnostics = None
        if lumapi_factory:
            lumapi_module, env_diagnostics = lumapi_factory()
        probe = build_probe(
            adapter,
            template=template,
            hostname=hostname,
            python_executable=python_executable,
            code_commit=code_commit,
            lumapi_module=lumapi_module,
            env_diagnostics=env_diagnostics,
        )
    except Exception as exc:
        probe = _failure_probe(
            template=template,
            error_type="probe_open_failed",
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
                probe["inspector"]["cleanup_state"] = "closed"
            except Exception as exc:
                probe["inspector"]["cleanup_state"] = "close_failed"
                probe.setdefault("warnings", []).append(
                    {"type": "cleanup_failed", "message": str(exc)}
                )
        probe["probe_fingerprint"] = probe_fingerprint(probe)
        atomic_write_json(output, probe)

    return 0 if probe["status"] == "probe" else 1


# ================================================================
# CLI
# ================================================================


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Targeted read-only probe for the metasurface template."
    )
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.probe:
        print("Only --probe is available in Stage B0.", file=sys.stderr)
        return 2
    code = run_probe(
        template=Path(args.template),
        output=Path(args.output),
        fdtd_factory=lambda hide: import_lumapi()[0].FDTD(hide=hide),
        hostname=socket.gethostname(),
        python_executable=sys.executable,
        code_commit=current_commit(),
        lumapi_factory=import_lumapi,
    )
    print(f"Probe: {args.output}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
