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
