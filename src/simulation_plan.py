"""Pure-Python SimulationPlan v0.1 normalization and approval helpers."""

import copy
import hashlib
import json
import math
from typing import Any


SCHEMA_VERSION = "0.1"
MAX_TASKS = 100

KNOWN_TOP_KEYS = {
    "schema_version",
    "intent",
    "device",
    "physics",
    "sweep",
    "execution",
    "outputs",
    "acceptance",
}

KNOWN_SECTION_KEYS = {
    "intent": {"summary"},
    "device": {"type"},
    "physics": {"materials", "source", "monitors", "boundaries", "mesh", "requirements"},
    "sweep": {
        "axis",
        "ratio_values",
        "period_values_m",
        "height_values_m",
        "fixed_height_m",
        "fixed_period_m",
    },
    "execution": {
        "resource",
        "express_mode",
        "processes",
        "capacity",
        "hide",
        "template",
    },
    "outputs": {"include_models"},
    "acceptance": {"required_quality", "required_task_success_rate"},
}

SECTION_NAMES = tuple(KNOWN_SECTION_KEYS)

TEMPLATE_INHERITED_KEYS = (
    "materials",
    "source",
    "monitors",
    "boundaries",
    "mesh",
)

DEFAULT_PLAN = {
    "schema_version": SCHEMA_VERSION,
    "intent": {"summary": ""},
    "device": {"type": "metasurface_unit_cell"},
    "physics": {
        "materials": {"strategy": "template_inherited"},
        "source": {"strategy": "template_inherited"},
        "monitors": {"strategy": "template_inherited"},
        "boundaries": {"strategy": "template_inherited"},
        "mesh": {"strategy": "template_inherited"},
        "requirements": {},
    },
    "sweep": {
        "axis": "period",
        "ratio_values": [0.2, 0.8],
        "period_values_m": [390e-9, 540e-9],
        "fixed_height_m": 700e-9,
    },
    "execution": {
        "resource": "CPU",
        "express_mode": 0,
        "processes": 1,
        "capacity": 1,
        "hide": True,
        "template": "templates/metasurface/base_model.fsp",
    },
    "outputs": {"include_models": False},
    "acceptance": {
        "required_quality": "pass",
        "required_task_success_rate": 1.0,
    },
}


def stable_json(value: dict) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def plan_fingerprint(normalized_plan: dict) -> str:
    return hashlib.sha256(
        stable_json(normalized_plan).encode("utf-8")
    ).hexdigest()


def _default(path: str, value: Any) -> dict:
    return {
        "path": path,
        "value": copy.deepcopy(value),
        "reason": "SimulationPlan v0.1 safe default.",
    }


def _section(plan: dict, name: str) -> dict:
    value = plan.get(name)
    return dict(value) if isinstance(value, dict) else {}


def _value(
    section: dict,
    key: str,
    default: Any,
    path: str,
    defaults_applied: list,
):
    if key in section:
        return copy.deepcopy(section[key])
    defaults_applied.append(_default(path, default))
    return copy.deepcopy(default)


def _normalize(plan: dict) -> tuple:
    defaults_applied = []
    intent_in = _section(plan, "intent")
    device_in = _section(plan, "device")
    physics_in = _section(plan, "physics")
    sweep_in = _section(plan, "sweep")
    execution_in = _section(plan, "execution")
    outputs_in = _section(plan, "outputs")
    acceptance_in = _section(plan, "acceptance")

    schema_version = plan.get("schema_version")
    if schema_version is None:
        schema_version = SCHEMA_VERSION
        defaults_applied.append(
            _default("schema_version", SCHEMA_VERSION)
        )

    physics = {}
    for key in TEMPLATE_INHERITED_KEYS:
        default = {"strategy": "template_inherited"}
        physics[key] = _value(
            physics_in,
            key,
            default,
            f"physics.{key}",
            defaults_applied,
        )
    physics["requirements"] = _value(
        physics_in,
        "requirements",
        {},
        "physics.requirements",
        defaults_applied,
    )

    axis = _value(
        sweep_in,
        "axis",
        "period",
        "sweep.axis",
        defaults_applied,
    )
    sweep = {
        "axis": axis,
        "ratio_values": _value(
            sweep_in,
            "ratio_values",
            [0.2, 0.8],
            "sweep.ratio_values",
            defaults_applied,
        ),
    }
    if axis == "height":
        sweep["height_values_m"] = _value(
            sweep_in,
            "height_values_m",
            [700e-9],
            "sweep.height_values_m",
            defaults_applied,
        )
        sweep["fixed_period_m"] = _value(
            sweep_in,
            "fixed_period_m",
            470e-9,
            "sweep.fixed_period_m",
            defaults_applied,
        )
    else:
        sweep["period_values_m"] = _value(
            sweep_in,
            "period_values_m",
            [390e-9, 540e-9],
            "sweep.period_values_m",
            defaults_applied,
        )
        sweep["fixed_height_m"] = _value(
            sweep_in,
            "fixed_height_m",
            700e-9,
            "sweep.fixed_height_m",
            defaults_applied,
        )

    normalized = {
        "schema_version": schema_version,
        "intent": {
            "summary": _value(
                intent_in,
                "summary",
                "",
                "intent.summary",
                defaults_applied,
            )
        },
        "device": {
            "type": _value(
                device_in,
                "type",
                "metasurface_unit_cell",
                "device.type",
                defaults_applied,
            )
        },
        "physics": physics,
        "sweep": sweep,
        "execution": {
            "resource": _value(
                execution_in,
                "resource",
                "CPU",
                "execution.resource",
                defaults_applied,
            ),
            "express_mode": _value(
                execution_in,
                "express_mode",
                0,
                "execution.express_mode",
                defaults_applied,
            ),
            "processes": _value(
                execution_in,
                "processes",
                1,
                "execution.processes",
                defaults_applied,
            ),
            "capacity": _value(
                execution_in,
                "capacity",
                1,
                "execution.capacity",
                defaults_applied,
            ),
            "hide": _value(
                execution_in,
                "hide",
                True,
                "execution.hide",
                defaults_applied,
            ),
            "template": _value(
                execution_in,
                "template",
                "templates/metasurface/base_model.fsp",
                "execution.template",
                defaults_applied,
            ),
        },
        "outputs": {
            "include_models": _value(
                outputs_in,
                "include_models",
                False,
                "outputs.include_models",
                defaults_applied,
            )
        },
        "acceptance": {
            "required_quality": _value(
                acceptance_in,
                "required_quality",
                "pass",
                "acceptance.required_quality",
                defaults_applied,
            ),
            "required_task_success_rate": _value(
                acceptance_in,
                "required_task_success_rate",
                1.0,
                "acceptance.required_task_success_rate",
                defaults_applied,
            ),
        },
    }
    return normalized, defaults_applied


def _task_count(plan: dict) -> int:
    sweep = plan["sweep"]
    y_values = (
        sweep["height_values_m"]
        if sweep["axis"] == "height"
        else sweep["period_values_m"]
    )
    return len(sweep["ratio_values"]) * len(y_values)


def _approval_summary(
    plan: dict,
    fingerprint: str,
    task_count: int,
    defaults_applied: list,
    assumptions: list,
    warnings: list,
) -> dict:
    return {
        "intent": plan["intent"]["summary"],
        "device_type": plan["device"]["type"],
        "template": plan["execution"]["template"],
        "template_inherited": list(TEMPLATE_INHERITED_KEYS),
        "sweep": copy.deepcopy(plan["sweep"]),
        "task_count": task_count,
        "execution": copy.deepcopy(plan["execution"]),
        "outputs": copy.deepcopy(plan["outputs"]),
        "acceptance": copy.deepcopy(plan["acceptance"]),
        "defaults_applied": copy.deepcopy(defaults_applied),
        "assumptions": copy.deepcopy(assumptions),
        "warnings": copy.deepcopy(warnings),
        "plan_fingerprint": fingerprint,
    }


def _error(error_type: str, message: str, details=None) -> dict:
    return {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
            "details": details or {},
        },
    }


def _finite_positive(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _validate_unique_numbers(
    values,
    *,
    path: str,
    predicate,
) -> dict | None:
    if not isinstance(values, list) or not values:
        return _error(
            "plan_validation_error",
            f"{path} must be a non-empty list.",
            {"path": path},
        )
    if any(not predicate(value) for value in values):
        return _error(
            "plan_validation_error",
            f"{path} contains an invalid value.",
            {"path": path, "values": values},
        )
    if len(set(values)) != len(values):
        return _error(
            "plan_validation_error",
            f"{path} must not contain duplicates.",
            {"path": path, "values": values},
        )
    return None


def _validate_normalized_plan(plan: dict) -> dict | None:
    if plan["schema_version"] != SCHEMA_VERSION:
        return _error(
            "plan_validation_error",
            f"schema_version must be {SCHEMA_VERSION}.",
        )
    if plan["device"]["type"] != "metasurface_unit_cell":
        return _error(
            "unsupported_plan_feature",
            "SimulationPlan v0.1 only supports metasurface_unit_cell.",
            {"device_type": plan["device"]["type"]},
        )
    for key in TEMPLATE_INHERITED_KEYS:
        if plan["physics"][key] != {"strategy": "template_inherited"}:
            return _error(
                "unsupported_plan_feature",
                f"physics.{key} must use template_inherited.",
                {"path": f"physics.{key}"},
            )
    if not isinstance(plan["physics"]["requirements"], dict):
        return _error(
            "plan_validation_error",
            "physics.requirements must be an object.",
        )

    sweep = plan["sweep"]
    if sweep["axis"] not in {"period", "height"}:
        return _error(
            "plan_validation_error",
            "sweep.axis must be period or height.",
        )
    ratio_error = _validate_unique_numbers(
        sweep["ratio_values"],
        path="sweep.ratio_values",
        predicate=lambda value: (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and 0 < float(value) < 1
        ),
    )
    if ratio_error:
        return ratio_error

    if sweep["axis"] == "period":
        y_path = "sweep.period_values_m"
        y_values = sweep["period_values_m"]
        fixed_path = "sweep.fixed_height_m"
        fixed_value = sweep["fixed_height_m"]
    else:
        y_path = "sweep.height_values_m"
        y_values = sweep["height_values_m"]
        fixed_path = "sweep.fixed_period_m"
        fixed_value = sweep["fixed_period_m"]
    y_error = _validate_unique_numbers(
        y_values,
        path=y_path,
        predicate=_finite_positive,
    )
    if y_error:
        return y_error
    if not _finite_positive(fixed_value):
        return _error(
            "plan_validation_error",
            f"{fixed_path} must be a positive finite number.",
        )

    execution = plan["execution"]
    if execution["resource"] != "CPU":
        return _error(
            "unsupported_plan_feature",
            "SimulationPlan v0.1 only supports CPU.",
        )
    if execution["express_mode"] != 0:
        return _error(
            "plan_validation_error",
            "CPU requires execution.express_mode=0.",
        )
    for key in ("processes", "capacity"):
        value = execution[key]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return _error(
                "plan_validation_error",
                f"execution.{key} must be a positive integer.",
            )
    if not isinstance(execution["hide"], bool):
        return _error(
            "plan_validation_error",
            "execution.hide must be boolean.",
        )
    if (
        not isinstance(execution["template"], str)
        or not execution["template"].strip()
    ):
        return _error(
            "plan_validation_error",
            "execution.template must be a non-empty path string.",
        )

    acceptance = plan["acceptance"]
    if acceptance["required_quality"] not in {"pass", "warning", "fail"}:
        return _error(
            "plan_validation_error",
            "acceptance.required_quality is invalid.",
        )
    rate = acceptance["required_task_success_rate"]
    if (
        not isinstance(rate, (int, float))
        or isinstance(rate, bool)
        or not math.isfinite(float(rate))
        or not 0 <= float(rate) <= 1
    ):
        return _error(
            "plan_validation_error",
            "required_task_success_rate must be between 0 and 1.",
        )
    return None


def _validate_input_structure(plan: dict) -> dict | None:
    """Reject non-object sections and unknown fields before normalization.

    Returns None when the input structure is acceptable, or an error dict.
    """
    unknown = []

    for key in plan:
        if key not in KNOWN_TOP_KEYS:
            unknown.append(key)
        elif key in SECTION_NAMES:
            value = plan[key]
            if not isinstance(value, dict):
                return _error(
                    "plan_validation_error",
                    f"{key} must be a JSON object.",
                    {"path": key, "received_type": type(value).__name__},
                )
            known_keys = KNOWN_SECTION_KEYS[key]
            for sub_key in value:
                if sub_key not in known_keys:
                    unknown.append(f"{key}.{sub_key}")

    if unknown:
        return _error(
            "plan_validation_error",
            "Input contains unknown fields.",
            {
                "unknown_fields": [
                    {"path": path, "message": f"'{path}' is not a recognised SimulationPlan v0.1 field."}
                    for path in unknown
                ],
            },
        )
    return None


PERIOD_ONLY_FIELDS = {"period_values_m", "fixed_height_m"}
HEIGHT_ONLY_FIELDS = {"height_values_m", "fixed_period_m"}


def _validate_sweep_axis_fields(plan: dict) -> dict | None:
    """Reject sweep fields that conflict with the declared axis."""
    sweep_in = plan.get("sweep")
    if not isinstance(sweep_in, dict):
        return None
    axis = sweep_in.get("axis", "period")
    if axis not in {"period", "height"}:
        return None

    conflicting = PERIOD_ONLY_FIELDS if axis == "height" else HEIGHT_ONLY_FIELDS
    invalid = [
        {"path": f"sweep.{key}", "message": f"sweep.{key} is not valid when axis={axis}."}
        for key in sorted(conflicting)
        if key in sweep_in
    ]
    if invalid:
        return _error(
            "plan_validation_error",
            f"Sweep axis={axis} conflicts with fields meant for the other axis.",
            {"invalid_fields": invalid},
        )
    return None


def validate_simulation_plan(plan: dict) -> dict:
    if not isinstance(plan, dict):
        return {
            "ok": False,
            "error": {
                "type": "plan_validation_error",
                "message": "SimulationPlan must be a JSON object.",
                "details": {},
            },
        }

    input_error = _validate_input_structure(plan)
    if input_error:
        return input_error

    axis_error = _validate_sweep_axis_fields(plan)
    if axis_error:
        return axis_error

    normalized, defaults_applied = _normalize(plan)

    validation_error = _validate_normalized_plan(normalized)
    if validation_error:
        return validation_error

    task_count = _task_count(normalized)
    if task_count > MAX_TASKS:
        return _error(
            "task_budget_exceeded",
            f"SimulationPlan v0.1 allows at most {MAX_TASKS} tasks.",
            {"task_count": task_count, "maximum": MAX_TASKS},
        )

    fingerprint = plan_fingerprint(normalized)
    assumptions = [
        {
            "path": "physics",
            "message": (
                "Materials, source, monitors, boundaries, and mesh are "
                "inherited from the selected .fsp template."
            ),
        }
    ]
    requirements = normalized["physics"]["requirements"]
    warnings = []
    if requirements:
        warnings.append(
            {
                "type": "template_requirement_unverified",
                "message": (
                    "physics.requirements are recorded for template-contract "
                    "verification; the compiler will not modify the .fsp."
                ),
                "details": copy.deepcopy(requirements),
            }
        )
    return {
        "ok": True,
        "normalized_plan": normalized,
        "plan_fingerprint": fingerprint,
        "task_count": task_count,
        "defaults_applied": defaults_applied,
        "assumptions": assumptions,
        "warnings": warnings,
        "errors": [],
        "approval_summary": _approval_summary(
            normalized,
            fingerprint,
            task_count,
            defaults_applied,
            assumptions,
            warnings,
        ),
    }


def approve_simulation_plan(plan: dict, fingerprint: str) -> dict:
    validated = validate_simulation_plan(plan)
    if not validated["ok"]:
        return validated
    actual = validated["plan_fingerprint"]
    if fingerprint != actual:
        return _error(
            "plan_fingerprint_mismatch",
            "The submitted fingerprint does not match the normalized Plan.",
            {"expected": actual, "received": fingerprint},
        )
    return {
        "ok": True,
        "approval": {
            "approved": True,
            "approved_for": "simulation_plan",
            "schema_version": SCHEMA_VERSION,
            "plan_fingerprint": actual,
        },
    }


def _approval_matches(approval, approved_for: str, fingerprint: str) -> bool:
    return (
        isinstance(approval, dict)
        and approval.get("approved") is True
        and approval.get("approved_for") == approved_for
        and approval.get("plan_fingerprint") == fingerprint
    )


def _requirements_match(requirements: dict, declared: dict) -> bool:
    if not isinstance(declared, dict):
        return False
    return all(declared.get(key) == value for key, value in requirements.items())


def validate_execution_approvals(
    validated_plan: dict,
    *,
    mode: str,
    plan_approval,
    real_run_approval=None,
    template_contract=None,
) -> dict:
    if not validated_plan.get("ok"):
        return validated_plan
    if mode not in {"mock", "real"}:
        return _error(
            "plan_validation_error",
            "mode must be mock or real.",
            {"mode": mode},
        )

    fingerprint = validated_plan["plan_fingerprint"]
    if not _approval_matches(
        plan_approval,
        "simulation_plan",
        fingerprint,
    ):
        error_type = (
            "plan_fingerprint_mismatch"
            if isinstance(plan_approval, dict)
            else "plan_approval_required"
        )
        return _error(
            error_type,
            "A matching SimulationPlan approval is required.",
        )
    if mode == "mock":
        return {"ok": True}

    if (
        isinstance(real_run_approval, dict)
        and real_run_approval.get("approved") is True
        and real_run_approval.get("approved_for") == "real_run"
        and real_run_approval.get("plan_fingerprint") != fingerprint
    ):
        return _error(
            "plan_fingerprint_mismatch",
            "The real-run approval targets a different Plan.",
        )
    if not _approval_matches(real_run_approval, "real_run", fingerprint):
        return _error(
            "real_run_approval_required",
            "A matching real-run approval is required.",
        )
    if not isinstance(template_contract, dict):
        return _error(
            "template_contract_required",
            "A verified template contract is required for real mode.",
        )

    plan = validated_plan["normalized_plan"]
    execution = plan["execution"]
    contract_ok = (
        template_contract.get("path") == execution["template"]
        and template_contract.get("sha256")
        == real_run_approval.get("template_sha256")
        and template_contract.get("resource") == "CPU"
        and template_contract.get("express_mode") == 0
        and template_contract.get("physics_strategy")
        == "template_inherited"
        and _requirements_match(
            plan["physics"]["requirements"],
            template_contract.get("declared_physics", {}),
        )
    )
    if not contract_ok:
        return _error(
            "template_contract_required",
            "Template contract does not match the approved Plan.",
        )
    return {"ok": True}
