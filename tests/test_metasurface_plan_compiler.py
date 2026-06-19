from src.plan_compilers.metasurface import compile_metasurface_plan
from src.simulation_plan import validate_simulation_plan


def test_compile_period_plan_to_existing_jobs_request():
    validated = validate_simulation_plan({})

    request = compile_metasurface_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
        mode="mock",
    )

    assert request == {
        "mode": "mock",
        "job_type": "metasurface-sweep",
        "idempotency_key": (
            "simulation-plan:"
            f"{validated['plan_fingerprint']}:mock"
        ),
        "sweep": {
            "template": "templates/metasurface/base_model.fsp",
            "phases": [1, 2, 3, 4],
            "hide": True,
            "include_models": False,
            "config": {
                "SWEEP_Y_AXIS": "period",
                "RATIO_LIST": [0.2, 0.8],
                "PERIOD_LIST": [390e-9, 540e-9],
                "BASE_HEIGHT": 700e-9,
                "FDTD_PROCESSES": 1,
                "FDTD_CAPACITY": 1,
                "EXPRESS_MODE": 0,
            },
        },
    }


def test_compile_height_plan_maps_height_list_and_fixed_period():
    validated = validate_simulation_plan(
        {
            "sweep": {
                "axis": "height",
                "ratio_values": [0.3],
                "height_values_m": [600e-9, 800e-9],
                "fixed_period_m": 470e-9,
            }
        }
    )

    request = compile_metasurface_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
        mode="mock",
    )

    config = request["sweep"]["config"]
    assert config["SWEEP_Y_AXIS"] == "height"
    assert config["RATIO_LIST"] == [0.3]
    assert config["HEIGHT_LIST"] == [600e-9, 800e-9]
    assert config["BASE_PERIOD"] == 470e-9
    assert "PERIOD_LIST" not in config


def test_real_compilation_adds_existing_rpc_approval():
    validated = validate_simulation_plan({})

    request = compile_metasurface_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
        mode="real",
    )

    assert request["approval"] == {
        "approved": True,
        "approved_for": "real_run",
    }
