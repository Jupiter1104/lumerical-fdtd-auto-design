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
