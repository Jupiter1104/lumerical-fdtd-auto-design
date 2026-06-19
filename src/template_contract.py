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


# ============================================================
# Stage B1: Strict inspection profile validation
# ============================================================

STRICT_PROFILE_VERSION = "0.1"
STRICT_PROFILE_MODE = "contract"
EXPECTED_TEMPLATE_SHA256 = (
    "03ba1f3ea9db6e86caa9c5458bcf84b6"
    "adb92db6c0664e60f262e2f5edde0176"
)

STRICT_PROFILE_KEYS = {
    "profile_version",
    "mode",
    "template",
    "canonical_paths",
    "fdtd",
    "materials",
    "model_parameters",
    "results",
    "warnings",
}

REQUIRED_CANONICAL_PATHS = {
    "fdtd": "::model::FDTD",
    "model": "::model",
    "pillar": "::model::pillar",
    "substrate": "::model::substrate",
    "mesh": "::model::mesh",
    "source": "::model::s_params::source",
    "analysis_group": "::model::s_params",
    "field_monitor": "::model::field",
    "transmission_monitor": "::model::s_params::T",
    "reflection_monitor": "::model::s_params::R",
    "transmission_index_monitor": "::model::s_params::T_index",
    "reflection_index_monitor": "::model::s_params::R_index",
}

REQUIRED_BOUNDARY_CONDITIONS = {
    "x_min_bc": "Anti-Symmetric",
    "x_max_bc": "Anti-Symmetric",
    "y_min_bc": "Symmetric",
    "y_max_bc": "Symmetric",
    "z_min_bc": "PML",
    "z_max_bc": "PML",
}

REQUIRED_MODEL_PARAMETERS = {
    "ratio": 0.8,
    "height": 7e-7,
    "period": 4.7e-7,
}

REQUIRED_RESULTS = {
    "transmission": "T",
    "s_parameter": "S21_Gn",
}


def inspection_profile_fingerprint(profile: dict) -> str:
    payload = dict(profile)
    payload.pop("profile_fingerprint", None)
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def _require_mapping(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    return value


def _require_equal(actual, expected, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} must be {expected!r}; got {actual!r}.")


def _require_physics_review_warning(profile: dict) -> None:
    warnings = profile.get("warnings", [])
    if not isinstance(warnings, list):
        raise ValueError("warnings must be a list.")
    if not any(
        isinstance(item, dict)
        and item.get("type") == "physics_review_required"
        for item in warnings
    ):
        raise ValueError("warnings must include physics_review_required.")


def validate_inspection_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        raise ValueError("Inspection profile must be an object.")
    _require_exact_keys(profile, STRICT_PROFILE_KEYS, "Inspection profile")
    _require_equal(
        profile["profile_version"],
        STRICT_PROFILE_VERSION,
        "profile_version",
    )
    _require_equal(profile["mode"], STRICT_PROFILE_MODE, "mode")

    template = _require_mapping(profile["template"], "template")
    _require_exact_keys(template, {"logical_path", "sha256"}, "template")
    _require_equal(
        template["logical_path"],
        "templates/metasurface/base_model.fsp",
        "template.logical_path",
    )
    _require_equal(
        template["sha256"],
        EXPECTED_TEMPLATE_SHA256,
        "Template SHA-256",
    )

    canonical_paths = _require_mapping(
        profile["canonical_paths"],
        "canonical_paths",
    )
    _require_equal(canonical_paths, REQUIRED_CANONICAL_PATHS, "canonical_paths")

    fdtd = _require_mapping(profile["fdtd"], "fdtd")
    _require_exact_keys(
        fdtd,
        {
            "dimension",
            "express_mode",
            "resource_type",
            "mesh_accuracy",
            "simulation_time",
            "boundary_conditions",
        },
        "fdtd",
    )
    _require_equal(fdtd["dimension"], "3D", "dimension")
    _require_equal(fdtd["express_mode"], 0, "express_mode")
    _require_equal(fdtd["resource_type"], "CPU", "resource_type")
    _require_equal(fdtd["mesh_accuracy"], 6, "mesh_accuracy")
    _require_equal(fdtd["simulation_time"], 5e-11, "simulation_time")
    _require_equal(
        fdtd["boundary_conditions"],
        REQUIRED_BOUNDARY_CONDITIONS,
        "boundary_conditions",
    )

    materials = _require_mapping(profile["materials"], "materials")
    _require_equal(
        materials,
        {
            "pillar": "Si3N4 (Silicon Nitride) - Kischkat",
            "substrate": "SiO2 (Glass) - Palik",
        },
        "materials",
    )
    _require_equal(
        profile["model_parameters"],
        REQUIRED_MODEL_PARAMETERS,
        "model_parameters",
    )
    _require_equal(profile["results"], REQUIRED_RESULTS, "results")
    _require_physics_review_warning(profile)
    return profile


# ============================================================
# Stage B1: Contract generation
# ============================================================

CONTRACT_VERSION = "0.1"


def contract_fingerprint(contract: dict) -> str:
    payload = dict(contract)
    payload.pop("contract_fingerprint", None)
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def _read_probe_property(probe: dict, key: str):
    return (
        probe.get("fdtd_configuration", {})
        .get("properties", {})
        .get(key, {})
        .get("value")
    )


def _check(name: str, passed: bool, *, expected=None, actual=None) -> tuple:
    return name, {
        "status": "pass" if passed else "fail",
        "expected": expected,
        "actual": actual,
    }


def _values_match(actual, expected) -> bool:
    if actual == expected:
        return True
    if actual is None:
        return False
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(actual) - float(expected)) < 1e-12
    return False


def _candidate_material(probe: dict, role: str, path: str):
    candidates = (
        probe.get("role_candidates", {})
        .get("structure", {})
        .get(role, {})
        .get("candidates", [])
    )
    for candidate in candidates:
        if candidate.get("path") != path or not candidate.get("exists"):
            continue
        material = candidate.get("properties", {}).get("material")
        if isinstance(material, dict):
            return material.get("value")
        return material
    return None


def _monitor_paths(probe: dict) -> set:
    return {
        item.get("path")
        for item in probe.get("monitors", [])
        if isinstance(item, dict)
    }


def generate_template_contract(profile: dict, probe: dict) -> dict:
    validate_inspection_profile(profile)
    paths = profile["canonical_paths"]
    checks = {}

    name, item = _check(
        "template_sha",
        probe.get("template", {}).get("sha256")
        == profile["template"]["sha256"],
        expected=profile["template"]["sha256"],
        actual=probe.get("template", {}).get("sha256"),
    )
    checks[name] = item

    name, item = _check(
        "probe_status",
        probe.get("status") == "probe"
        and probe.get("stage_b1_ready") is True,
        expected={"status": "probe", "stage_b1_ready": True},
        actual={
            "status": probe.get("status"),
            "stage_b1_ready": probe.get("stage_b1_ready"),
        },
    )
    checks[name] = item

    name, item = _check(
        "probe_errors",
        probe.get("errors") == [],
        expected=[],
        actual=probe.get("errors"),
    )
    checks[name] = item

    actual_fdtd_path = probe.get("fdtd_configuration", {}).get(
        "canonical_path"
    )
    name, item = _check(
        "canonical_fdtd_path",
        actual_fdtd_path == paths["fdtd"],
        expected=paths["fdtd"],
        actual=actual_fdtd_path,
    )
    checks[name] = item

    for prop_name, expected in (
        ("dimension", profile["fdtd"]["dimension"]),
        ("express_mode", profile["fdtd"]["express_mode"]),
        ("mesh_accuracy", profile["fdtd"]["mesh_accuracy"]),
        ("simulation_time", profile["fdtd"]["simulation_time"]),
    ):
        actual = _read_probe_property(probe, prop_name)
        checks[prop_name] = _check(
            prop_name,
            _values_match(actual, expected),
            expected=expected,
            actual=actual,
        )[1]

    actual_cpu = (
        probe.get("fdtd_configuration", {})
        .get("cpu_express_mode_evidence", {})
        .get("cpu_confirmed")
    )
    checks["cpu_confirmed"] = _check(
        "cpu_confirmed",
        actual_cpu is True,
        expected=True,
        actual=actual_cpu,
    )[1]

    actual_boundaries = {
        key: _read_probe_property(probe, key)
        for key in REQUIRED_BOUNDARY_CONDITIONS
    }
    checks["boundary_conditions"] = _check(
        "boundary_conditions",
        actual_boundaries == profile["fdtd"]["boundary_conditions"],
        expected=profile["fdtd"]["boundary_conditions"],
        actual=actual_boundaries,
    )[1]

    for role in ("pillar", "substrate"):
        actual = _candidate_material(probe, role, paths[role])
        checks[f"{role}_material"] = _check(
            f"{role}_material",
            actual == profile["materials"][role],
            expected=profile["materials"][role],
            actual=actual,
        )[1]

    actual_source_paths = {
        item.get("path")
        for item in (
            probe.get("source_strategy", {})
            .get("evidence", {})
            .get("source_objects_found", [])
        )
    }
    checks["source"] = _check(
        "source",
        probe.get("source_strategy", {}).get("classification")
        == "explicit_object"
        and paths["source"] in actual_source_paths,
        expected=paths["source"],
        actual=sorted(path for path in actual_source_paths if path),
    )[1]

    expected_monitors = {
        paths["field_monitor"],
        paths["transmission_monitor"],
        paths["reflection_monitor"],
        paths["transmission_index_monitor"],
        paths["reflection_index_monitor"],
    }
    actual_monitors = _monitor_paths(probe)
    checks["monitors"] = _check(
        "monitors",
        expected_monitors.issubset(actual_monitors),
        expected=sorted(expected_monitors),
        actual=sorted(path for path in actual_monitors if path),
    )[1]

    ag = probe.get("analysis_group", {}).get(
        paths["analysis_group"], {}
    )
    result_names = ag.get("result_naming_assumptions", {})
    checks["analysis_group"] = _check(
        "analysis_group",
        ag.get("exists") is True
        and result_names.get("transmission", {}).get("assumed_name")
        == profile["results"]["transmission"]
        and result_names.get("s_parameter", {}).get("assumed_name")
        == profile["results"]["s_parameter"],
        expected={
            "path": paths["analysis_group"],
            "results": profile["results"],
        },
        actual={"exists": ag.get("exists"), "results": result_names},
    )[1]

    all_params_match = True
    actual_params = {}
    for key in REQUIRED_MODEL_PARAMETERS:
        actual_val = (
            probe.get("model_parameters", {}).get(key, {}).get("value")
        )
        actual_params[key] = actual_val
        if not _values_match(actual_val, profile["model_parameters"][key]):
            all_params_match = False
    checks["model_parameters"] = _check(
        "model_parameters",
        all_params_match,
        expected=profile["model_parameters"],
        actual=actual_params,
    )[1]

    verified = all(item["status"] == "pass" for item in checks.values())
    contract = {
        "contract_version": CONTRACT_VERSION,
        "status": "verified" if verified else "unverified",
        "verified": verified,
        "contract_fingerprint": "",
        "profile_fingerprint": inspection_profile_fingerprint(profile),
        "probe_fingerprint": probe.get("probe_fingerprint"),
        "template": profile["template"],
        "installation": {
            "path_version_tag": probe.get("installation", {}).get(
                "path_version_tag"
            ),
            "recorded_version": probe.get("installation", {}).get(
                "recorded_version"
            ),
            "confirmable": probe.get("installation", {}).get("confirmable"),
        },
        "code_commit": probe.get("inspector", {}).get("code_commit"),
        "checks": checks,
        "warnings": profile["warnings"]
        + [
            item
            for item in probe.get("warnings", [])
            if item.get("type") == "version_unknown_warning"
        ],
    }
    contract["contract_fingerprint"] = contract_fingerprint(contract)
    return contract


# ============================================================
# Stage B1: Contract validation
# ============================================================


def validate_template_contract(contract: dict) -> dict:
    errors = []
    if not isinstance(contract, dict):
        return {"ok": False, "errors": ["contract_not_object"]}
    if contract.get("contract_version") != CONTRACT_VERSION:
        errors.append("unsupported_contract_version")
    if (
        contract.get("status") != "verified"
        or contract.get("verified") is not True
    ):
        errors.append("contract_not_verified")
    expected_fingerprint = contract_fingerprint(contract)
    if contract.get("contract_fingerprint") != expected_fingerprint:
        errors.append("contract_fingerprint_mismatch")
    checks = contract.get("checks", {})
    if not isinstance(checks, dict):
        errors.append("checks_not_object")
    else:
        failed = [
            name
            for name, item in checks.items()
            if not isinstance(item, dict) or item.get("status") != "pass"
        ]
        if failed:
            errors.append(
                "contract_checks_failed:" + ",".join(sorted(failed))
            )
    return {"ok": not errors, "errors": errors}


# ============================================================
# Stage C0: Contract execution summary adapter
# ============================================================


def _contract_error(error_type: str, message: str, details=None) -> dict:
    return {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
            "details": details or {},
        },
    }


def _looks_like_legacy_execution_contract(contract: dict) -> bool:
    return all(
        key in contract
        for key in (
            "path",
            "sha256",
            "resource",
            "express_mode",
            "physics_strategy",
            "declared_physics",
        )
    )


def template_contract_execution_summary(contract: dict) -> dict:
    """Return the flat execution contract required by SimulationPlan real mode.

    Accepts both the old flat contract and the Stage B1 verified contract.
    """
    if not isinstance(contract, dict):
        return _contract_error(
            "template_contract_required",
            "Template contract must be an object.",
        )

    if _looks_like_legacy_execution_contract(contract):
        return {
            "ok": True,
            "path": contract["path"],
            "sha256": contract["sha256"],
            "resource": contract["resource"],
            "express_mode": contract["express_mode"],
            "physics_strategy": contract["physics_strategy"],
            "declared_physics": dict(contract["declared_physics"]),
            "contract_fingerprint": contract.get("contract_fingerprint"),
            "warnings": list(contract.get("warnings", [])),
        }

    validation = validate_template_contract(contract)
    if not validation["ok"]:
        return _contract_error(
            "template_contract_unverified",
            "Stage B1 template contract is not verified.",
            {"validation_errors": validation["errors"]},
        )

    checks = contract.get("checks", {})
    express = checks.get("express_mode", {})
    cpu = checks.get("cpu_confirmed", {})
    if express.get("status") != "pass" or express.get("expected") != 0:
        return _contract_error(
            "template_contract_required",
            "Verified contract does not prove express_mode=0.",
        )
    if cpu.get("status") != "pass":
        return _contract_error(
            "template_contract_required",
            "Verified contract does not prove CPU execution.",
        )

    template = contract.get("template", {})
    return {
        "ok": True,
        "path": template.get("logical_path"),
        "sha256": template.get("sha256"),
        "resource": "CPU",
        "express_mode": 0,
        "physics_strategy": "template_inherited",
        "declared_physics": {},
        "contract_fingerprint": contract.get("contract_fingerprint"),
        "warnings": list(contract.get("warnings", [])),
    }
