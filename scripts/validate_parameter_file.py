#!/usr/bin/env python3
"""Lossless parameter file validate/normalize/compile check.

Validates a JSON parameter file through the DeviceRecipe and Generic SweepPlan
compilers without starting any FDTD solve, RPC call, or job creation.

Usage:
    .venv/bin/python scripts/validate_parameter_file.py --parameter-file tests/fixtures/synthetic_parameters.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path so 'src' imports work without PYTHONPATH
_sys_path_project_root = Path(__file__).resolve().parent.parent
if str(_sys_path_project_root) not in sys.path:
    sys.path.insert(0, str(_sys_path_project_root))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a parameter file through Recipe + SweepPlan compilers."
    )
    parser.add_argument(
        "--parameter-file",
        required=True,
        type=Path,
        help="Path to JSON parameter file (Recipe shape).",
    )
    args = parser.parse_args()

    param_path: Path = args.parameter_file
    if not param_path.exists():
        print(json.dumps({"ok": False, "error": f"File not found: {param_path}"}, indent=2))
        return 1

    try:
        raw = param_path.read_text(encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"Read error: {exc}"}, indent=2))
        return 1

    try:
        recipe = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"JSON parse error: {exc}"}, indent=2))
        return 1

    # Import compilers (pure Python, no Windows/Lumerical needed)
    from src.device_recipe import validate_recipe, compile_recipe
    from src.generic_sweep import validate_sweep_plan, plan_generic_sweep

    # Step 1: validate recipe
    validation = validate_recipe(recipe)
    if not validation.get("ok"):
        validation["technical_validation"] = True
        validation["physical_conclusion"] = False
        print(json.dumps(validation, indent=2, ensure_ascii=False))
        return 1

    # Step 2: compile recipe
    compile_result = compile_recipe(recipe)
    if not compile_result.get("ok"):
        compile_result["technical_validation"] = True
        compile_result["physical_conclusion"] = False
        print(json.dumps(compile_result, indent=2, ensure_ascii=False))
        return 1

    # Step 3: build a minimal sweep plan (single point)
    sweep_plan = {
        "schema_version": "1.0",
        "recipe_ref": {"recipe": recipe},
        "parameters": [
            {"name": "period", "values": [recipe["parameters"]["period"]["default"]]}
        ],
    }
    sweep_validation = validate_sweep_plan(sweep_plan, compile_result["recipe_fingerprint"])
    if not sweep_validation.get("ok"):
        sweep_validation["technical_validation"] = True
        sweep_validation["physical_conclusion"] = False
        print(json.dumps(sweep_validation, indent=2, ensure_ascii=False))
        return 1

    # Step 4: plan (single task)
    plan_result = plan_generic_sweep(recipe, sweep_plan)
    if not plan_result.get("ok"):
        plan_result["technical_validation"] = True
        plan_result["physical_conclusion"] = False
        print(json.dumps(plan_result, indent=2, ensure_ascii=False))
        return 1

    task_count = len(plan_result["plan"]["tasks"])

    output = {
        "ok": True,
        "parameter_count": len(recipe.get("parameters", {})),
        "task_count": task_count,
        "recipe_fingerprint": compile_result["recipe_fingerprint"],
        "compile_fingerprint": compile_result["compile_fingerprint"],
        "sweep_fingerprint": plan_result["plan"]["sweep_fingerprint"],
        "packet_fingerprint": plan_result["plan"]["packet_fingerprint"],
        "technical_validation": True,
        "physical_conclusion": False,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
