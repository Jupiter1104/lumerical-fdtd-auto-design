"""Compile normalized metasurface SimulationPlans to RPC API v1 jobs."""

from ..simulation_plan import metasurface_plan_to_recipe_sweep


def compile_metasurface_plan(
    normalized_plan: dict,
    fingerprint: str,
    *,
    mode: str,
) -> dict:
    sweep = normalized_plan["sweep"]
    execution = normalized_plan["execution"]
    config = {
        "SWEEP_Y_AXIS": sweep["axis"],
        "RATIO_LIST": list(sweep["ratio_values"]),
        "FDTD_PROCESSES": execution["processes"],
        "FDTD_CAPACITY": execution["capacity"],
        "EXPRESS_MODE": execution["express_mode"],
    }
    if sweep["axis"] == "height":
        config["HEIGHT_LIST"] = list(sweep["height_values_m"])
        config["BASE_PERIOD"] = sweep["fixed_period_m"]
    else:
        config["PERIOD_LIST"] = list(sweep["period_values_m"])
        config["BASE_HEIGHT"] = sweep["fixed_height_m"]

    request = {
        "mode": mode,
        "job_type": "metasurface-sweep",
        "idempotency_key": f"simulation-plan:{fingerprint}:{mode}",
        "sweep": {
            "template": execution["template"],
            "phases": [1, 2, 3, 4],
            "hide": execution["hide"],
            "include_models": normalized_plan["outputs"]["include_models"],
            "config": config,
        },
    }
    if mode == "real":
        request["approval"] = {
            "approved": True,
            "approved_for": "real_run",
        }

    # ── Bridge: attach generic DeviceRecipe + SweepPlan fingerprints ─────
    bridge = metasurface_plan_to_recipe_sweep(normalized_plan)
    request["generic_recipe_fingerprint"] = bridge.get(
        "recipe_fingerprint", ""
    )
    request["generic_sweep_fingerprint"] = bridge.get(
        "sweep_fingerprint", ""
    )

    return request
