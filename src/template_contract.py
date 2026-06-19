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
