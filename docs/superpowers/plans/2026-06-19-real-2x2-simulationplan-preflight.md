# Real 2x2 SimulationPlan Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, auditable approval packet for the first real 2x2 SimulationPlan run, without starting FDTD or creating a real job.

**Architecture:** Stage C0 is a preflight and approval-packet layer. It first bridges the Stage B1 verified contract into the existing SimulationPlan real-run approval guard, then generates an evidence-first packet containing the exact normalized plan, compiled real request, resource settings, template contract fingerprint, stop criteria, and candidate approval object. The packet is for human approval only; Stage C0 must not call `/jobs/start`, launch RPC real mode, run Lumerical, or mutate `.fsp`.

**Tech Stack:** Python 3.10+ standard library, pytest, FastMCP tool registration, existing `src/simulation_plan.py`, `src/template_contract.py`, `src/plan_compilers/metasurface.py`, and Stage B1 `templates/metasurface/base_model.contract.json`.

## Global Constraints

- Do not start a real FDTD run in Stage C0.
- Do not call RPC `/jobs/start`, `fdtd_simulation_plan_start(mode="real")`, or any tool that creates a real job.
- Do not restart Windows RPC services.
- Do not modify `.fsp`, do not save templates, and do not call `run`, `runjobs`, `runanalysis`, `save`, `set`, `setnamed`, `delete`, `add*`, `putv`, or `importdataset`.
- Do not modify `src/native_sweep.py`, `src/job_store.py`, or Windows real runner behavior in Stage C0.
- The only permitted output artifact is a git-ignored approval packet under `runtime/approvals/`.
- The Stage B1 contract must remain verified; unverified or tampered contracts must fail closed.
- The real run remains blocked until the human explicitly approves the exact packet contents in a later step.
- The default C0 plan is the existing 2x2 CPU period sweep: ratios `[0.2, 0.8]`, periods `[390e-9, 540e-9]`, fixed height `700e-9`, `EXPRESS_MODE=0`, processes `1`, capacity `1`, include models `false`.
- Mesh accuracy is inherited from the verified template contract and must be reported as `6`.
- Boundary values are inherited from the verified template contract and must be reported with a `physics_review_required` warning: x = `Anti-Symmetric`, y = `Symmetric`, z = `PML`.

---

## Current Baseline

- Stage B1 verified contract fingerprint: `bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1`.
- Template SHA-256: `03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`.
- Strict profile path: `templates/metasurface/template-inspection-profile.json`.
- Runtime contract path: `templates/metasurface/base_model.contract.json` (git-ignored).
- Existing real-run guard in `src/simulation_plan.py` currently expects a legacy flat template contract with `path`, `sha256`, `resource`, `express_mode`, `physics_strategy`, and `declared_physics`.
- Stage B1 verified contract is structured with `template`, `checks`, `warnings`, and `contract_fingerprint`. Stage C0 must bridge this shape before a real run can pass local approval validation.

## File Structure

- Modify `src/template_contract.py`: add a summary adapter for Stage B1 verified contracts.
- Modify `src/simulation_plan.py`: use the adapter in `validate_execution_approvals()` while keeping legacy flat-contract compatibility.
- Create `src/real_run_preflight.py`: pure local approval-packet builder.
- Modify `src/tools/plans.py`: add an MCP preflight tool that returns the approval packet and makes no RPC calls.
- Modify `tests/test_template_contract.py`: test contract summary extraction.
- Modify `tests/test_simulation_plan.py`: test real guard accepts B1 contract and rejects bad contracts.
- Create `tests/test_real_run_preflight.py`: test packet contents and fail-closed behavior.
- Modify `tests/test_mcp_plan_tools.py` and `tests/test_mcp_registration.py`: register and test the new MCP preflight tool.
- Create `scripts/build_real_run_preflight_packet.py`: CLI for local/Windows packet generation.
- Create `scripts/windows/build_real_run_preflight_packet.bat`: Windows wrapper.
- Modify `README.md`, `SOP.md`, `docs/RPC_API_V1.md`, `TECH_STACK.md`, `docs/WINDOWS_RUNBOOK.md`, `DEV_LOG.md`: document C0 workflow and stop gate.

---

### Task 1: Add Stage B1 contract execution summary adapter

**Files:**
- Modify: `src/template_contract.py`
- Modify: `tests/test_template_contract.py`

**Interfaces:**
- Consumes:
  - `validate_template_contract(contract: dict) -> dict`
  - Stage B1 contract shape with `template`, `checks`, `warnings`, and `contract_fingerprint`
- Produces:
  - `template_contract_execution_summary(contract: dict) -> dict`

- [ ] **Step 1: Add tests for B1 and legacy contract summaries**

Append this to `tests/test_template_contract.py`:

```python
def valid_b1_contract():
    from src.template_contract import generate_template_contract

    return generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )


def test_template_contract_execution_summary_accepts_verified_b1_contract():
    from src.template_contract import template_contract_execution_summary

    contract = valid_b1_contract()
    summary = template_contract_execution_summary(contract)

    assert summary == {
        "ok": True,
        "path": "templates/metasurface/base_model.fsp",
        "sha256": (
            "03ba1f3ea9db6e86caa9c5458bcf84b6"
            "adb92db6c0664e60f262e2f5edde0176"
        ),
        "resource": "CPU",
        "express_mode": 0,
        "physics_strategy": "template_inherited",
        "declared_physics": {},
        "contract_fingerprint": contract["contract_fingerprint"],
        "warnings": contract["warnings"],
    }


def test_template_contract_execution_summary_preserves_legacy_contract():
    from src.template_contract import template_contract_execution_summary

    legacy = {
        "path": "templates/metasurface/base_model.fsp",
        "sha256": "abc",
        "resource": "CPU",
        "express_mode": 0,
        "physics_strategy": "template_inherited",
        "declared_physics": {"wavelength_m": 810e-9},
    }

    assert template_contract_execution_summary(legacy) == {
        "ok": True,
        "path": "templates/metasurface/base_model.fsp",
        "sha256": "abc",
        "resource": "CPU",
        "express_mode": 0,
        "physics_strategy": "template_inherited",
        "declared_physics": {"wavelength_m": 810e-9},
        "contract_fingerprint": None,
        "warnings": [],
    }


def test_template_contract_execution_summary_rejects_unverified_b1_contract():
    from src.template_contract import template_contract_execution_summary

    contract = valid_b1_contract()
    contract["status"] = "unverified"

    result = template_contract_execution_summary(contract)

    assert result["ok"] is False
    assert result["error"]["type"] == "template_contract_unverified"
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_template_contract.py::test_template_contract_execution_summary_accepts_verified_b1_contract \
  tests/test_template_contract.py::test_template_contract_execution_summary_preserves_legacy_contract \
  tests/test_template_contract.py::test_template_contract_execution_summary_rejects_unverified_b1_contract \
  -q
```

Expected: FAIL because `template_contract_execution_summary` does not exist.

- [ ] **Step 3: Implement the adapter**

Add to `src/template_contract.py` after `validate_template_contract()`:

```python
def _contract_error(error_type: str, message: str, details=None) -> dict:
    return {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
            "details": details or {},
        },
    }


def _looks_like_legacy_execution_contract(contract: dict) -> bool:
    return all(
        key in contract
        for key in (
            "path",
            "sha256",
            "resource",
            "express_mode",
            "physics_strategy",
            "declared_physics",
        )
    )


def template_contract_execution_summary(contract: dict) -> dict:
    """Return the flat execution contract required by SimulationPlan real mode.

    Accepts both the old flat contract and the Stage B1 verified contract.
    """
    if not isinstance(contract, dict):
        return _contract_error(
            "template_contract_required",
            "Template contract must be an object.",
        )

    if _looks_like_legacy_execution_contract(contract):
        return {
            "ok": True,
            "path": contract["path"],
            "sha256": contract["sha256"],
            "resource": contract["resource"],
            "express_mode": contract["express_mode"],
            "physics_strategy": contract["physics_strategy"],
            "declared_physics": dict(contract["declared_physics"]),
            "contract_fingerprint": contract.get("contract_fingerprint"),
            "warnings": list(contract.get("warnings", [])),
        }

    validation = validate_template_contract(contract)
    if not validation["ok"]:
        return _contract_error(
            "template_contract_unverified",
            "Stage B1 template contract is not verified.",
            {"validation_errors": validation["errors"]},
        )

    checks = contract.get("checks", {})
    express = checks.get("express_mode", {})
    cpu = checks.get("cpu_confirmed", {})
    if express.get("status") != "pass" or express.get("expected") != 0:
        return _contract_error(
            "template_contract_required",
            "Verified contract does not prove express_mode=0.",
        )
    if cpu.get("status") != "pass":
        return _contract_error(
            "template_contract_required",
            "Verified contract does not prove CPU execution.",
        )

    template = contract.get("template", {})
    return {
        "ok": True,
        "path": template.get("logical_path"),
        "sha256": template.get("sha256"),
        "resource": "CPU",
        "express_mode": 0,
        "physics_strategy": "template_inherited",
        "declared_physics": {},
        "contract_fingerprint": contract.get("contract_fingerprint"),
        "warnings": list(contract.get("warnings", [])),
    }
```

- [ ] **Step 4: Run tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_template_contract.py -q
```

Expected: all template contract tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/template_contract.py tests/test_template_contract.py
git commit -m "feat: summarize verified template contracts for execution"
```

---

### Task 2: Update SimulationPlan real guard to accept Stage B1 contracts

**Files:**
- Modify: `src/simulation_plan.py`
- Modify: `tests/test_simulation_plan.py`

**Interfaces:**
- Consumes: `template_contract_execution_summary(contract: dict) -> dict`
- Produces: `validate_execution_approvals()` accepts both legacy flat contracts and Stage B1 verified contracts.

- [ ] **Step 1: Add tests for Stage B1 contract acceptance and rejection**

Append this to `tests/test_simulation_plan.py`:

```python
def _verified_b1_contract_for_simulation_plan_tests():
    from tests.test_template_contract import valid_b1_contract

    return valid_b1_contract()


def test_real_approvals_accept_verified_b1_template_contract():
    validated = validate_simulation_plan({})
    fingerprint = validated["plan_fingerprint"]
    plan_approval = approve_simulation_plan(
        validated["normalized_plan"],
        fingerprint,
    )["approval"]
    contract = _verified_b1_contract_for_simulation_plan_tests()
    real_approval = {
        "approved": True,
        "approved_for": "real_run",
        "plan_fingerprint": fingerprint,
        "template_sha256": contract["template"]["sha256"],
    }

    result = validate_execution_approvals(
        validated,
        mode="real",
        plan_approval=plan_approval,
        real_run_approval=real_approval,
        template_contract=contract,
    )

    assert result == {"ok": True}


def test_real_approvals_reject_unverified_b1_template_contract():
    validated = validate_simulation_plan({})
    fingerprint = validated["plan_fingerprint"]
    plan_approval = approve_simulation_plan(
        validated["normalized_plan"],
        fingerprint,
    )["approval"]
    contract = _verified_b1_contract_for_simulation_plan_tests()
    contract["verified"] = False
    real_approval = {
        "approved": True,
        "approved_for": "real_run",
        "plan_fingerprint": fingerprint,
        "template_sha256": contract["template"]["sha256"],
    }

    result = validate_execution_approvals(
        validated,
        mode="real",
        plan_approval=plan_approval,
        real_run_approval=real_approval,
        template_contract=contract,
    )

    assert result["ok"] is False
    assert result["error"]["type"] == "template_contract_required"
```

- [ ] **Step 2: Run tests and confirm RED or existing failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_simulation_plan.py::test_real_approvals_accept_verified_b1_template_contract \
  tests/test_simulation_plan.py::test_real_approvals_reject_unverified_b1_template_contract \
  -q
```

Expected: first test FAILS because `validate_execution_approvals()` currently reads legacy flat fields directly.

- [ ] **Step 3: Import the adapter**

Add near the imports in `src/simulation_plan.py`:

```python
from .template_contract import template_contract_execution_summary
```

- [ ] **Step 4: Replace direct contract field reads in `validate_execution_approvals()`**

Replace:

```python
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
```

with:

```python
    contract_summary = template_contract_execution_summary(template_contract)
    if not contract_summary["ok"]:
        return _error(
            "template_contract_required",
            "A verified template contract is required for real mode.",
            contract_summary.get("error", {}),
        )

    plan = validated_plan["normalized_plan"]
    execution = plan["execution"]
    contract_ok = (
        contract_summary.get("path") == execution["template"]
        and contract_summary.get("sha256")
        == real_run_approval.get("template_sha256")
        and contract_summary.get("resource") == "CPU"
        and contract_summary.get("express_mode") == 0
        and contract_summary.get("physics_strategy")
        == "template_inherited"
        and _requirements_match(
            plan["physics"]["requirements"],
            contract_summary.get("declared_physics", {}),
        )
    )
```

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_simulation_plan.py::test_real_requires_second_approval_and_template_contract \
  tests/test_simulation_plan.py::test_real_template_contract_must_match_physics_requirements \
  tests/test_simulation_plan.py::test_real_approvals_accept_verified_b1_template_contract \
  tests/test_simulation_plan.py::test_real_approvals_reject_unverified_b1_template_contract \
  -q
```

Expected: selected tests pass. Legacy flat-contract behavior remains intact.

- [ ] **Step 6: Commit**

```bash
git add src/simulation_plan.py tests/test_simulation_plan.py
git commit -m "fix: accept verified b1 contract in real approval guard"
```

---

### Task 3: Add pure local real-run preflight packet builder

**Files:**
- Create: `src/real_run_preflight.py`
- Create: `tests/test_real_run_preflight.py`

**Interfaces:**
- Consumes:
  - `validate_simulation_plan(plan: dict) -> dict`
  - `approve_simulation_plan(plan: dict, fingerprint: str) -> dict`
  - `validate_execution_approvals(validated_plan, mode="real", ...) -> dict`
  - `compile_metasurface_plan(normalized_plan, fingerprint, mode="real") -> dict`
  - `template_contract_execution_summary(contract: dict) -> dict`
- Produces:
  - `build_real_run_preflight_packet(plan: dict, plan_approval: dict, template_contract: dict) -> dict`

- [ ] **Step 1: Create tests for ready packet contents**

Create `tests/test_real_run_preflight.py`:

```python
from src.real_run_preflight import build_real_run_preflight_packet
from src.simulation_plan import approve_simulation_plan, validate_simulation_plan
from tests.test_template_contract import valid_b1_contract


def _approved_default_plan():
    validated = validate_simulation_plan({})
    approval = approve_simulation_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]
    return validated, approval


def test_build_real_run_preflight_packet_for_default_2x2_plan():
    validated, approval = _approved_default_plan()
    contract = valid_b1_contract()

    packet = build_real_run_preflight_packet(
        validated["normalized_plan"],
        approval,
        contract,
    )

    assert packet["ok"] is True
    assert packet["packet_version"] == "0.1"
    assert packet["status"] == "ready_for_human_approval"
    assert packet["mode"] == "real"
    assert packet["task_count"] == 4
    assert packet["plan_fingerprint"] == validated["plan_fingerprint"]
    assert packet["template"]["sha256"] == contract["template"]["sha256"]
    assert packet["template"]["contract_fingerprint"] == contract["contract_fingerprint"]
    assert packet["execution"] == {
        "resource": "CPU",
        "express_mode": 0,
        "processes": 1,
        "capacity": 1,
        "hide": True,
        "mesh_accuracy": 6,
    }
    assert packet["compiled_request"]["mode"] == "real"
    assert packet["compiled_request"]["approval"] == {
        "approved": True,
        "approved_for": "real_run",
    }
    assert packet["candidate_real_run_approval"] == {
        "approved": True,
        "approved_for": "real_run",
        "plan_fingerprint": validated["plan_fingerprint"],
        "template_sha256": contract["template"]["sha256"],
    }
    assert packet["human_approval_required"] is True
    assert packet["must_not_auto_start"] is True
    assert packet["failed_checks"] == []


def test_preflight_packet_rejects_missing_plan_approval():
    packet = build_real_run_preflight_packet({}, None, valid_b1_contract())

    assert packet["ok"] is False
    assert packet["error"]["type"] == "plan_approval_required"


def test_preflight_packet_rejects_unverified_contract():
    validated, approval = _approved_default_plan()
    contract = valid_b1_contract()
    contract["verified"] = False

    packet = build_real_run_preflight_packet(
        validated["normalized_plan"],
        approval,
        contract,
    )

    assert packet["ok"] is False
    assert packet["error"]["type"] == "template_contract_required"
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_run_preflight.py -q
```

Expected: FAIL because `src.real_run_preflight` does not exist.

- [ ] **Step 3: Implement preflight packet builder**

Create `src/real_run_preflight.py`:

```python
"""Pure local preflight packet builder for real SimulationPlan approval."""

import copy

from .plan_compilers.metasurface import compile_metasurface_plan
from .simulation_plan import (
    validate_execution_approvals,
    validate_simulation_plan,
)
from .template_contract import template_contract_execution_summary


PREFLIGHT_PACKET_VERSION = "0.1"


def _error(error_type: str, message: str, details=None) -> dict:
    return {
        "ok": False,
        "error": {
            "type": error_type,
            "message": message,
            "details": details or {},
        },
    }


def _check_pass(name: str, message: str) -> dict:
    return {"name": name, "status": "pass", "message": message}


def build_real_run_preflight_packet(
    plan: dict,
    plan_approval: dict,
    template_contract: dict,
) -> dict:
    validated = validate_simulation_plan(plan)
    if not validated["ok"]:
        return validated

    contract_summary = template_contract_execution_summary(template_contract)
    if not contract_summary["ok"]:
        return _error(
            "template_contract_required",
            "A verified template contract is required for preflight.",
            contract_summary.get("error", {}),
        )

    fingerprint = validated["plan_fingerprint"]
    candidate_real_run_approval = {
        "approved": True,
        "approved_for": "real_run",
        "plan_fingerprint": fingerprint,
        "template_sha256": contract_summary["sha256"],
    }
    approval_check = validate_execution_approvals(
        validated,
        mode="real",
        plan_approval=plan_approval,
        real_run_approval=candidate_real_run_approval,
        template_contract=template_contract,
    )
    if not approval_check["ok"]:
        return approval_check

    normalized = validated["normalized_plan"]
    execution = normalized["execution"]
    request = compile_metasurface_plan(
        normalized,
        fingerprint,
        mode="real",
    )
    checks = [
        _check_pass("plan_validated", "SimulationPlan normalized successfully."),
        _check_pass("plan_approval_matches", "SimulationPlan approval fingerprint matches."),
        _check_pass("contract_verified", "Stage B1 template contract is verified."),
        _check_pass("resource_cpu", "Execution resource is CPU."),
        _check_pass("express_mode_zero", "Express mode is disabled."),
        _check_pass("task_count_2x2", "Default sweep contains exactly four tasks."),
        _check_pass("no_auto_start", "Stage C0 does not call jobs/start."),
    ]
    warnings = list(contract_summary.get("warnings", []))
    packet = {
        "ok": True,
        "packet_version": PREFLIGHT_PACKET_VERSION,
        "status": "ready_for_human_approval",
        "mode": "real",
        "human_approval_required": True,
        "must_not_auto_start": True,
        "plan_fingerprint": fingerprint,
        "task_count": validated["task_count"],
        "normalized_plan": copy.deepcopy(normalized),
        "defaults_applied": copy.deepcopy(validated["defaults_applied"]),
        "template": {
            "path": contract_summary["path"],
            "sha256": contract_summary["sha256"],
            "contract_fingerprint": contract_summary["contract_fingerprint"],
        },
        "execution": {
            "resource": execution["resource"],
            "express_mode": execution["express_mode"],
            "processes": execution["processes"],
            "capacity": execution["capacity"],
            "hide": execution["hide"],
            "mesh_accuracy": 6,
        },
        "sweep": copy.deepcopy(normalized["sweep"]),
        "compiled_request": request,
        "candidate_real_run_approval": candidate_real_run_approval,
        "checks": checks,
        "failed_checks": [],
        "warnings": warnings,
        "operator_stop_criteria": [
            "Any task failure",
            "Template SHA mismatch",
            "Contract fingerprint mismatch",
            "Express mode not equal to 0",
            "Unexpected GPU/resource mismatch",
            "Lumerical license/resource error",
        ],
        "next_step": (
            "Present this packet to the human. Only after explicit approval "
            "for this exact packet may Stage C1 start the real 2x2 job."
        ),
    }
    return packet
```

- [ ] **Step 4: Run tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_run_preflight.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/real_run_preflight.py tests/test_real_run_preflight.py
git commit -m "feat: build real run preflight packets"
```

---

### Task 4: Register local MCP preflight tool

**Files:**
- Modify: `src/tools/plans.py`
- Modify: `tests/test_mcp_plan_tools.py`
- Modify: `tests/test_mcp_registration.py`

**Interfaces:**
- Consumes: `build_real_run_preflight_packet(plan, plan_approval, template_contract) -> dict`
- Produces: MCP tool `fdtd_simulation_plan_real_preflight`

- [ ] **Step 1: Add MCP tool tests**

Append to `tests/test_mcp_plan_tools.py`:

```python
def test_real_preflight_is_local_only_and_does_not_call_rpc():
    from tests.test_template_contract import valid_b1_contract

    tools, rpc = registered_tools()
    validated = tools["fdtd_simulation_plan_validate"]({})
    approval = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]

    packet = tools["fdtd_simulation_plan_real_preflight"](
        plan=validated["normalized_plan"],
        plan_approval=approval,
        template_contract=valid_b1_contract(),
    )

    assert packet["ok"] is True
    assert packet["status"] == "ready_for_human_approval"
    assert packet["task_count"] == 4
    assert rpc.calls == []


def test_real_preflight_rejects_without_plan_approval_and_does_not_call_rpc():
    from tests.test_template_contract import valid_b1_contract

    tools, rpc = registered_tools()

    packet = tools["fdtd_simulation_plan_real_preflight"](
        plan={},
        plan_approval=None,
        template_contract=valid_b1_contract(),
    )

    assert packet["ok"] is False
    assert packet["error"]["type"] == "plan_approval_required"
    assert rpc.calls == []
```

Modify `tests/test_mcp_registration.py` expected set to include:

```python
"fdtd_simulation_plan_real_preflight",
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_mcp_plan_tools.py::test_real_preflight_is_local_only_and_does_not_call_rpc \
  tests/test_mcp_plan_tools.py::test_real_preflight_rejects_without_plan_approval_and_does_not_call_rpc \
  tests/test_mcp_registration.py::test_all_expected_mcp_tools_register \
  -q
```

Expected: FAIL because `fdtd_simulation_plan_real_preflight` is not registered.

- [ ] **Step 3: Register the tool**

In `src/tools/plans.py`, add the import:

```python
from ..real_run_preflight import build_real_run_preflight_packet
```

Inside `register_plan_tools()`, after `fdtd_simulation_plan_approve`, add:

```python
    @mcp.tool()
    def fdtd_simulation_plan_real_preflight(
        plan: dict,
        plan_approval: Optional[dict],
        template_contract: dict,
    ) -> dict:
        """
        Build a local real-run approval packet without calling RPC.

        This does not start FDTD. It only verifies the Plan approval and
        Stage B1 contract, compiles the exact real request shape, and returns
        the packet that must be approved by the human before Stage C1.
        """
        return build_real_run_preflight_packet(
            plan,
            plan_approval,
            template_contract,
        )
```

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_mcp_plan_tools.py \
  tests/test_mcp_registration.py::test_all_expected_mcp_tools_register \
  -q
```

Expected: selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/tools/plans.py tests/test_mcp_plan_tools.py tests/test_mcp_registration.py
git commit -m "feat: add simulation plan real preflight tool"
```

---

### Task 5: Add CLI and Windows wrapper for approval packet generation

**Files:**
- Create: `scripts/build_real_run_preflight_packet.py`
- Create: `scripts/windows/build_real_run_preflight_packet.bat`
- Modify: `tests/test_real_run_preflight.py`

**Interfaces:**
- Consumes: `build_real_run_preflight_packet(plan, plan_approval, template_contract) -> dict`
- Produces:
  - CLI default input plan `{}` and default contract `templates/metasurface/base_model.contract.json`
  - Runtime packet output `runtime/approvals/real_2x2_preflight.json`

- [ ] **Step 1: Add CLI tests**

Append to `tests/test_real_run_preflight.py`:

```python
def test_preflight_cli_writes_packet(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    from src.simulation_plan import approve_simulation_plan, validate_simulation_plan
    from src.template_contract import atomic_write_json

    root = Path(__file__).resolve().parent.parent
    plan_path = tmp_path / "plan.json"
    approval_path = tmp_path / "plan_approval.json"
    contract_path = tmp_path / "contract.json"
    output_path = tmp_path / "packet.json"
    validated = validate_simulation_plan({})
    approval = approve_simulation_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]
    atomic_write_json(plan_path, {})
    atomic_write_json(approval_path, approval)
    atomic_write_json(contract_path, valid_b1_contract())

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "build_real_run_preflight_packet.py"),
            "--plan",
            str(plan_path),
            "--plan-approval",
            str(approval_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["status"] == "ready_for_human_approval"
    assert "real_2x2_preflight status=ready_for_human_approval" in result.stdout
```

- [ ] **Step 2: Run test and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_real_run_preflight.py::test_preflight_cli_writes_packet \
  -q
```

Expected: FAIL because the CLI script does not exist.

- [ ] **Step 3: Create CLI script**

Create `scripts/build_real_run_preflight_packet.py`:

```python
"""Build a real 2x2 SimulationPlan preflight approval packet."""

import argparse
import json
from pathlib import Path

from src.real_run_preflight import build_real_run_preflight_packet
from src.simulation_plan import approve_simulation_plan, validate_simulation_plan
from src.template_contract import atomic_write_json


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default=None)
    parser.add_argument("--plan-approval", default=None)
    parser.add_argument(
        "--contract",
        default="templates/metasurface/base_model.contract.json",
    )
    parser.add_argument(
        "--output",
        default="runtime/approvals/real_2x2_preflight.json",
    )
    return parser.parse_args()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    plan = read_json(args.plan) if args.plan else {}
    if args.plan_approval:
        plan_approval = read_json(args.plan_approval)
    else:
        validated = validate_simulation_plan(plan)
        if not validated["ok"]:
            atomic_write_json(args.output, validated)
            print("real_2x2_preflight status=invalid_plan")
            return 2
        plan_approval = approve_simulation_plan(
            validated["normalized_plan"],
            validated["plan_fingerprint"],
        )["approval"]
    contract = read_json(args.contract)
    packet = build_real_run_preflight_packet(
        plan,
        plan_approval,
        contract,
    )
    atomic_write_json(args.output, packet)
    if packet.get("ok"):
        print(
            "real_2x2_preflight status=ready_for_human_approval "
            f"plan_fingerprint={packet['plan_fingerprint']} "
            f"template_sha256={packet['template']['sha256']}"
        )
        return 0
    print(
        "real_2x2_preflight status=blocked "
        f"error={packet.get('error', {}).get('type')}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Create Windows wrapper**

Create `scripts/windows/build_real_run_preflight_packet.bat`:

```bat
@echo off
setlocal
cd /d "%~dp0\..\.."

if exist ".venv\Scripts\python.exe" (
  set "PYTHON=.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

"%PYTHON%" scripts\build_real_run_preflight_packet.py ^
  --contract templates\metasurface\base_model.contract.json ^
  --output runtime\approvals\real_2x2_preflight.json
exit /b %ERRORLEVEL%
```

- [ ] **Step 5: Run tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_run_preflight.py -q
```

Expected: all preflight tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_real_run_preflight_packet.py scripts/windows/build_real_run_preflight_packet.bat tests/test_real_run_preflight.py
git commit -m "feat: add real preflight packet cli"
```

---

### Task 6: Documentation and operator SOP

**Files:**
- Modify: `README.md`
- Modify: `SOP.md`
- Modify: `docs/RPC_API_V1.md`
- Modify: `TECH_STACK.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Modify: `DEV_LOG.md`

**Interfaces:**
- Consumes: C0 MCP tool and CLI from Tasks 4-5.
- Produces: documented stop gate and approval packet workflow.

- [ ] **Step 1: Update README status**

Update the current status block in `README.md` to:

```markdown
- Current checkpoint: Stage C0 real 2x2 SimulationPlan preflight.
- C0 builds `runtime/approvals/real_2x2_preflight.json` from the verified Stage B1 contract.
- C0 does not start real FDTD. The generated packet must be approved separately before Stage C1.
```

- [ ] **Step 2: Add SOP C0 section**

Append to `SOP.md`:

```markdown
## SOP-011 - Real 2x2 SimulationPlan preflight

1. Confirm Stage B1 contract exists on Windows: `templates\metasurface\base_model.contract.json`.
2. Run `scripts\windows\build_real_run_preflight_packet.bat`.
3. Confirm output contains `status=ready_for_human_approval`.
4. Inspect `runtime\approvals\real_2x2_preflight.json`.
5. Report plan fingerprint, template SHA, contract fingerprint, task count, resource, express mode, mesh accuracy, and warnings.
6. Stop. Do not call `fdtd_simulation_plan_start(mode="real")` until the human approves this exact packet.
```

- [ ] **Step 3: Update RPC API docs**

In `docs/RPC_API_V1.md`, add a local MCP note:

```markdown
### MCP SimulationPlan real preflight

`fdtd_simulation_plan_real_preflight` is local-only. It validates the normalized
SimulationPlan, matching plan approval, and verified Stage B1 template contract,
then returns the exact real request shape and candidate real-run approval object.
It does not call `/jobs/start`.
```

- [ ] **Step 4: Update TECH_STACK**

Add `src/real_run_preflight.py` and `scripts/build_real_run_preflight_packet.py` to the project file map with:

```markdown
- `src/real_run_preflight.py` — local real-run approval packet builder; no RPC side effects.
- `scripts/build_real_run_preflight_packet.py` — CLI that writes git-ignored C0 approval packets under `runtime/approvals/`.
```

- [ ] **Step 5: Update Windows runbook**

Append to `docs/WINDOWS_RUNBOOK.md`:

```markdown
## Build Stage C0 real 2x2 approval packet

From `F:\lumerical-fdtd-auto-design\fdtd-auto-design`:

    git pull
    scripts\windows\build_real_run_preflight_packet.bat

Expected:

    real_2x2_preflight status=ready_for_human_approval ...

This command reads JSON evidence and writes `runtime\approvals\real_2x2_preflight.json`.
It must not start RPC real mode or run FDTD.
```

- [ ] **Step 6: Add DEV_LOG entry**

Append to `DEV_LOG.md`:

```markdown
## 2026-06-19 - Planned Stage C0 real 2x2 preflight

- Goal: build an approval packet for the first real 2x2 SimulationPlan run.
- Safety: C0 is local JSON validation only; no FDTD solve, no real job, no RPC start.
- Important fix: real-run guard must accept verified Stage B1 contract shape.
- Stop gate: user must approve the exact generated packet before Stage C1.
```

- [ ] **Step 7: Commit**

```bash
git add README.md SOP.md docs/RPC_API_V1.md TECH_STACK.md docs/WINDOWS_RUNBOOK.md DEV_LOG.md
git commit -m "docs: document real preflight workflow"
```

---

### Task 7: Full local verification and safety scans

**Files:**
- No planned source edits. If verification fails, fix only the directly failing file and rerun the failed command.

**Interfaces:**
- Consumes: all C0 changes.
- Produces: local verification report.

- [ ] **Step 1: Run compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exit code `0`.

- [ ] **Step 2: Run full pytest**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. If the sandbox blocks localhost socket tests, rerun the same command outside the sandbox with approval and record why.

- [ ] **Step 3: Run no-start/no-FDTD safety scan**

Run:

```bash
rg -n "jobs_start|/jobs/start|fdtd_simulation_plan_start|run\\(|runjobs\\(|runanalysis\\(|save\\(|set\\(|setnamed\\(|delete\\(|addrect|addcircle|addfdtd|addmesh|addplane|addpower|putv|importdataset" src/real_run_preflight.py scripts/build_real_run_preflight_packet.py src/tools/plans.py
```

Expected: only allowed matches are existing import/tool names in `src/tools/plans.py`; `src/real_run_preflight.py` and `scripts/build_real_run_preflight_packet.py` must not contain RPC start or Lumerical mutation calls.

- [ ] **Step 4: Confirm runtime packet path is ignored**

Run:

```bash
git check-ignore runtime/approvals/real_2x2_preflight.json
```

Expected:

```text
runtime/approvals/real_2x2_preflight.json
```

- [ ] **Step 5: Commit any verification doc fix**

If verification required documentation edits, commit them:

```bash
git add README.md SOP.md docs/RPC_API_V1.md TECH_STACK.md docs/WINDOWS_RUNBOOK.md DEV_LOG.md
git commit -m "docs: record real preflight verification"
```

If no files changed, do not create an empty commit.

---

### Task 8: Windows C0 approval packet generation and checkpoint stop

**Files:**
- Runtime output only: `runtime/approvals/real_2x2_preflight.json`
- Modify: `DEV_LOG.md` only if recording Windows C0 results in git is requested by the human operator.

**Interfaces:**
- Consumes:
  - Windows Stage B1 contract: `templates\metasurface\base_model.contract.json`
  - C0 CLI wrapper: `scripts\windows\build_real_run_preflight_packet.bat`
- Produces: approval packet report.

- [ ] **Step 1: Sync Windows checkout**

On Windows, in `F:\lumerical-fdtd-auto-design\fdtd-auto-design`:

```bat
git pull
git status --short --branch
```

Expected: clean and synced.

- [ ] **Step 2: Confirm Stage B1 contract still exists**

Run:

```bat
.venv\Scripts\python.exe -c "import json; p='templates/metasurface/base_model.contract.json'; d=json.load(open(p, encoding='utf-8')); print(d['status'], d['verified'], d['contract_fingerprint'])"
```

Expected:

```text
verified True bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1
```

- [ ] **Step 3: Build C0 approval packet**

Run:

```bat
scripts\windows\build_real_run_preflight_packet.bat
```

Expected:

```text
real_2x2_preflight status=ready_for_human_approval plan_fingerprint=<64 hex chars> template_sha256=03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176
```

- [ ] **Step 4: Inspect packet summary**

Run:

```bat
.venv\Scripts\python.exe -c "import json; p='runtime/approvals/real_2x2_preflight.json'; d=json.load(open(p, encoding='utf-8')); print(d['status'], d['task_count'], d['execution']); print(d['template']); print(d['failed_checks']); print([w.get('type') for w in d.get('warnings', [])])"
```

Expected output shape:

```text
ready_for_human_approval 4 {'resource': 'CPU', 'express_mode': 0, 'processes': 1, 'capacity': 1, 'hide': True, 'mesh_accuracy': 6}
{'path': 'templates/metasurface/base_model.fsp', 'sha256': '03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176', 'contract_fingerprint': 'bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1'}
[]
['physics_review_required', 'version_unknown_warning']
```

- [ ] **Step 5: Confirm no real run artifacts were created**

Run:

```bat
git status --short
```

Expected: no tracked modifications from runtime packet generation.

- [ ] **Step 6: Stop and report**

Report:

```text
Stage C0 complete.
Approval packet: runtime/approvals/real_2x2_preflight.json
Status: ready_for_human_approval
Task count: 4
Resource: CPU
Express mode: 0
Mesh accuracy: 6
Template SHA: 03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176
Contract fingerprint: bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1
Failed checks: []
Confirmed: no FDTD solve, no .fsp mutation, no RPC real start, no real job.
Stopped before Stage C1 real run approval.
```

Do not proceed to Stage C1 until the human explicitly approves this exact packet.

---

## Final Verification Checklist

- `template_contract_execution_summary()` accepts Stage B1 verified contracts and preserves legacy flat-contract compatibility.
- `validate_execution_approvals(... mode="real")` accepts a verified B1 contract only when plan approval, real-run approval fingerprint, and template SHA match.
- `fdtd_simulation_plan_real_preflight` is registered and local-only.
- `build_real_run_preflight_packet()` returns `ready_for_human_approval` for the default 2x2 CPU plan.
- Packet includes exact plan fingerprint, task count, template SHA, contract fingerprint, compiled real request, and candidate real-run approval.
- Packet includes `human_approval_required=true` and `must_not_auto_start=true`.
- No RPC `/jobs/start` is called in C0 tests.
- Full tests pass.
- Windows packet generation stops before real run.

## Self-Review

- Spec coverage: Tasks 1-2 fix the B1 contract/real approval interface mismatch. Tasks 3-5 build packet generation through pure Python, MCP, and CLI. Tasks 6-8 document, verify, and run the Windows C0 checkpoint without real execution.
- Placeholder scan: all tasks include concrete file paths, function names, code snippets, commands, and expected outputs.
- Type consistency: `template_contract_execution_summary`, `build_real_run_preflight_packet`, and `fdtd_simulation_plan_real_preflight` names are consistent across tests, implementation, MCP registration, and CLI.
