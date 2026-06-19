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


# ============================================================
# Stage B1: Contract generation tests (Task B1-3)
# ============================================================


def valid_b01_probe():
    return {
        "probe_version": "0.1",
        "probe_only": True,
        "status": "probe",
        "probe_fingerprint": (
            "a8e7e2ee4265f607012c54b85e29a01"
            "f55ede9220cb37b12033be6f471c017d6"
        ),
        "template": {
            "logical_path": "templates/metasurface/base_model.fsp",
            "sha256": (
                "03ba1f3ea9db6e86caa9c5458bcf84b6"
                "adb92db6c0664e60f262e2f5edde0176"
            ),
        },
        "installation": {
            "confirmable": True,
            "path_version_tag": "v242",
            "recorded_version": "unknown",
        },
        "inspector": {
            "code_commit": "bff39a0",
            "cleanup_state": "closed",
        },
        "fdtd_configuration": {
            "canonical_path": "::model::FDTD",
            "properties": {
                "dimension": {"status": "readable", "value": "3D"},
                "express_mode": {"status": "readable", "value": 0.0},
                "mesh_accuracy": {"status": "readable", "value": 6.0},
                "simulation_time": {"status": "readable", "value": 5e-11},
                "x_min_bc": {"status": "readable", "value": "Anti-Symmetric"},
                "x_max_bc": {"status": "readable", "value": "Anti-Symmetric"},
                "y_min_bc": {"status": "readable", "value": "Symmetric"},
                "y_max_bc": {"status": "readable", "value": "Symmetric"},
                "z_min_bc": {"status": "readable", "value": "PML"},
                "z_max_bc": {"status": "readable", "value": "PML"},
            },
            "cpu_express_mode_evidence": {
                "express_mode_value": 0.0,
                "cpu_confirmed": True,
                "evidence_source": "getnamed",
            },
        },
        "role_candidates": {
            "structure": {
                "pillar": {
                    "candidates": [
                        {
                            "path": "::model::pillar",
                            "exists": True,
                            "properties": {
                                "type": {"value": "Circle"},
                                "material": {
                                    "value": (
                                        "Si3N4 (Silicon Nitride) - Kischkat"
                                    )
                                },
                            },
                        }
                    ]
                },
                "substrate": {
                    "candidates": [
                        {
                            "path": "::model::substrate",
                            "exists": True,
                            "properties": {
                                "type": {"value": "Rectangle"},
                                "material": {
                                    "value": "SiO2 (Glass) - Palik"
                                },
                            },
                        }
                    ]
                },
            }
        },
        "mesh_configuration": {
            "global_mesh_accuracy_source": "::model::FDTD",
            "overrides": [{"path": "::model::mesh", "exists": True}],
        },
        "source_strategy": {
            "classification": "explicit_object",
            "evidence": {
                "source_objects_found": [
                    {
                        "path": "::model::s_params::source",
                        "type": "planesource",
                    }
                ]
            },
        },
        "monitors": [
            {"path": "::model::field"},
            {"path": "::model::s_params::T"},
            {"path": "::model::s_params::R"},
            {"path": "::model::s_params::T_index"},
            {"path": "::model::s_params::R_index"},
        ],
        "analysis_group": {
            "::model::s_params": {
                "exists": True,
                "result_naming_assumptions": {
                    "transmission": {"assumed_name": "T"},
                    "s_parameter": {"assumed_name": "S21_Gn"},
                },
            }
        },
        "model_parameters": {
            "ratio": {"value": 0.8},
            "height": {"value": 7e-7},
            "period": {"value": 4.7e-7},
        },
        "warnings": [
            {"type": "version_unknown_warning"},
        ],
        "errors": [],
        "stage_b1_ready": True,
        "stage_b1_blockers": [],
    }


def test_generate_template_contract_returns_verified_contract():
    from src.template_contract import (
        contract_fingerprint,
        generate_template_contract,
    )

    contract = generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )

    assert contract["contract_version"] == "0.1"
    assert contract["status"] == "verified"
    assert contract["verified"] is True
    assert contract["contract_fingerprint"] == contract_fingerprint(contract)
    assert (
        contract["template"]["sha256"]
        == valid_inspection_profile()["template"]["sha256"]
    )
    assert contract["checks"]["express_mode"]["status"] == "pass"
    assert contract["checks"]["cpu_confirmed"]["status"] == "pass"
    assert contract["warnings"][0]["type"] == "physics_review_required"


@pytest.mark.parametrize(
    "mutation,failed_check",
    [
        (
            lambda p: p["template"].update({"sha256": "bad"}),
            "template_sha",
        ),
        (
            lambda p: p["fdtd_configuration"].update(
                {"canonical_path": "FDTD"}
            ),
            "canonical_fdtd_path",
        ),
        (
            lambda p: p["fdtd_configuration"]["properties"][
                "express_mode"
            ].update({"value": 1}),
            "express_mode",
        ),
        (
            lambda p: p["fdtd_configuration"][
                "cpu_express_mode_evidence"
            ].update({"cpu_confirmed": False}),
            "cpu_confirmed",
        ),
        (
            lambda p: p["source_strategy"].update(
                {"classification": "unresolved"}
            ),
            "source",
        ),
        (
            lambda p: p["monitors"].pop(),
            "monitors",
        ),
        (
            lambda p: p["fdtd_configuration"]["properties"].pop("x_min_bc"),
            "boundary_conditions",
        ),
        (
            lambda p: p.update({"errors": [{"type": "probe_error"}]}),
            "probe_errors",
        ),
    ],
)
def test_generate_template_contract_fails_closed(mutation, failed_check):
    from src.template_contract import generate_template_contract

    probe = valid_b01_probe()
    mutation(probe)
    contract = generate_template_contract(valid_inspection_profile(), probe)

    assert contract["status"] == "unverified"
    assert contract["verified"] is False
    assert contract["checks"][failed_check]["status"] == "fail"


# ============================================================
# Stage B1: Contract validation tests (Task B1-4)
# ============================================================


def test_validate_template_contract_accepts_verified_contract():
    from src.template_contract import (
        generate_template_contract,
        validate_template_contract,
    )

    contract = generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )

    assert validate_template_contract(contract) == {
        "ok": True,
        "errors": [],
    }


def test_validate_template_contract_rejects_tampered_fingerprint():
    from src.template_contract import (
        generate_template_contract,
        validate_template_contract,
    )

    contract = generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )
    contract["checks"]["express_mode"]["actual"] = 1

    result = validate_template_contract(contract)

    assert result["ok"] is False
    assert "contract_fingerprint_mismatch" in result["errors"]


def test_validate_template_contract_rejects_unverified_status():
    from src.template_contract import validate_template_contract

    contract = {
        "contract_version": "0.1",
        "status": "unverified",
        "verified": False,
        "contract_fingerprint": "not-a-real-fingerprint",
        "checks": {"template_sha": {"status": "fail"}},
    }

    result = validate_template_contract(contract)

    assert result["ok"] is False
    assert "contract_not_verified" in result["errors"]


# ============================================================
# Stage B1: CLI tests (Task B1-5)
# ============================================================


def test_generate_template_contract_cli_writes_verified_contract(tmp_path):
    import subprocess
    import sys

    profile_path = tmp_path / "profile.json"
    probe_path = tmp_path / "probe.json"
    output_path = tmp_path / "contract.json"
    atomic_write_json(profile_path, valid_inspection_profile())
    atomic_write_json(probe_path, valid_b01_probe())

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_template_contract.py"),
            "--profile",
            str(profile_path),
            "--probe",
            str(probe_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    contract = json.loads(output_path.read_text(encoding="utf-8"))
    assert contract["status"] == "verified"


def test_generate_template_contract_cli_nonzero_for_unverified(tmp_path):
    import subprocess
    import sys

    profile_path = tmp_path / "profile.json"
    probe_path = tmp_path / "probe.json"
    output_path = tmp_path / "contract.json"
    probe = valid_b01_probe()
    probe["fdtd_configuration"]["properties"]["express_mode"]["value"] = 1
    atomic_write_json(profile_path, valid_inspection_profile())
    atomic_write_json(probe_path, probe)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_template_contract.py"),
            "--profile",
            str(profile_path),
            "--probe",
            str(probe_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    contract = json.loads(output_path.read_text(encoding="utf-8"))
    assert contract["status"] == "unverified"


# ============================================================
# Stage C0: Contract execution summary tests (Task C0-1)
# ============================================================


def valid_b1_contract():
    from src.template_contract import generate_template_contract

    return generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )


def test_template_contract_execution_summary_accepts_verified_b1_contract():
    from src.template_contract import template_contract_execution_summary

    contract = valid_b1_contract()
    summary = template_contract_execution_summary(contract)

    assert summary == {
        "ok": True,
        "path": "templates/metasurface/base_model.fsp",
        "sha256": (
            "03ba1f3ea9db6e86caa9c5458bcf84b6"
            "adb92db6c0664e60f262e2f5edde0176"
        ),
        "resource": "CPU",
        "express_mode": 0,
        "physics_strategy": "template_inherited",
        "declared_physics": {},
        "contract_fingerprint": contract["contract_fingerprint"],
        "warnings": contract["warnings"],
    }


def test_template_contract_execution_summary_preserves_legacy_contract():
    from src.template_contract import template_contract_execution_summary

    legacy = {
        "path": "templates/metasurface/base_model.fsp",
        "sha256": "abc",
        "resource": "CPU",
        "express_mode": 0,
        "physics_strategy": "template_inherited",
        "declared_physics": {"wavelength_m": 810e-9},
    }

    assert template_contract_execution_summary(legacy) == {
        "ok": True,
        "path": "templates/metasurface/base_model.fsp",
        "sha256": "abc",
        "resource": "CPU",
        "express_mode": 0,
        "physics_strategy": "template_inherited",
        "declared_physics": {"wavelength_m": 810e-9},
        "contract_fingerprint": None,
        "warnings": [],
    }


def test_template_contract_execution_summary_rejects_unverified_b1_contract():
    from src.template_contract import template_contract_execution_summary

    contract = valid_b1_contract()
    contract["status"] = "unverified"

    result = template_contract_execution_summary(contract)

    assert result["ok"] is False
    assert result["error"]["type"] == "template_contract_unverified"
