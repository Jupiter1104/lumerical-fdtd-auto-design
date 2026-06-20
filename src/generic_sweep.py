"""Generic SweepPlan validation, expansion, and compilation.

Pure Python — no Windows/Lumerical/RPC required.

Takes a DeviceRecipe and sweep parameter specification, generates
Cartesian product task grids, compiles each task's script, and
produces deterministic plan packets with fingerprints.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import math
from typing import Any, Dict, List, Optional, Union

from .device_recipe import compile_recipe, validate_recipe
from .fdtd_schema import fingerprint_json, stable_json_dumps


# ═══════════════════════════════════════════════════════════════════════════
# Range expansion
# ═══════════════════════════════════════════════════════════════════════════


def _expand_range(start: float, stop: float, step: float) -> List[float]:
    """Expand a range specification into a list of values.

    Inclusive start and stop.  Uses ``n = round((stop - start) / step) + 1``
    and returns ``[start + i*step for i in range(n)]``.

    Raises :exc:`ValueError` if step is not positive.
    """
    if step <= 0:
        raise ValueError(f"Range step must be positive, got {step!r}")

    n = round((stop - start) / step) + 1
    if n < 1:
        n = 1

    values: List[float] = []
    for i in range(n):
        v = start + i * step
        # Round to suppress floating-point artefacts while preserving
        # the precision implied by the step magnitude.
        v = _round_value(v, step)
        values.append(v)

    # Ensure the final value is exactly *stop* (inclusive guarantee).
    if values:
        values[-1] = float(stop)

    return values


def _round_value(v: float, step: float) -> float:
    """Round *v* to a precision appropriate for the step magnitude."""
    # Determine the number of decimal places from the step.
    # We use the step's string representation to count decimals.
    decimals = _count_step_decimals(step)
    if decimals is not None:
        return round(v, decimals)
    # Fallback: round to 12 significant digits to squash float artefacts.
    return round(v, 12)


def _count_step_decimals(step: float) -> Optional[int]:
    """Count decimal places in *step* for rounding purposes.

    Returns *None* when the step is best handled by significant-figure
    rounding (scientific-notation values).
    """
    # Use repr to get a precise string, then convert to non-scientific form
    s = repr(step)
    if "e" in s.lower():
        # Scientific notation — count mantissa decimals and adjust for exponent
        mantissa, exp = s.lower().split("e")
        exp = int(exp)
        if "." in mantissa:
            mantissa_dec = len(mantissa.split(".")[1])
        else:
            mantissa_dec = 0
        # decimals = mantissa_dec - exp (e.g., 7.5e-08: mantissa_dec=1, exp=-8 → 9)
        return max(0, mantissa_dec - exp)
    else:
        if "." in s:
            return len(s.split(".")[1])
        return 0


# ═══════════════════════════════════════════════════════════════════════════
# Cartesian product expansion
# ═══════════════════════════════════════════════════════════════════════════


def _expand_cartesian_product(params: List[dict]) -> List[dict]:
    """Expand sweep parameters into a Cartesian product of parameter assignments.

    Each element of *params* must have ``name`` and either ``values``
    (explicit list) or ``range`` (``start``/``stop``/``step``).

    The last declared parameter changes fastest (standard Cartesian
    product iteration order with ``itertools.product``).
    """
    names: List[str] = []
    value_lists: List[List[float]] = []

    for p in params:
        name = p["name"]
        names.append(name)

        if "values" in p:
            value_lists.append(list(p["values"]))
        elif "range" in p:
            r = p["range"]
            value_lists.append(_expand_range(r["start"], r["stop"], r["step"]))
        else:
            raise ValueError(f"Parameter {name!r} has neither values nor range")

    result: List[dict] = []
    for combo in itertools.product(*value_lists):
        result.append(dict(zip(names, combo)))

    return result


# ═══════════════════════════════════════════════════════════════════════════
# Sweep plan validation
# ═══════════════════════════════════════════════════════════════════════════


def validate_sweep_plan(
    sweep_plan: dict,
    recipe_fingerprint: str,
) -> dict:
    """Validate a sweep plan structure without compiling all tasks.

    Args:
        sweep_plan: The sweep specification dict.
        recipe_fingerprint: Expected recipe fingerprint for consistency
            checking (stored, not verified here).

    Returns:
        A dict with keys ``ok``, ``errors``, ``warnings``,
        ``sweep_fingerprint``, ``task_count_estimate``, and
        ``coverage_risks``.
    """
    errors: List[dict] = []
    warnings: List[dict] = []

    if not isinstance(sweep_plan, dict):
        return {
            "ok": False,
            "errors": [{"code": "invalid_sweep_plan", "message": "Sweep plan must be a dict"}],
            "warnings": [],
            "sweep_fingerprint": "",
            "task_count_estimate": 0,
            "coverage_risks": [],
            "recipe_fingerprint": recipe_fingerprint,
        }

    # ── schema_version ────────────────────────────────────────────────────

    sv = sweep_plan.get("schema_version")
    if sv != "1.0":
        errors.append({
            "code": "invalid_schema_version",
            "message": f"schema_version must be '1.0', got {sv!r}",
        })
        return _build_validation_result(errors, warnings, recipe_fingerprint)

    # ── parameters ────────────────────────────────────────────────────────

    raw_params = sweep_plan.get("parameters")
    if not isinstance(raw_params, list) or len(raw_params) == 0:
        errors.append({
            "code": "missing_parameters",
            "message": "Sweep plan must have at least one parameter",
        })
        return _build_validation_result(errors, warnings, recipe_fingerprint)

    param_names: List[str] = []
    task_count = 1

    for i, p in enumerate(raw_params):
        p_errors, p_warnings, p_count = _validate_sweep_param(p, i)
        errors.extend(p_errors)
        warnings.extend(p_warnings)

        if isinstance(p, dict) and p.get("name"):
            name = p["name"]
            if name in param_names:
                errors.append({
                    "code": "duplicate_parameter_name",
                    "message": f"Duplicate sweep parameter {name!r}",
                })
            param_names.append(name)

        if p_count > 0:
            task_count *= p_count

    # ── max_tasks ─────────────────────────────────────────────────────────

    plan_max = sweep_plan.get("max_tasks", 1000)
    if not isinstance(plan_max, int) or plan_max < 1:
        errors.append({
            "code": "invalid_max_tasks",
            "message": f"max_tasks must be a positive integer, got {plan_max!r}",
        })
        plan_max = 1000

    if task_count > plan_max:
        errors.append({
            "code": "task_count_exceeds_max",
            "message": (
                f"Estimated {task_count} tasks exceeds max_tasks={plan_max}. "
                f"Reduce sweep range or increase max_tasks."
            ),
        })

    # ── sweep fingerprint ─────────────────────────────────────────────────

    sweep_data = {
        "schema_version": "1.0",
        "parameters": [
            _normalize_param_for_fingerprint(p) for p in raw_params
            if isinstance(p, dict)
        ],
        "max_tasks": plan_max,
    }
    sweep_fingerprint = fingerprint_json(sweep_data) if not errors else ""

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "sweep_fingerprint": sweep_fingerprint,
        "task_count_estimate": task_count if task_count <= plan_max else task_count,
        "coverage_risks": [],
        "recipe_fingerprint": recipe_fingerprint,
    }


def _validate_sweep_param(p: Any, index: int):
    """Validate a single sweep parameter specification.

    Returns (errors, warnings, value_count).
    """
    errors: List[dict] = []
    warnings: List[dict] = []
    value_count = 0

    if not isinstance(p, dict):
        errors.append({
            "code": "invalid_parameter",
            "message": f"Sweep parameter {index} must be an object",
        })
        return errors, warnings, 0

    # name
    name = p.get("name")
    if not isinstance(name, str) or not name:
        errors.append({
            "code": "missing_parameter_name",
            "message": f"Sweep parameter {index} must have a non-empty 'name'",
        })
        return errors, warnings, 0

    has_values = "values" in p
    has_range = "range" in p

    if not has_values and not has_range:
        errors.append({
            "code": "missing_parameter_spec",
            "message": (
                f"Parameter {name!r} must have either 'values' (explicit list) "
                f"or 'range' ({{start, stop, step}})"
            ),
        })
        return errors, warnings, 0

    if has_values and has_range:
        errors.append({
            "code": "ambiguous_parameter_spec",
            "message": (
                f"Parameter {name!r} has both 'values' and 'range' — "
                f"use only one"
            ),
        })
        return errors, warnings, 0

    if has_values:
        vals = p["values"]
        if not isinstance(vals, list) or len(vals) == 0:
            errors.append({
                "code": "empty_parameter_values",
                "message": f"Parameter {name!r} 'values' must be a non-empty list",
            })
            return errors, warnings, 0

        # Check all values are numeric
        for vi, v in enumerate(vals):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                errors.append({
                    "code": "invalid_value",
                    "message": (
                        f"Parameter {name!r} value at index {vi} must be numeric, "
                        f"got {type(v).__name__}"
                    ),
                })
                break

        value_count = len(vals)

        # Duplicate check
        seen: set = set()
        for v in vals:
            key = repr(v)
            if key in seen:
                errors.append({
                    "code": "duplicate_parameter_values",
                    "message": (
                        f"Parameter {name!r} has duplicate value {v!r}"
                    ),
                })
                break
            seen.add(key)

    elif has_range:
        r = p["range"]
        if not isinstance(r, dict):
            errors.append({
                "code": "invalid_range_spec",
                "message": f"Parameter {name!r} 'range' must be an object",
            })
            return errors, warnings, 0

        start = r.get("start")
        stop = r.get("stop")
        step = r.get("step")

        for field in ("start", "stop", "step"):
            if field not in r:
                errors.append({
                    "code": "invalid_range_spec",
                    "message": (
                        f"Parameter {name!r} 'range' missing required field "
                        f"{field!r}"
                    ),
                })

        if errors:
            return errors, warnings, 0

        if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                   for x in (start, stop, step)):
            errors.append({
                "code": "invalid_range_spec",
                "message": (
                    f"Parameter {name!r} range fields must be numeric"
                ),
            })
            return errors, warnings, 0

        if step <= 0:
            errors.append({
                "code": "invalid_range_spec",
                "message": f"Parameter {name!r} range step must be positive",
            })
            return errors, warnings, 0

        try:
            value_count = round((stop - start) / step) + 1
        except Exception:
            value_count = 0
        if value_count < 1:
            value_count = 1

    return errors, warnings, value_count


def _normalize_param_for_fingerprint(p: dict) -> dict:
    """Build a stable dict for fingerprinting a sweep parameter."""
    norm: dict = {"name": p.get("name", "")}
    if "values" in p:
        norm["values"] = list(p["values"])
    elif "range" in p:
        r = p["range"]
        norm["range"] = {
            "start": r.get("start"),
            "stop": r.get("stop"),
            "step": r.get("step"),
        }
    return norm


def _build_validation_result(
    errors: List[dict],
    warnings: List[dict],
    recipe_fingerprint: str,
) -> dict:
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "sweep_fingerprint": "",
        "task_count_estimate": 0,
        "coverage_risks": [],
        "recipe_fingerprint": recipe_fingerprint,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Plan generation
# ═══════════════════════════════════════════════════════════════════════════


def plan_generic_sweep(
    recipe: dict,
    sweep_plan: dict,
    max_tasks: int = 1000,
) -> dict:
    """Full expansion and compilation of a generic sweep plan.

    Args:
        recipe: A device recipe dict.
        sweep_plan: The sweep specification with parameters to sweep.
        max_tasks: Maximum allowed task count (default 1000).

    Returns:
        A plan packet dict with ``ok``, ``plan`` (if ok), and ``errors``.
    """
    errors: List[dict] = []
    warnings: List[dict] = []

    # ── 1. Validate / compile the base recipe ─────────────────────────────

    compile_result = compile_recipe(recipe)
    if not compile_result["ok"]:
        errors.extend(compile_result.get("errors", []))
        return {
            "ok": False,
            "errors": errors,
            "warnings": compile_result.get("warnings", []),
            "plan": {},
        }

    recipe_fingerprint = compile_result["recipe_fingerprint"]
    compile_fingerprint = compile_result["compile_fingerprint"]

    # ── 2. Validate sweep plan structure ──────────────────────────────────

    validation = validate_sweep_plan(sweep_plan, recipe_fingerprint)
    if not validation["ok"]:
        return {
            "ok": False,
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "plan": {},
        }

    sweep_params = sweep_plan.get("parameters", [])
    recipe_param_names = set(recipe.get("parameters", {}).keys())

    # ── 3. Check every swept parameter exists in the recipe ───────────────

    for p in sweep_params:
        if isinstance(p, dict):
            name = p.get("name", "")
            if name and name not in recipe_param_names:
                errors.append({
                    "code": "unknown_sweep_parameter",
                    "message": (
                        f"Sweep parameter {name!r} not found in recipe "
                        f"parameters: {sorted(recipe_param_names)}"
                    ),
                })

    if errors:
        return {
            "ok": False,
            "errors": errors,
            "warnings": validation["warnings"],
            "plan": {},
        }

    # ── 4. Check task count against max_tasks ─────────────────────────────

    actual_max = sweep_plan.get("max_tasks", max_tasks)
    if not isinstance(actual_max, int) or actual_max < 1:
        actual_max = max_tasks

    estimated = validation.get("task_count_estimate", 0)
    if estimated > actual_max:
        errors.append({
            "code": "task_count_exceeds_max",
            "message": (
                f"Estimated {estimated} tasks exceeds max_tasks={actual_max}. "
                f"Reduce sweep range or increase max_tasks."
            ),
        })
        return {
            "ok": False,
            "errors": errors,
            "warnings": validation["warnings"],
            "plan": {},
        }

    # ── 5. Expand Cartesian product ───────────────────────────────────────

    try:
        param_assignments = _expand_cartesian_product(sweep_params)
    except ValueError as exc:
        errors.append({
            "code": "expansion_error",
            "message": str(exc),
        })
        return {
            "ok": False,
            "errors": errors,
            "warnings": validation["warnings"],
            "plan": {},
        }

    task_count = len(param_assignments)

    # ── 6. Fingerprint sweep plan ─────────────────────────────────────────

    sweep_fingerprint = fingerprint_json({
        "schema_version": "1.0",
        "parameters": [
            _normalize_param_for_fingerprint(p) for p in sweep_params
        ],
        "max_tasks": actual_max,
    })

    # ── 7. Compile each task ──────────────────────────────────────────────

    tasks: List[dict] = []
    for index, assignment in enumerate(param_assignments):
        task_recipe = _apply_param_overrides(recipe, assignment)
        task_compile = compile_recipe(task_recipe)

        if not task_compile["ok"]:
            errors.append({
                "code": "task_compilation_failed",
                "message": (
                    f"Task {index} compilation failed for parameters "
                    f"{assignment}: {task_compile.get('errors', [])}"
                ),
            })
            continue

        # Build stable task_id
        task_id_data = {
            "recipe_fingerprint": recipe_fingerprint,
            "sweep_fingerprint": sweep_fingerprint,
            "index": index,
            "parameters": assignment,
        }
        task_id = fingerprint_json(task_id_data)

        tasks.append({
            "task_id": task_id,
            "index": index,
            "parameters": dict(assignment),
            "script_sha256": task_compile["script_sha256"],
            "script": task_compile["script"],
        })

    if errors:
        return {
            "ok": False,
            "errors": errors,
            "warnings": warnings + validation.get("warnings", []),
            "plan": {},
        }

    # ── 8. Assemble packet fingerprint ────────────────────────────────────

    packet_data = {
        "recipe_fingerprint": recipe_fingerprint,
        "sweep_fingerprint": sweep_fingerprint,
        "task_count": task_count,
        "task_ids": [t["task_id"] for t in tasks],
    }
    packet_fingerprint = fingerprint_json(packet_data)

    return {
        "ok": True,
        "plan": {
            "sweep_fingerprint": sweep_fingerprint,
            "packet_fingerprint": packet_fingerprint,
            "task_count": task_count,
            "tasks": tasks,
            "recipe_fingerprint": recipe_fingerprint,
            "compile_fingerprint": compile_fingerprint,
        },
        "errors": [],
        "warnings": warnings + validation.get("warnings", []),
    }


def _apply_param_overrides(recipe: dict, overrides: Dict[str, float]) -> dict:
    """Create a copy of *recipe* with parameter defaults set to *overrides*.

    Also adds synthetic assumptions for any swept parameters that lack
    them, so the recipe remains valid through ``compile_recipe``.
    """
    task_recipe = copy.deepcopy(recipe)

    existing_assumptions = {
        a["parameter"]
        for a in task_recipe.get("assumptions", [])
        if isinstance(a, dict)
    }

    for name, value in overrides.items():
        if name in task_recipe.get("parameters", {}):
            task_recipe["parameters"][name]["default"] = value

        if name not in existing_assumptions:
            assumptions = task_recipe.setdefault("assumptions", [])
            # Ensure assumptions is a list (it should be)
            if isinstance(assumptions, list):
                assumptions.append({
                    "parameter": name,
                    "reason": f"Sweep value for {name}",
                })
                existing_assumptions.add(name)

    return task_recipe


def _sha256_hex(content: str) -> str:
    """Return ``sha256:<hex>`` for a string."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
