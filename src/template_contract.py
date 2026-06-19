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
