"""Pure-Python SimulationPlan v0.1 normalization and approval helpers."""

import copy
import hashlib
import json
import math
from typing import Any


SCHEMA_VERSION = "0.1"
MAX_TASKS = 100
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

    normalized, defaults_applied = _normalize(plan)
    task_count = _task_count(normalized)
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
    warnings = []
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
