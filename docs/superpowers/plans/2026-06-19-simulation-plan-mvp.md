# SimulationPlan MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic `SimulationPlan v0.1` layer that discloses defaults, fingerprints and approves plans, compiles approved metasurface plans into the existing persistent `/jobs/*` workflow, and rejects resume when the real template changes.

**Architecture:** Keep natural-language interpretation in Claude Code/Codex. Add a pure-Python plan normalizer/validator, a focused metasurface compiler, and three MCP tools in front of the already verified `JobStore` and `NativeSweepRunner`. Preserve the existing RPC API; only harden `JobStore.resume()` with template SHA-256 verification.

**Tech Stack:** Python 3.10+, standard library `copy/hashlib/json/math/pathlib`, FastMCP, existing `RpcClient`, Flask RPC API v1, pytest.

---

## Scope Guard

- Do not start Windows services or FDTD.
- Do not modify the `.fsp` template.
- Do not add natural-language parsing to Python.
- Do not add a recipe registry or a second device.
- Do not add GPU support.
- Do not change the existing `/jobs/*` HTTP contract.
- Keep existing `fdtd_metasurface_sweep_*` tools registered.
- Use TDD for every behavior change.

## File Map

- Create `src/simulation_plan.py`
  - Own defaults, normalization, validation, warnings, stable fingerprinting, approval summaries, Plan approval checks, real-run approval checks, and template-contract matching.
- Create `src/plan_compilers/__init__.py`
  - Mark the compiler package.
- Create `src/plan_compilers/metasurface.py`
  - Compile a normalized metasurface Plan into the existing `/jobs/*` request.
- Create `src/tools/plans.py`
  - Register `fdtd_simulation_plan_validate`, `fdtd_simulation_plan_approve`, and `fdtd_simulation_plan_start`.
- Modify `src/server.py`
  - Register the new MCP module and update the entry-point description.
- Modify `src/job_store.py`
  - Verify real metasurface template SHA-256 before resume.
- Create `tests/test_simulation_plan.py`
  - Test defaults, validation, warnings, fingerprints, approvals, and template contracts.
- Create `tests/test_metasurface_plan_compiler.py`
  - Test period/height request compilation and approval propagation.
- Create `tests/test_mcp_plan_tools.py`
  - Test MCP behavior with fake RPC.
- Modify `tests/test_mcp_registration.py`
  - Lock the three new tool names.
- Modify `tests/test_job_store.py`
  - Test resume fingerprint acceptance and conflicts.
- Modify `README.md`, `TECH_STACK.md`, `docs/RPC_API_V1.md`, `SOP.md`, `DEV_LOG.md`, and `src/knowledge/prompts/workflow.md`
  - Document the natural-language Plan workflow and current limitations.

---

## Task 1: Add SimulationPlan defaults, normalization, and fingerprinting

**Files:**
- Create: `src/simulation_plan.py`
- Create: `tests/test_simulation_plan.py`

- [ ] **Step 1: Write failing tests for the default normalized Plan**

Create `tests/test_simulation_plan.py`:

```python
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
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation_plan.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'src.simulation_plan'`.

- [ ] **Step 3: Implement stable JSON, defaults, and normalization**

Create `src/simulation_plan.py`:

```python
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
```

- [ ] **Step 4: Run the tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation_plan.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/simulation_plan.py tests/test_simulation_plan.py
git commit -m "feat: add simulation plan normalization"
```

---

## Task 2: Add strict Plan validation and physics-requirement warnings

**Files:**
- Modify: `src/simulation_plan.py`
- Modify: `tests/test_simulation_plan.py`

- [ ] **Step 1: Add failing validation tests**

Append to `tests/test_simulation_plan.py`:

```python
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
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation_plan.py -q
```

Expected: failures because invalid values are currently accepted and physics requirements do not create warnings.

- [ ] **Step 3: Add minimal validation helpers**

Add to `src/simulation_plan.py` before `validate_simulation_plan`:

```python
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
```

Then update `validate_simulation_plan` immediately after `_normalize(plan)`:

```python
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
```

Replace `warnings = []` with:

```python
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
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation_plan.py -q
```

Expected: all tests in `tests/test_simulation_plan.py` pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/simulation_plan.py tests/test_simulation_plan.py
git commit -m "feat: validate simulation plans"
```

---

## Task 3: Add Plan approvals, template-contract checks, and metasurface compilation

**Files:**
- Modify: `src/simulation_plan.py`
- Create: `src/plan_compilers/__init__.py`
- Create: `src/plan_compilers/metasurface.py`
- Create: `tests/test_metasurface_plan_compiler.py`
- Modify: `tests/test_simulation_plan.py`

- [ ] **Step 1: Write failing approval tests**

Append to `tests/test_simulation_plan.py`:

```python
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
```

- [ ] **Step 2: Write failing compiler tests**

Create `tests/test_metasurface_plan_compiler.py`:

```python
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
```

- [ ] **Step 3: Run approval and compiler tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation_plan.py tests/test_metasurface_plan_compiler.py -q
```

Expected: import errors for the missing approval functions and compiler module.

- [ ] **Step 4: Implement approval helpers**

Append to `src/simulation_plan.py`:

```python
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
```

- [ ] **Step 5: Implement the focused metasurface compiler**

Create `src/plan_compilers/__init__.py`:

```python
"""SimulationPlan compilers."""
```

Create `src/plan_compilers/metasurface.py`:

```python
"""Compile normalized metasurface SimulationPlans to RPC API v1 jobs."""


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
    return request
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation_plan.py tests/test_metasurface_plan_compiler.py -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit Task 3**

```bash
git add src/simulation_plan.py src/plan_compilers tests/test_simulation_plan.py tests/test_metasurface_plan_compiler.py
git commit -m "feat: approve and compile simulation plans"
```

---

## Task 4: Add MCP SimulationPlan tools

**Files:**
- Create: `src/tools/plans.py`
- Create: `tests/test_mcp_plan_tools.py`

- [ ] **Step 1: Write failing MCP tool tests**

Create `tests/test_mcp_plan_tools.py`:

```python
from src.tools.plans import register_plan_tools


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FakeRpc:
    def __init__(self):
        self.calls = []

    def jobs_start(self, request):
        self.calls.append(("jobs_start", request))
        return {
            "ok": True,
            "job_id": "job_mock",
            "task_count": 4,
            "summary": {
                "quality_report": {"conclusion": "pass"},
                "evidence": {"index": "evidence/index.json"},
            },
        }


def registered_tools():
    mcp = FakeMcp()
    rpc = FakeRpc()
    register_plan_tools(mcp, rpc)
    return mcp.tools, rpc


def test_validate_and_approve_are_local_only():
    tools, rpc = registered_tools()

    validated = tools["fdtd_simulation_plan_validate"]({})
    approved = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )

    assert validated["ok"] is True
    assert approved["ok"] is True
    assert rpc.calls == []


def test_mock_start_requires_plan_approval_without_rpc_call():
    tools, rpc = registered_tools()

    response = tools["fdtd_simulation_plan_start"](
        plan={},
        plan_approval=None,
        mode="mock",
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "plan_approval_required"
    assert rpc.calls == []


def test_approved_mock_compiles_and_calls_jobs_start_once():
    tools, rpc = registered_tools()
    validated = tools["fdtd_simulation_plan_validate"]({})
    approval = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]

    response = tools["fdtd_simulation_plan_start"](
        plan=validated["normalized_plan"],
        plan_approval=approval,
        mode="mock",
    )

    assert response["ok"] is True
    assert response["job_id"] == "job_mock"
    assert len(rpc.calls) == 1
    request = rpc.calls[0][1]
    assert request["mode"] == "mock"
    assert request["job_type"] == "metasurface-sweep"
    assert "approval" not in request


def test_changed_plan_rejects_old_approval_without_rpc_call():
    tools, rpc = registered_tools()
    validated = tools["fdtd_simulation_plan_validate"]({})
    approval = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]

    response = tools["fdtd_simulation_plan_start"](
        plan={"sweep": {"ratio_values": [0.2, 0.5]}},
        plan_approval=approval,
        mode="mock",
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "plan_fingerprint_mismatch"
    assert rpc.calls == []


def test_real_is_locally_rejected_without_second_approval():
    tools, rpc = registered_tools()
    validated = tools["fdtd_simulation_plan_validate"]({})
    approval = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]

    response = tools["fdtd_simulation_plan_start"](
        plan=validated["normalized_plan"],
        plan_approval=approval,
        mode="real",
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "real_run_approval_required"
    assert rpc.calls == []
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_plan_tools.py -q
```

Expected: collection fails because `src.tools.plans` does not exist.

- [ ] **Step 3: Implement minimal MCP tools**

Create `src/tools/plans.py`:

```python
"""MCP tools for SimulationPlan validation, approval, and execution."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..plan_compilers.metasurface import compile_metasurface_plan
from ..rpc_client.client import RpcClient
from ..simulation_plan import (
    approve_simulation_plan,
    validate_execution_approvals,
    validate_simulation_plan,
)


def register_plan_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register deterministic SimulationPlan tools."""

    @mcp.tool()
    def fdtd_simulation_plan_validate(plan: dict) -> dict:
        """
        Normalize and validate a SimulationPlan without creating a job.

        Returns disclosed defaults, assumptions, warnings, task count,
        approval summary, and a deterministic SHA-256 fingerprint.
        """
        return validate_simulation_plan(plan)

    @mcp.tool()
    def fdtd_simulation_plan_approve(
        plan: dict,
        plan_fingerprint: str,
    ) -> dict:
        """
        Create a stateless plan approval after the user confirms the summary.

        The supplied fingerprint must match the current normalized Plan.
        """
        return approve_simulation_plan(plan, plan_fingerprint)

    @mcp.tool()
    def fdtd_simulation_plan_start(
        plan: dict,
        plan_approval: Optional[dict],
        mode: str = "mock",
        real_run_approval: Optional[dict] = None,
        template_contract: Optional[dict] = None,
    ) -> dict:
        """
        Start an approved persistent metasurface job.

        Mock requires a matching SimulationPlan approval. Real additionally
        requires a matching real-run approval and verified template contract.
        """
        validated = validate_simulation_plan(plan)
        if not validated["ok"]:
            return validated
        approval_check = validate_execution_approvals(
            validated,
            mode=mode,
            plan_approval=plan_approval,
            real_run_approval=real_run_approval,
            template_contract=template_contract,
        )
        if not approval_check["ok"]:
            return approval_check
        request = compile_metasurface_plan(
            validated["normalized_plan"],
            validated["plan_fingerprint"],
            mode=mode,
        )
        return rpc.jobs_start(request)
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_plan_tools.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/tools/plans.py tests/test_mcp_plan_tools.py
git commit -m "feat: add simulation plan mcp tools"
```

---

## Task 5: Register Plan tools and lock the MCP surface

**Files:**
- Modify: `src/server.py`
- Modify: `tests/test_mcp_registration.py`

- [ ] **Step 1: Update the registration test first**

In `tests/test_mcp_registration.py`, add these names to the expected set:

```python
        "fdtd_simulation_plan_validate",
        "fdtd_simulation_plan_approve",
        "fdtd_simulation_plan_start",
```

- [ ] **Step 2: Run registration test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_registration.py -q
```

Expected: failure because the three Plan tools are not registered.

- [ ] **Step 3: Register the module in `src/server.py`**

Add the import:

```python
from .tools.plans import register_plan_tools
```

Call it immediately before the lower-level job tools:

```python
    register_simulation_tools(mcp, rpc)
    register_plan_tools(mcp, rpc)
    register_job_tools(mcp, rpc)
```

Update the module docstring to state:

```text
Mac 端 MCP Server，先把自然语言需求编译为可审批的 SimulationPlan，
再通过 FDTD 持久 job 状态机调用 Windows RPC Server。
```

- [ ] **Step 4: Run registration and Plan tool tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_registration.py tests/test_mcp_plan_tools.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add src/server.py tests/test_mcp_registration.py
git commit -m "feat: register simulation plan tools"
```

---

## Task 6: Reject real metasurface resume when the template fingerprint changes

**Files:**
- Modify: `src/job_store.py`
- Modify: `tests/test_job_store.py`

- [ ] **Step 1: Write failing resume fingerprint tests**

Append to `tests/test_job_store.py`:

```python
import hashlib


def create_real_metasurface_job_with_template(store, tmp_path):
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"original-template")
    job = store.enqueue(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "template": str(template),
                "config": {
                    "RATIO_LIST": [0.2],
                    "PERIOD_LIST": [390e-9],
                },
            },
            "approval": {
                "approved": True,
                "approved_for": "real_run",
            },
        }
    )
    store.update_manifest(
        job["job_id"],
        {
            "template": {
                "path": str(template),
                "sha256": hashlib.sha256(
                    template.read_bytes()
                ).hexdigest(),
                "size_bytes": template.stat().st_size,
                "modified_at": template.stat().st_mtime,
            }
        },
    )
    return job, template


def test_real_metasurface_resume_allows_unchanged_template(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job, _ = create_real_metasurface_job_with_template(store, tmp_path)

    resumed = store.resume(job["job_id"])

    assert resumed["task_ids"] == ["task_0001"]


def test_real_metasurface_resume_rejects_changed_template(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job, template = create_real_metasurface_job_with_template(store, tmp_path)
    template.write_bytes(b"changed-template")

    with pytest.raises(JobError) as error:
        store.resume(job["job_id"])

    assert error.value.error_type == "resume_conflict"
    assert error.value.status_code == 409


def test_real_metasurface_resume_rejects_missing_template(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job, template = create_real_metasurface_job_with_template(store, tmp_path)
    template.unlink()

    with pytest.raises(JobError) as error:
        store.resume(job["job_id"])

    assert error.value.error_type == "resume_conflict"


def test_old_real_metasurface_job_without_fingerprint_cannot_resume(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    job = store.enqueue(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {"template": str(template)},
            "approval": {
                "approved": True,
                "approved_for": "real_run",
            },
        }
    )

    with pytest.raises(JobError) as error:
        store.resume(job["job_id"])

    assert error.value.error_type == "resume_conflict"


def test_mock_resume_does_not_require_template_fingerprint(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.plan({"mode": "mock", "job_type": "metasurface-sweep"})

    resumed = store.resume(job["job_id"])

    assert len(resumed["task_ids"]) == 4
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py -q
```

Expected: changed, missing, and unrecorded templates are currently accepted.

- [ ] **Step 3: Add resume fingerprint verification**

Add `Path` is already imported. Add this private method to `JobStore` before `resume`:

```python
    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _verify_resume_template(self, job_id: str) -> None:
        job_dir = self._job_dir(job_id)
        manifest = self._read_json(job_dir / "manifest.json")
        if (
            manifest.get("mode") != "real"
            or manifest.get("job_type") != "metasurface-sweep"
        ):
            return

        template_record = manifest.get("template") or {}
        expected_sha = template_record.get("sha256")
        request_data = self._read_json(job_dir / "inputs" / "request.json")
        template_path = Path(request_data["sweep"]["template"])
        if not expected_sha:
            raise JobError(
                "resume_conflict",
                "Real metasurface job has no recorded template fingerprint.",
                409,
                {"job_id": job_id},
            )
        if not template_path.is_file():
            raise JobError(
                "resume_conflict",
                "Sweep template is missing; create a new job.",
                409,
                {"job_id": job_id, "template": str(template_path)},
            )
        actual_sha = self._file_sha256(template_path)
        if actual_sha != expected_sha:
            raise JobError(
                "resume_conflict",
                "Sweep template changed; create a new job.",
                409,
                {
                    "job_id": job_id,
                    "template": str(template_path),
                    "expected_sha256": expected_sha,
                    "actual_sha256": actual_sha,
                },
            )
```

Call it at the beginning of `resume`:

```python
    def resume(...):
        self._verify_resume_template(job_id)
        tasks = self._tasks(job_id)
```

- [ ] **Step 4: Run JobStore and RPC resume tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py tests/test_rpc_server_jobs.py -q
```

Expected: all selected tests pass. Existing mock and geometry resume behavior remains unchanged.

- [ ] **Step 5: Commit Task 6**

```bash
git add src/job_store.py tests/test_job_store.py
git commit -m "fix: protect resume with template fingerprint"
```

---

## Task 7: Add an offline end-to-end approved mock test

**Files:**
- Create: `tests/test_simulation_plan_workflow.py`

- [ ] **Step 1: Write the workflow test**

Create `tests/test_simulation_plan_workflow.py`:

```python
from rpc_server import create_app
from src.job_store import JobStore
from src.tools.plans import register_plan_tools


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FlaskRpcAdapter:
    def __init__(self, client):
        self.client = client
        self.calls = []

    def jobs_start(self, request):
        self.calls.append(request)
        return self.client.post("/jobs/start", json=request).get_json()


class FakeSession:
    @property
    def is_connected(self):
        return False

    def status(self):
        return {"connected": False, "version": None, "model_file": None}


def test_natural_language_agent_plan_to_approved_persistent_mock(tmp_path):
    app = create_app(
        FakeSession(),
        job_store=JobStore(tmp_path / "jobs", code_version="test-sha"),
    )
    app.config.update(TESTING=True)
    rpc = FlaskRpcAdapter(app.test_client())
    mcp = FakeMcp()
    register_plan_tools(mcp, rpc)

    # Claude/Codex has translated:
    # "Use CPU to sweep metasurface unit-cell ratio and period."
    draft = {
        "intent": {
            "summary": (
                "Use CPU to sweep metasurface unit-cell ratio and period."
            )
        },
        "execution": {"resource": "CPU"},
    }
    validated = mcp.tools["fdtd_simulation_plan_validate"](draft)
    assert validated["ok"] is True
    assert validated["task_count"] == 4
    assert validated["defaults_applied"]
    assert validated["assumptions"]

    approved = mcp.tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )
    response = mcp.tools["fdtd_simulation_plan_start"](
        plan=validated["normalized_plan"],
        plan_approval=approved["approval"],
        mode="mock",
    )

    assert response["ok"] is True
    assert response["task_count"] == 4
    assert response["summary"]["task_counts"]["succeeded"] == 4
    assert response["summary"]["quality_report"]["conclusion"] == "pass"
    assert response["summary"]["evidence"]["download_policy"][
        "default_payload"
    ] == "evidence-only"
    assert all(item["synthetic"] for item in response["summary"]["results"])
    assert len(rpc.calls) == 1
```

- [ ] **Step 2: Run the workflow test**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation_plan_workflow.py -q
```

Expected: `1 passed`.

- [ ] **Step 3: Run all Phase 5 focused tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_simulation_plan.py \
  tests/test_metasurface_plan_compiler.py \
  tests/test_mcp_plan_tools.py \
  tests/test_mcp_registration.py \
  tests/test_job_store.py \
  tests/test_rpc_server_jobs.py \
  tests/test_simulation_plan_workflow.py
```

Expected: all selected tests pass.

- [ ] **Step 4: Commit Task 7**

```bash
git add tests/test_simulation_plan_workflow.py
git commit -m "test: verify approved simulation plan mock workflow"
```

---

## Task 8: Update documentation and agent workflow guidance

**Files:**
- Modify: `README.md`
- Modify: `TECH_STACK.md`
- Modify: `docs/RPC_API_V1.md`
- Modify: `SOP.md`
- Modify: `DEV_LOG.md`
- Modify: `src/knowledge/prompts/workflow.md`

- [ ] **Step 1: Update `README.md` current state**

Replace the old “主要下一步” resume-only note with:

```markdown
- SimulationPlan v0.1 已支持 metasurface unit-cell：默认值披露、任务预算、
  SHA-256 指纹、Plan 审批、mock 编译和 MCP 执行。
- mock 前必须批准默认值和假设；real 还需要匹配同一 Plan 指纹的真实运行
  审批与模板契约。
- real metasurface resume 会重新校验模板 SHA-256；模板变化时拒绝恢复。
- 当前下一步：在 Windows 模板检查流程中生成可审计 template contract，
  再进行 SimulationPlan real 端到端验证。
```

Add the three Plan tools to the MCP tool overview and mark `fdtd_metasurface_sweep_*` as lower-level tools.

- [ ] **Step 2: Update `TECH_STACK.md`**

Add to the Mac-side architecture:

```text
自然语言 -> Agent 生成 Plan JSON -> SimulationPlan validator/compiler
-> MCP Plan tools -> RpcClient.jobs_* -> Windows /jobs/*
```

Add a tool row:

```markdown
| SimulationPlan | `fdtd_simulation_plan_validate`, `fdtd_simulation_plan_approve`, `fdtd_simulation_plan_start` |
```

Document:

- `SimulationPlan v0.1` supports only `metasurface_unit_cell`.
- CPU requires `EXPRESS_MODE=0`.
- materials/source/monitors/boundaries/mesh are template-inherited.
- task budget is 100.
- Python does not parse natural language.

- [ ] **Step 3: Update `docs/RPC_API_V1.md`**

Do not add new HTTP routes. Add an MCP-layer section:

```markdown
## SimulationPlan MCP layer

SimulationPlan validation and approval run locally in the Mac MCP process.
Only an approved compiled request reaches the existing `/jobs/start` route.
The RPC Server continues to enforce its existing `real_run` approval as the
final service-side guard.
```

Update known limitations to state template-fingerprint resume protection is implemented.

- [ ] **Step 4: Update `SOP.md`**

In SOP-007, make the executable order explicit:

1. Agent converts natural language to Plan JSON.
2. Call `fdtd_simulation_plan_validate`.
3. Show `defaults_applied`, assumptions, warnings, task count, and fingerprint.
4. Obtain explicit user approval.
5. Call `fdtd_simulation_plan_approve`.
6. Start mock with the returned Plan approval.
7. For real, separately generate a template contract and real-run summary.
8. Never reuse approval after Plan or template fingerprint changes.

In SOP-008, state that real metasurface resume returns `resume_conflict` for missing or changed template fingerprints.

- [ ] **Step 5: Update the embedded workflow guide**

In `src/knowledge/prompts/workflow.md`, replace the target-only SimulationPlan language with the now-supported flow and explicitly state:

```text
The language model writes Plan JSON. Python validates and compiles it.
Do not send a natural-language string to the RPC Server.
```

Keep real execution marked as requiring separate approval and template contract.

- [ ] **Step 6: Record implementation in `DEV_LOG.md`**

Append a dated entry:

```markdown
## 2026-06-19 - SimulationPlan MVP

- 目标：把自然语言 Agent 与已验证 `/jobs/*` 执行链之间增加可审批的结构化计划层。
- 实现：
  - SimulationPlan v0.1 默认值、校验、任务预算和稳定 SHA-256。
  - Plan 审批、real 双层审批和模板契约本地防线。
  - metasurface period/height compiler。
  - 三个 MCP Plan 工具。
  - real metasurface resume 模板指纹保护。
  - 离线 approved mock 端到端测试。
- 限制：未启动真实 FDTD；材料、光源、监视器、边界和网格仍继承模板。
```

- [ ] **Step 7: Check documentation consistency**

Run:

```bash
rg -n "SimulationPlan|template contract|resume_conflict|fdtd_simulation_plan_" \
  README.md TECH_STACK.md docs/RPC_API_V1.md SOP.md DEV_LOG.md \
  src/knowledge/prompts/workflow.md
```

Expected: every operational document describes the same Plan → approval → mock/real order.

- [ ] **Step 8: Commit Task 8**

```bash
git add README.md TECH_STACK.md docs/RPC_API_V1.md SOP.md DEV_LOG.md src/knowledge/prompts/workflow.md
git commit -m "docs: document simulation plan workflow"
```

---

## Task 9: Final verification and project-state audit

**Files:**
- Modify only if verification reveals a Phase 5 defect.

- [ ] **Step 1: Run compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exit code `0`, no output.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. Record the actual count in `DEV_LOG.md`.

- [ ] **Step 3: Run scope and contract scans**

Run:

```bash
! rg -n "localhost:5001|127\\.0\\.0\\.1:5001|5001" \
  src/server.py README.md TECH_STACK.md docs/RPC_API_V1.md .mcp.json
```

Expected: no matches.

Run:

```bash
! rg -n "fdtd_simulation_plan_.*sweep_|/sweep/" \
  src/tools/plans.py src/plan_compilers tests/test_mcp_plan_tools.py
```

Expected: no legacy `/sweep/*` dependency in the new Plan path.

Run:

```bash
rg -n "EXPRESS_MODE.*0|express_mode.*0|resource.*CPU" \
  src/simulation_plan.py src/plan_compilers/metasurface.py \
  tests/test_simulation_plan.py tests/test_metasurface_plan_compiler.py
```

Expected: Plan defaults and compiler remain CPU-safe.

- [ ] **Step 4: Confirm no real execution occurred**

Run:

```bash
git status -sb
git log --oneline -12
```

Verify:

- no generated `.fsp` was added;
- no Windows service or FDTD command was invoked;
- only Phase 5 code, tests, and docs changed;
- each task has its own commit.

- [ ] **Step 5: Record the exact verification output**

Copy the final pytest summary line printed by Step 2 verbatim into the Phase 5
`DEV_LOG.md` entry; do not estimate or reuse the pre-Phase-5 count. Then run:

```bash
git add DEV_LOG.md
git commit -m "docs: record simulation plan verification"
```

- [ ] **Step 6: Final handoff**

Report:

- commit list;
- files created/modified;
- exact compileall and pytest results;
- MCP tool names;
- proof that no real FDTD ran;
- remaining next step: generate a verified Windows template contract, then request a separately approved real SimulationPlan run.
