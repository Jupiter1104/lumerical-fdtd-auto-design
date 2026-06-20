from src.plan_compilers.metasurface import compile_metasurface_plan
from src.simulation_plan import (
    metasurface_plan_to_recipe_sweep,
    validate_simulation_plan,
)


def test_compile_period_plan_to_existing_jobs_request():
    validated = validate_simulation_plan({})

    request = compile_metasurface_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
        mode="mock",
    )

    # Compute expected bridge fingerprints
    bridge = metasurface_plan_to_recipe_sweep(validated["normalized_plan"])

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
        "generic_recipe_fingerprint": bridge["recipe_fingerprint"],
        "generic_sweep_fingerprint": bridge["sweep_fingerprint"],
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


# ============================================================
# Bridge integration tests
# ============================================================


def test_compiler_includes_bridge_fingerprints():
    """compile_metasurface_plan output now carries generic fingerprint fields."""
    validated = validate_simulation_plan({})

    request = compile_metasurface_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
        mode="mock",
    )

    assert "generic_recipe_fingerprint" in request
    assert request["generic_recipe_fingerprint"].startswith("sha256:")
    assert "generic_sweep_fingerprint" in request
    assert request["generic_sweep_fingerprint"].startswith("sha256:")


def test_compiler_bridge_fingerprints_are_stable():
    """Identical plans produce identical bridge fingerprints in compiler output."""
    first = compile_metasurface_plan(
        validate_simulation_plan({})["normalized_plan"],
        "fp",
        mode="mock",
    )
    second = compile_metasurface_plan(
        validate_simulation_plan({})["normalized_plan"],
        "fp",
        mode="mock",
    )

    assert first["generic_recipe_fingerprint"] == second["generic_recipe_fingerprint"]
    assert first["generic_sweep_fingerprint"] == second["generic_sweep_fingerprint"]


def test_compiler_bridge_for_height_axis():
    """Height-axis plans get correct bridge fingerprints in compiler output."""
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

    assert request["generic_recipe_fingerprint"].startswith("sha256:")
    assert request["generic_sweep_fingerprint"].startswith("sha256:")
    # Existing compiler output still correct
    assert request["sweep"]["config"]["SWEEP_Y_AXIS"] == "height"
    assert request["sweep"]["config"]["HEIGHT_LIST"] == [600e-9, 800e-9]
    assert request["sweep"]["config"]["BASE_PERIOD"] == 470e-9
