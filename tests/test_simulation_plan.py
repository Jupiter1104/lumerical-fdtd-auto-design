from src.simulation_plan import validate_simulation_plan


def test_empty_plan_uses_disclosed_2x2_cpu_defaults():
    result = validate_simulation_plan({})

    assert result["ok"] is True
    plan = result["normalized_plan"]
    assert plan["schema_version"] == "0.1"
    assert plan["device"] == {"type": "metasurface_unit_cell"}
    assert plan["sweep"] == {
        "axis": "period",
        "ratio_values": [0.2, 0.8],
        "period_values_m": [390e-9, 540e-9],
        "fixed_height_m": 700e-9,
    }
    assert plan["execution"] == {
        "resource": "CPU",
        "express_mode": 0,
        "processes": 1,
        "capacity": 1,
        "hide": True,
        "template": "templates/metasurface/base_model.fsp",
    }
    assert plan["outputs"] == {"include_models": False}
    assert plan["acceptance"] == {
        "required_quality": "pass",
        "required_task_success_rate": 1.0,
    }
    assert result["task_count"] == 4
    assert result["errors"] == []
    assert {
        item["path"] for item in result["defaults_applied"]
    } >= {
        "device.type",
        "sweep.ratio_values",
        "sweep.period_values_m",
        "execution.resource",
        "execution.express_mode",
        "execution.template",
    }


def test_same_normalized_plan_has_stable_fingerprint():
    first = validate_simulation_plan({})
    second = validate_simulation_plan(
        {
            "schema_version": "0.1",
            "device": {"type": "metasurface_unit_cell"},
            "sweep": {
                "axis": "period",
                "ratio_values": [0.2, 0.8],
                "period_values_m": [390e-9, 540e-9],
                "fixed_height_m": 700e-9,
            },
        }
    )

    assert first["plan_fingerprint"] == second["plan_fingerprint"]


def test_plan_change_changes_fingerprint():
    first = validate_simulation_plan({})
    second = validate_simulation_plan(
        {"sweep": {"ratio_values": [0.2, 0.5]}}
    )

    assert first["plan_fingerprint"] != second["plan_fingerprint"]


import pytest


@pytest.mark.parametrize(
    ("plan", "error_type"),
    [
        ({"schema_version": "1.0"}, "plan_validation_error"),
        (
            {"device": {"type": "waveguide"}},
            "unsupported_plan_feature",
        ),
        (
            {"sweep": {"ratio_values": [0.0]}},
            "plan_validation_error",
        ),
        (
            {"sweep": {"ratio_values": [0.2, 0.2]}},
            "plan_validation_error",
        ),
        (
            {"sweep": {"period_values_m": [-1.0]}},
            "plan_validation_error",
        ),
        (
            {"execution": {"resource": "GPU", "express_mode": 1}},
            "unsupported_plan_feature",
        ),
        (
            {"execution": {"resource": "CPU", "express_mode": 1}},
            "plan_validation_error",
        ),
        (
            {
                "physics": {
                    "mesh": {"strategy": "explicit", "accuracy": 6}
                }
            },
            "unsupported_plan_feature",
        ),
    ],
)
def test_invalid_or_unsupported_plans_are_rejected(plan, error_type):
    result = validate_simulation_plan(plan)

    assert result["ok"] is False
    assert result["error"]["type"] == error_type


def test_task_budget_is_limited_to_100():
    result = validate_simulation_plan(
        {
            "sweep": {
                "ratio_values": [index / 100 for index in range(1, 12)],
                "period_values_m": [
                    (390 + index) * 1e-9 for index in range(10)
                ],
            }
        }
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "task_budget_exceeded"
    assert result["error"]["details"]["task_count"] == 110


def test_physics_requirements_are_preserved_with_warning():
    result = validate_simulation_plan(
        {
            "physics": {
                "requirements": {
                    "wavelength_m": 810e-9,
                    "pillar_material": "Si3N4",
                }
            }
        }
    )

    assert result["ok"] is True
    assert result["normalized_plan"]["physics"]["requirements"] == {
        "wavelength_m": 810e-9,
        "pillar_material": "Si3N4",
    }
    assert result["warnings"][0]["type"] == "template_requirement_unverified"


def test_height_sweep_has_expected_task_count():
    result = validate_simulation_plan(
        {
            "sweep": {
                "axis": "height",
                "ratio_values": [0.2, 0.8],
                "height_values_m": [600e-9, 800e-9],
                "fixed_period_m": 470e-9,
            }
        }
    )

    assert result["ok"] is True
    assert result["task_count"] == 4
    assert "period_values_m" not in result["normalized_plan"]["sweep"]


# ============================================================
# Strict-input validation
# ============================================================


def test_sweep_as_list_is_rejected_not_silently_defaulted():
    result = validate_simulation_plan({"sweep": []})
    assert result["ok"] is False
    assert result["error"]["type"] == "plan_validation_error"
    assert "sweep" in result["error"]["message"].lower()
    assert "object" in result["error"]["message"].lower()


def test_unknown_field_in_sweep_section_is_rejected():
    result = validate_simulation_plan(
        {"sweep": {"period_values_nm": [390, 540]}}
    )
    assert result["ok"] is False
    assert result["error"]["type"] == "plan_validation_error"
    assert "unknown" in result["error"]["message"].lower()
    unknown_paths = [
        item["path"] for item in result["error"]["details"].get("unknown_fields", [])
    ]
    assert "sweep.period_values_nm" in unknown_paths


def test_physics_requirement_at_wrong_level_is_rejected():
    result = validate_simulation_plan(
        {"physics": {"wavelength_m": 810e-9}}
    )
    assert result["ok"] is False
    assert result["error"]["type"] == "plan_validation_error"
    unknown_paths = [
        item["path"] for item in result["error"]["details"].get("unknown_fields", [])
    ]
    assert "physics.wavelength_m" in unknown_paths


def test_unknown_top_level_field_is_rejected():
    result = validate_simulation_plan({"simulate_this": True})
    assert result["ok"] is False
    assert result["error"]["type"] == "plan_validation_error"
    unknown_paths = [
        item["path"] for item in result["error"]["details"].get("unknown_fields", [])
    ]
    assert "simulate_this" in unknown_paths


def test_intent_as_string_is_rejected():
    result = validate_simulation_plan({"intent": "sweep metasurface"})
    assert result["ok"] is False
    assert result["error"]["type"] == "plan_validation_error"
    assert "intent" in result["error"]["message"].lower()
    assert "object" in result["error"]["message"].lower()


def test_minimal_valid_plan_still_passes():
    result = validate_simulation_plan({})
    assert result["ok"] is True
    assert result["task_count"] == 4
    assert result["plan_fingerprint"]


def test_period_axis_rejects_height_fields():
    result = validate_simulation_plan(
        {
            "sweep": {
                "axis": "period",
                "ratio_values": [0.2, 0.8],
                "period_values_m": [390e-9, 540e-9],
                "fixed_height_m": 700e-9,
                "height_values_m": [600e-9, 800e-9],
                "fixed_period_m": 470e-9,
            }
        }
    )
    assert result["ok"] is False
    assert result["error"]["type"] == "plan_validation_error"
    paths = {item["path"] for item in result["error"]["details"]["invalid_fields"]}
    assert paths == {"sweep.height_values_m", "sweep.fixed_period_m"}


def test_height_axis_rejects_period_fields():
    result = validate_simulation_plan(
        {
            "sweep": {
                "axis": "height",
                "ratio_values": [0.3],
                "height_values_m": [600e-9, 800e-9],
                "fixed_period_m": 470e-9,
                "period_values_m": [390e-9, 540e-9],
                "fixed_height_m": 700e-9,
            }
        }
    )
    assert result["ok"] is False
    assert result["error"]["type"] == "plan_validation_error"
    paths = {item["path"] for item in result["error"]["details"]["invalid_fields"]}
    assert paths == {"sweep.period_values_m", "sweep.fixed_height_m"}


def test_valid_period_plan_with_period_fields_passes():
    result = validate_simulation_plan(
        {
            "sweep": {
                "axis": "period",
                "ratio_values": [0.2, 0.8],
                "period_values_m": [390e-9, 540e-9],
                "fixed_height_m": 700e-9,
            }
        }
    )
    assert result["ok"] is True
    assert result["task_count"] == 4


def test_valid_height_plan_with_height_fields_passes():
    result = validate_simulation_plan(
        {
            "sweep": {
                "axis": "height",
                "ratio_values": [0.2, 0.8],
                "height_values_m": [600e-9, 800e-9],
                "fixed_period_m": 470e-9,
            }
        }
    )
    assert result["ok"] is True
    assert result["task_count"] == 4


from src.simulation_plan import (
    approve_simulation_plan,
    validate_execution_approvals,
)


def test_plan_can_be_approved_only_for_matching_fingerprint():
    validated = validate_simulation_plan({})

    approval = approve_simulation_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )

    assert approval == {
        "ok": True,
        "approval": {
            "approved": True,
            "approved_for": "simulation_plan",
            "schema_version": "0.1",
            "plan_fingerprint": validated["plan_fingerprint"],
        },
    }


def test_changed_plan_rejects_old_fingerprint():
    old = validate_simulation_plan({})
    changed = {
        "sweep": {"ratio_values": [0.2, 0.5]},
    }

    approval = approve_simulation_plan(
        changed,
        old["plan_fingerprint"],
    )

    assert approval["ok"] is False
    assert approval["error"]["type"] == "plan_fingerprint_mismatch"


def test_mock_requires_matching_plan_approval():
    validated = validate_simulation_plan({})

    missing = validate_execution_approvals(
        validated,
        mode="mock",
        plan_approval=None,
    )

    assert missing["ok"] is False
    assert missing["error"]["type"] == "plan_approval_required"


def test_real_requires_second_approval_and_template_contract():
    validated = validate_simulation_plan({})
    fingerprint = validated["plan_fingerprint"]
    plan_approval = approve_simulation_plan(
        validated["normalized_plan"],
        fingerprint,
    )["approval"]

    missing_real = validate_execution_approvals(
        validated,
        mode="real",
        plan_approval=plan_approval,
    )
    assert missing_real["error"]["type"] == "real_run_approval_required"

    real_approval = {
        "approved": True,
        "approved_for": "real_run",
        "plan_fingerprint": fingerprint,
        "template_sha256": "abc",
    }
    missing_contract = validate_execution_approvals(
        validated,
        mode="real",
        plan_approval=plan_approval,
        real_run_approval=real_approval,
    )
    assert missing_contract["error"]["type"] == "template_contract_required"


def test_real_rejects_approval_for_an_old_plan_fingerprint():
    validated = validate_simulation_plan({})
    fingerprint = validated["plan_fingerprint"]
    plan_approval = approve_simulation_plan(
        validated["normalized_plan"],
        fingerprint,
    )["approval"]

    result = validate_execution_approvals(
        validated,
        mode="real",
        plan_approval=plan_approval,
        real_run_approval={
            "approved": True,
            "approved_for": "real_run",
            "plan_fingerprint": "old-fingerprint",
            "template_sha256": "abc",
        },
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "plan_fingerprint_mismatch"


def test_real_template_contract_must_match_physics_requirements():
    validated = validate_simulation_plan(
        {
            "physics": {
                "requirements": {"wavelength_m": 810e-9}
            }
        }
    )
    fingerprint = validated["plan_fingerprint"]
    plan_approval = approve_simulation_plan(
        validated["normalized_plan"],
        fingerprint,
    )["approval"]
    real_approval = {
        "approved": True,
        "approved_for": "real_run",
        "plan_fingerprint": fingerprint,
        "template_sha256": "abc",
    }
    result = validate_execution_approvals(
        validated,
        mode="real",
        plan_approval=plan_approval,
        real_run_approval=real_approval,
        template_contract={
            "path": "templates/metasurface/base_model.fsp",
            "sha256": "abc",
            "resource": "CPU",
            "express_mode": 0,
            "physics_strategy": "template_inherited",
            "declared_physics": {"wavelength_m": 1550e-9},
        },
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "template_contract_required"
