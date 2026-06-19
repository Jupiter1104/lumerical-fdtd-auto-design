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


# ============================================================
# Stage B1: Strict profile validation tests (Task B1-1)
# ============================================================


def valid_inspection_profile():
    return {
        "profile_version": "0.1",
        "mode": "contract",
        "template": {
            "logical_path": "templates/metasurface/base_model.fsp",
            "sha256": (
                "03ba1f3ea9db6e86caa9c5458bcf84b6"
                "adb92db6c0664e60f262e2f5edde0176"
            ),
        },
        "canonical_paths": {
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
        },
        "fdtd": {
            "dimension": "3D",
            "express_mode": 0,
            "resource_type": "CPU",
            "mesh_accuracy": 6,
            "simulation_time": 5e-11,
            "boundary_conditions": {
                "x_min_bc": "Anti-Symmetric",
                "x_max_bc": "Anti-Symmetric",
                "y_min_bc": "Symmetric",
                "y_max_bc": "Symmetric",
                "z_min_bc": "PML",
                "z_max_bc": "PML",
            },
        },
        "materials": {
            "pillar": "Si3N4 (Silicon Nitride) - Kischkat",
            "substrate": "SiO2 (Glass) - Palik",
        },
        "model_parameters": {
            "ratio": 0.8,
            "height": 7e-7,
            "period": 4.7e-7,
        },
        "results": {
            "transmission": "T",
            "s_parameter": "S21_Gn",
        },
        "warnings": [
            {
                "type": "physics_review_required",
                "message": (
                    "B0.1 evidence shows x boundaries are Anti-Symmetric "
                    "and y boundaries are Symmetric. Stage B1 preserves "
                    "template evidence and does not change physics settings."
                ),
            }
        ],
    }


def test_inspection_profile_accepts_valid_strict_profile():
    from src.template_contract import validate_inspection_profile

    profile = valid_inspection_profile()
    assert validate_inspection_profile(profile) == profile


def test_inspection_profile_fingerprint_excludes_its_own_field():
    from src.template_contract import inspection_profile_fingerprint

    profile = valid_inspection_profile()
    first = inspection_profile_fingerprint(profile)
    profile["profile_fingerprint"] = "old"
    assert inspection_profile_fingerprint(profile) == first


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda p: p.update({"mode": "inventory"}), "mode"),
        (lambda p: p["template"].update({"sha256": "bad"}), "Template"),
        (lambda p: p["canonical_paths"].update({"fdtd": "FDTD"}), "fdtd"),
        (lambda p: p["fdtd"].update({"express_mode": 1}), "express_mode"),
        (lambda p: p["fdtd"].update({"resource_type": "GPU"}), "resource_type"),
        (
            lambda p: p["fdtd"]["boundary_conditions"].pop("x_min_bc"),
            "boundary_conditions",
        ),
        (lambda p: p["warnings"].clear(), "physics_review_required"),
    ],
)
def test_inspection_profile_rejects_invalid_strict_profile(mutation, match):
    from src.template_contract import validate_inspection_profile

    profile = valid_inspection_profile()
    mutation(profile)
    with pytest.raises(ValueError, match=match):
        validate_inspection_profile(profile)


def test_repository_inspection_profile_matches_schema():
    from src.template_contract import validate_inspection_profile

    profile_path = (
        ROOT
        / "templates"
        / "metasurface"
        / "template-inspection-profile.json"
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert validate_inspection_profile(profile) == profile
