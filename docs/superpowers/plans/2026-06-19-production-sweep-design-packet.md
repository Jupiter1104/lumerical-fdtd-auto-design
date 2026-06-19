# Production Sweep Design Packet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Stage C3 approval packet for the next bounded real sweep, using the C2 review as evidence, without starting FDTD.

**Architecture:** Stage C3 is a planning and approval-packet layer. It reads the completed C2 `review.json`, proposes a conservative 25-task production-discovery sweep, validates and approves the resulting SimulationPlan locally, verifies the Stage B1 template contract, and writes a packet that a human can approve later. The packet includes the exact compiled `/jobs/start` request shape, but C3 must never submit it.

**Tech Stack:** Python 3.10+ standard library, pytest, existing `src/simulation_plan.py`, existing `src/plan_compilers/metasurface.py`, existing `src/template_contract.py`, existing C2 `src/real_result_review.py`, FastMCP registration for a local-only planning tool, Windows `.bat` wrapper for packet generation.

## Global Constraints

- Do not start FDTD, do not create a real job, and do not call `/jobs/start`.
- Do not call `fdtd_simulation_plan_start(mode="real")`, `fdtd_job_start`, or `fdtd_job_resume`.
- Do not resume the C1 job and do not expand a running job.
- Do not restart Windows RPC services.
- Do not modify `.fsp` files, do not save templates, and do not call `run`, `runjobs`, `runanalysis`, `save`, `set`, `setnamed`, `delete`, `add*`, `putv`, or `importdataset`.
- Do not modify `src/native_sweep.py`, `src/job_store.py`, or real-run execution behavior.
- Keep Stage C0 `real_2x2_preflight` locked to exactly 4 tasks; C3 must use a new packet builder instead of weakening C0.
- C3 default sweep must be bounded to 25 tasks: 5 ratio values × 5 height values.
- C3 default sweep must use CPU with `express_mode=0`, `processes=1`, `capacity=1`, `hide=True`, and `include_models=False`.
- C3 default sweep must inherit template physics and must not alter materials, source, monitors, boundaries, mesh, or template file.
- C3 default height values must not exceed `700e-9` because the Stage B0.1 evidence recorded mesh override z span `700e-9`; taller pillars require a separate template/mesh review stage.
- C3 packet must stop at `status=ready_for_human_approval`; a later Stage C4 may start the real run only after explicit approval of the exact C3 packet.
- C2 source review must be present and must show `software_chain_verdict=pass`.
- Physical conclusion remains human-reviewed. C3 may define acceptance criteria but must not claim the next sweep will produce a final design library.

---

## Current Baseline

Stage C2 completed the first real 2×2 evidence review:

- C1 job ID: `job_20260619_213418_metasurface_sweep`.
- C1 state: `succeeded`.
- C1 quality: `pass`.
- C1 task counts: `4 succeeded / 0 failed / 4 total`.
- C1 software-chain verdict: `pass`.
- C1 physical-review conclusion: `human_review_required`.
- C1 phase span: `1.3272514058176679 rad` (`76.046°`), far below `2π`.
- C1 transmission mean: `0.9001426292124059`.
- C2 review path: `runtime/reviews/job_20260619_213418_metasurface_sweep/review.json`.
- Verified template contract path on Windows and local checkout: `templates/metasurface/base_model.contract.json`.
- Expected template SHA-256: `03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`.
- Expected Stage B1 contract fingerprint: `bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1`.

## C3 Default Sweep Decision

Use a conservative `ratio × height` discovery sweep:

```json
{
  "sweep": {
    "axis": "height",
    "ratio_values": [0.2, 0.35, 0.5, 0.65, 0.8],
    "height_values_m": [5e-7, 5.5e-7, 6e-7, 6.5e-7, 7e-7],
    "fixed_period_m": 4.7e-7
  }
}
```

Rationale:

- C1 already tried period endpoints at fixed height `700 nm` and found only `1.3273 rad` phase span.
- Height is a physically important phase-control dimension for nanopillar metasurfaces.
- The default height range stops at `700 nm` to stay within the currently verified mesh/template envelope.
- A 25-task sweep is large enough to show coarse trends while staying bounded for single-machine CPU execution.
- If C3/C4 still lacks phase coverage, the next stage should explicitly review template mesh and consider a taller-pillar or period-range expansion, rather than silently changing physics.

## File Structure

- Create `src/production_sweep_design.py`: pure local Stage C3 packet builder.
- Create `tests/test_production_sweep_design.py`: tests for default plan, fail-closed behavior, packet content, and CLI.
- Create `scripts/build_production_sweep_packet.py`: CLI for Mac/Windows local packet generation.
- Create `scripts/windows/build_production_sweep_packet.bat`: Windows wrapper.
- Modify `src/tools/plans.py`: add local-only MCP tool `fdtd_simulation_plan_production_preflight`.
- Modify `tests/test_mcp_plan_tools.py`: verify the new MCP tool never calls RPC.
- Modify `tests/test_mcp_registration.py`: register the new tool name.
- Modify `README.md`, `SOP.md`, `DEV_LOG.md`, and `docs/WINDOWS_RUNBOOK.md`: document Stage C3.
- Runtime output, not committed: `runtime/approvals/production_sweep_c3_packet.json`.

---

### Task 1: Add Stage C3 production sweep packet builder

**Files:**
- Create: `src/production_sweep_design.py`
- Create: `tests/test_production_sweep_design.py`

**Interfaces:**
- Consumes:
  - `validate_simulation_plan(plan: dict) -> dict`
  - `approve_simulation_plan(plan: dict, fingerprint: str) -> dict`
  - `validate_execution_approvals(validated_plan: dict, mode: str, plan_approval: dict, real_run_approval: dict, template_contract: dict) -> dict`
  - `compile_metasurface_plan(normalized_plan: dict, fingerprint: str, mode: str) -> dict`
  - `template_contract_execution_summary(contract: dict) -> dict`
  - C2 review dict from `runtime/reviews/.../review.json`
- Produces:
  - `default_c3_production_plan() -> dict`
  - `build_production_sweep_design_packet(c2_review: dict, template_contract: dict, plan: dict | None = None, max_tasks: int = 25) -> dict`

- [ ] **Step 1: Write failing tests**

Create `tests/test_production_sweep_design.py` with this content:

```python
from tests.test_template_contract import valid_b1_contract


TEMPLATE_SHA = (
    "03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176"
)
CONTRACT_FINGERPRINT = (
    "bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1"
)


def valid_c2_review():
    return {
        "ok": True,
        "job_id": "job_20260619_213418_metasurface_sweep",
        "software_chain_verdict": "pass",
        "task_counts": {"total": 4, "succeeded": 4, "failed": 0},
        "metrics": {
            "transmission": {
                "min": 0.7300105242892926,
                "max": 0.9679605819741104,
                "mean": 0.9001426292124059,
                "span": 0.2379500576848178,
            },
            "phase_rad": {
                "min": -1.9698575481531564,
                "max": -0.6426061423354885,
                "mean": -1.0589270743563999,
                "span": 1.3272514058176679,
                "span_degrees": 76.046,
            },
            "sample_count": 4,
        },
        "physical_review": {
            "required": True,
            "conclusion": "human_review_required",
            "note": "Phase coverage is far below 2π.",
        },
    }


def test_default_c3_plan_is_bounded_height_sweep():
    from src.production_sweep_design import default_c3_production_plan
    from src.simulation_plan import validate_simulation_plan

    plan = default_c3_production_plan()
    validated = validate_simulation_plan(plan)

    assert validated["ok"] is True
    assert validated["task_count"] == 25
    assert plan["sweep"] == {
        "axis": "height",
        "ratio_values": [0.2, 0.35, 0.5, 0.65, 0.8],
        "height_values_m": [5e-7, 5.5e-7, 6e-7, 6.5e-7, 7e-7],
        "fixed_period_m": 4.7e-7,
    }
    assert plan["execution"]["resource"] == "CPU"
    assert plan["execution"]["express_mode"] == 0
    assert plan["outputs"]["include_models"] is False


def test_build_production_sweep_design_packet_for_default_plan():
    from src.production_sweep_design import build_production_sweep_design_packet

    packet = build_production_sweep_design_packet(
        valid_c2_review(),
        valid_b1_contract(),
    )

    assert packet["ok"] is True
    assert packet["stage"] == "C3"
    assert packet["status"] == "ready_for_human_approval"
    assert packet["mode"] == "real"
    assert packet["task_count"] == 25
    assert packet["human_approval_required"] is True
    assert packet["must_not_auto_start"] is True
    assert packet["source_review"]["job_id"] == "job_20260619_213418_metasurface_sweep"
    assert packet["source_review"]["software_chain_verdict"] == "pass"
    assert packet["template"]["sha256"] == TEMPLATE_SHA
    assert packet["template"]["contract_fingerprint"] == CONTRACT_FINGERPRINT
    assert packet["execution"] == {
        "resource": "CPU",
        "express_mode": 0,
        "processes": 1,
        "capacity": 1,
        "hide": True,
        "include_models": False,
    }
    assert packet["sweep"]["axis"] == "height"
    assert packet["compiled_request"]["mode"] == "real"
    assert packet["compiled_request"]["job_type"] == "metasurface-sweep"
    assert packet["compiled_request"]["sweep"]["config"]["SWEEP_Y_AXIS"] == "height"
    assert packet["compiled_request"]["sweep"]["config"]["HEIGHT_LIST"] == [
        5e-7,
        5.5e-7,
        6e-7,
        6.5e-7,
        7e-7,
    ]
    assert packet["failed_checks"] == []
    assert packet["approval_gate"]["candidate_plan_approval"]["approved_for"] == "simulation_plan"
    assert packet["approval_gate"]["candidate_real_run_approval"]["approved_for"] == "real_run"


def test_packet_rejects_failed_c2_review():
    from src.production_sweep_design import build_production_sweep_design_packet

    review = valid_c2_review()
    review["software_chain_verdict"] = "fail"

    packet = build_production_sweep_design_packet(review, valid_b1_contract())

    assert packet["ok"] is False
    assert packet["error"]["type"] == "source_review_not_passed"


def test_packet_rejects_task_count_above_c3_budget():
    from src.production_sweep_design import build_production_sweep_design_packet

    plan = {
        "sweep": {
            "axis": "height",
            "ratio_values": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "height_values_m": [5e-7, 5.5e-7, 6e-7, 6.5e-7, 7e-7],
            "fixed_period_m": 4.7e-7,
        }
    }

    packet = build_production_sweep_design_packet(
        valid_c2_review(),
        valid_b1_contract(),
        plan=plan,
    )

    assert packet["ok"] is False
    assert packet["error"]["type"] == "production_task_budget_exceeded"
    assert packet["error"]["details"] == {"task_count": 30, "maximum": 25}


def test_packet_rejects_height_above_verified_mesh_envelope():
    from src.production_sweep_design import build_production_sweep_design_packet

    plan = {
        "sweep": {
            "axis": "height",
            "ratio_values": [0.2, 0.5, 0.8],
            "height_values_m": [5e-7, 7.5e-7],
            "fixed_period_m": 4.7e-7,
        }
    }

    packet = build_production_sweep_design_packet(
        valid_c2_review(),
        valid_b1_contract(),
        plan=plan,
    )

    assert packet["ok"] is False
    assert packet["error"]["type"] == "height_exceeds_verified_mesh_envelope"
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_production_sweep_design.py -q
```

Expected: FAIL because `src.production_sweep_design` does not exist.

- [ ] **Step 3: Add implementation**

Create `src/production_sweep_design.py` with this content:

```python
"""Stage C3 local production sweep design packet builder."""

import copy

from .plan_compilers.metasurface import compile_metasurface_plan
from .simulation_plan import (
    approve_simulation_plan,
    validate_execution_approvals,
    validate_simulation_plan,
)
from .template_contract import template_contract_execution_summary


C3_PACKET_VERSION = "0.1"
C3_MAX_TASKS = 25
VERIFIED_HEIGHT_MAX_M = 700e-9


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


def default_c3_production_plan() -> dict:
    return {
        "schema_version": "0.1",
        "intent": {
            "summary": (
                "Stage C3 bounded production-discovery sweep after the "
                "real 2x2 software-chain validation."
            )
        },
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
            "axis": "height",
            "ratio_values": [0.2, 0.35, 0.5, 0.65, 0.8],
            "height_values_m": [5e-7, 5.5e-7, 6e-7, 6.5e-7, 7e-7],
            "fixed_period_m": 4.7e-7,
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


def _source_review_ok(c2_review: dict) -> bool:
    return (
        isinstance(c2_review, dict)
        and c2_review.get("ok") is True
        and c2_review.get("software_chain_verdict") == "pass"
        and (c2_review.get("physical_review") or {}).get("conclusion")
        == "human_review_required"
    )


def _height_limit_error(normalized_plan: dict) -> dict | None:
    sweep = normalized_plan["sweep"]
    if sweep["axis"] != "height":
        return None
    too_high = [
        value
        for value in sweep["height_values_m"]
        if float(value) > VERIFIED_HEIGHT_MAX_M
    ]
    if too_high:
        return _error(
            "height_exceeds_verified_mesh_envelope",
            "C3 height sweep must not exceed the verified 700 nm mesh envelope.",
            {
                "maximum_m": VERIFIED_HEIGHT_MAX_M,
                "received_m": too_high,
            },
        )
    return None


def build_production_sweep_design_packet(
    c2_review: dict,
    template_contract: dict,
    plan: dict | None = None,
    max_tasks: int = C3_MAX_TASKS,
) -> dict:
    if not _source_review_ok(c2_review):
        return _error(
            "source_review_not_passed",
            "Stage C3 requires a passing C2 software-chain review.",
        )

    selected_plan = copy.deepcopy(plan) if plan is not None else default_c3_production_plan()
    validated = validate_simulation_plan(selected_plan)
    if not validated["ok"]:
        return validated

    task_count = validated["task_count"]
    if task_count > max_tasks:
        return _error(
            "production_task_budget_exceeded",
            "Stage C3 production packet exceeds the allowed task budget.",
            {"task_count": task_count, "maximum": max_tasks},
        )

    height_error = _height_limit_error(validated["normalized_plan"])
    if height_error:
        return height_error

    contract_summary = template_contract_execution_summary(template_contract)
    if not contract_summary["ok"]:
        return _error(
            "template_contract_required",
            "A verified Stage B1 template contract is required for C3.",
            contract_summary.get("error", {}),
        )

    fingerprint = validated["plan_fingerprint"]
    plan_approval = approve_simulation_plan(
        validated["normalized_plan"],
        fingerprint,
    )["approval"]
    real_run_approval = {
        "approved": True,
        "approved_for": "real_run",
        "plan_fingerprint": fingerprint,
        "template_sha256": contract_summary["sha256"],
    }
    approval_check = validate_execution_approvals(
        validated,
        mode="real",
        plan_approval=plan_approval,
        real_run_approval=real_run_approval,
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
    return {
        "ok": True,
        "packet_version": C3_PACKET_VERSION,
        "stage": "C3",
        "status": "ready_for_human_approval",
        "mode": "real",
        "human_approval_required": True,
        "must_not_auto_start": True,
        "plan_fingerprint": fingerprint,
        "task_count": task_count,
        "max_tasks": max_tasks,
        "source_review": {
            "job_id": c2_review.get("job_id"),
            "software_chain_verdict": c2_review.get("software_chain_verdict"),
            "quality_task_counts": copy.deepcopy(c2_review.get("task_counts")),
            "phase_span_rad": (
                (c2_review.get("metrics") or {})
                .get("phase_rad", {})
                .get("span")
            ),
            "transmission_mean": (
                (c2_review.get("metrics") or {})
                .get("transmission", {})
                .get("mean")
            ),
        },
        "design_rationale": [
            "C1 validated the software chain but covered only 1.3273 rad phase span.",
            "Height is explored as a bounded phase-control dimension.",
            "Height values stop at 700 nm to stay inside the verified mesh envelope.",
            "The packet prepares the next run but does not start it.",
        ],
        "normalized_plan": copy.deepcopy(normalized),
        "defaults_applied": copy.deepcopy(validated["defaults_applied"]),
        "sweep": copy.deepcopy(normalized["sweep"]),
        "execution": {
            "resource": execution["resource"],
            "express_mode": execution["express_mode"],
            "processes": execution["processes"],
            "capacity": execution["capacity"],
            "hide": execution["hide"],
            "include_models": normalized["outputs"]["include_models"],
        },
        "template": {
            "path": contract_summary["path"],
            "sha256": contract_summary["sha256"],
            "contract_fingerprint": contract_summary["contract_fingerprint"],
        },
        "compiled_request": request,
        "approval_gate": {
            "candidate_plan_approval": plan_approval,
            "candidate_real_run_approval": real_run_approval,
            "approval_required_for_next_stage": (
                "A human must approve this exact C3 packet before Stage C4 "
                "may submit compiled_request to /jobs/start."
            ),
        },
        "acceptance_criteria": {
            "software": {
                "required_quality": "pass",
                "required_task_success_rate": 1.0,
                "expected_task_count": task_count,
            },
            "physical_review": {
                "required": True,
                "coarse_success_indicators": [
                    "At least one fixed-height row shows materially larger unwrapped phase span than C1.",
                    "Transmission remains high enough for human-selected candidate units.",
                    "No unexplained discontinuity is accepted without visual review of heatmaps.",
                ],
                "not_a_final_library": True,
            },
        },
        "checks": [
            _check_pass("source_review_passed", "C2 software-chain review passed."),
            _check_pass("plan_validated", "C3 SimulationPlan normalized successfully."),
            _check_pass("task_budget", "C3 task count is within the 25-task budget."),
            _check_pass("template_contract_verified", "Stage B1 template contract is verified."),
            _check_pass("cpu_express_mode", "Execution remains CPU with express_mode=0."),
            _check_pass("no_auto_start", "C3 packet generation does not call RPC."),
        ],
        "failed_checks": [],
        "operator_stop_criteria": [
            "Any task failure",
            "Template SHA mismatch",
            "Contract fingerprint mismatch",
            "Express mode not equal to 0",
            "Unexpected GPU/resource mismatch",
            "Lumerical license/resource error",
            "Any result suggesting mesh envelope violation",
        ],
        "next_step": (
            "Present this packet to the human. Only after explicit approval "
            "for this exact packet may Stage C4 start the real production "
            "discovery sweep."
        ),
    }
```

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_production_sweep_design.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/production_sweep_design.py tests/test_production_sweep_design.py
git commit -m "feat: build production sweep design packets"
```

---

### Task 2: Add CLI and Windows wrapper for C3 packet generation

**Files:**
- Create: `scripts/build_production_sweep_packet.py`
- Create: `scripts/windows/build_production_sweep_packet.bat`
- Modify: `tests/test_production_sweep_design.py`

**Interfaces:**
- Consumes:
  - `build_production_sweep_design_packet(c2_review, template_contract, plan=None, max_tasks=25) -> dict`
- Produces:
  - CLI:
    `python scripts/build_production_sweep_packet.py --review <review.json> --contract <contract.json> --output <packet.json>`
  - Windows wrapper:
    `scripts\windows\build_production_sweep_packet.bat`
  - Packet output:
    `runtime/approvals/production_sweep_c3_packet.json`

- [ ] **Step 1: Add failing CLI test**

Append this to `tests/test_production_sweep_design.py`:

```python
def test_production_sweep_packet_cli_writes_packet(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    from src.template_contract import atomic_write_json

    root = Path(__file__).resolve().parent.parent
    review_path = tmp_path / "review.json"
    contract_path = tmp_path / "contract.json"
    output_path = tmp_path / "production_sweep_c3_packet.json"
    atomic_write_json(review_path, valid_c2_review())
    atomic_write_json(contract_path, valid_b1_contract())

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "build_production_sweep_packet.py"),
            "--review",
            str(review_path),
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
    assert packet["task_count"] == 25
    assert "production_sweep_c3 status=ready_for_human_approval" in result.stdout
```

- [ ] **Step 2: Run test and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_production_sweep_design.py::test_production_sweep_packet_cli_writes_packet -q
```

Expected: FAIL because `scripts/build_production_sweep_packet.py` does not exist.

- [ ] **Step 3: Add CLI script**

Create `scripts/build_production_sweep_packet.py` with this content:

```python
#!/usr/bin/env python3
"""Build a Stage C3 production sweep approval packet."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.production_sweep_design import build_production_sweep_design_packet
from src.template_contract import atomic_write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review",
        default="runtime/reviews/job_20260619_213418_metasurface_sweep/review.json",
    )
    parser.add_argument(
        "--contract",
        default="templates/metasurface/base_model.contract.json",
    )
    parser.add_argument("--plan", default=None)
    parser.add_argument(
        "--output",
        default="runtime/approvals/production_sweep_c3_packet.json",
    )
    parser.add_argument("--max-tasks", type=int, default=25)
    return parser.parse_args()


def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    review = read_json(args.review)
    contract = read_json(args.contract)
    plan = read_json(args.plan) if args.plan else None
    packet = build_production_sweep_design_packet(
        review,
        contract,
        plan=plan,
        max_tasks=args.max_tasks,
    )
    atomic_write_json(args.output, packet)
    if packet.get("ok"):
        print(
            "production_sweep_c3 status=ready_for_human_approval "
            f"task_count={packet['task_count']} "
            f"plan_fingerprint={packet['plan_fingerprint']} "
            f"template_sha256={packet['template']['sha256']}"
        )
        return 0
    print(
        "production_sweep_c3 status=blocked "
        f"error={packet.get('error', {}).get('type')}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add Windows wrapper**

Create `scripts/windows/build_production_sweep_packet.bat` with this content:

```bat
@echo off
setlocal
cd /d "%~dp0\..\.."

if "%FDTD_PYTHON%"=="" (
  set "FDTD_PYTHON=F:\Program Files\Lumerical\v242\python\python.exe"
)

"%FDTD_PYTHON%" scripts\build_production_sweep_packet.py %*
exit /b %ERRORLEVEL%
```

- [ ] **Step 5: Run CLI tests and help checks**

Run:

```bash
.venv/bin/python -m pytest tests/test_production_sweep_design.py -q
.venv/bin/python scripts/build_production_sweep_packet.py --help
```

Expected:

- pytest reports `6 passed`.
- help output includes `--review`, `--contract`, `--output`, and `--max-tasks`.

- [ ] **Step 6: Commit**

Run:

```bash
git add scripts/build_production_sweep_packet.py scripts/windows/build_production_sweep_packet.bat tests/test_production_sweep_design.py
git commit -m "feat: add production sweep packet cli"
```

---

### Task 3: Add local-only MCP tool for production preflight

**Files:**
- Modify: `src/tools/plans.py`
- Modify: `tests/test_mcp_plan_tools.py`
- Modify: `tests/test_mcp_registration.py`

**Interfaces:**
- Consumes:
  - `build_production_sweep_design_packet(c2_review: dict, template_contract: dict, plan: dict | None = None, max_tasks: int = 25) -> dict`
- Produces:
  - MCP tool `fdtd_simulation_plan_production_preflight(c2_review: dict, template_contract: dict, plan: Optional[dict] = None, max_tasks: int = 25) -> dict`

- [ ] **Step 1: Add failing MCP tests**

Append this to `tests/test_mcp_plan_tools.py`:

```python
def test_production_preflight_is_local_only_and_does_not_call_rpc():
    from tests.test_production_sweep_design import valid_c2_review
    from tests.test_template_contract import valid_b1_contract

    tools, rpc = registered_tools()

    packet = tools["fdtd_simulation_plan_production_preflight"](
        c2_review=valid_c2_review(),
        template_contract=valid_b1_contract(),
    )

    assert packet["ok"] is True
    assert packet["stage"] == "C3"
    assert packet["status"] == "ready_for_human_approval"
    assert packet["task_count"] == 25
    assert rpc.calls == []
```

Modify `tests/test_mcp_registration.py` so the expected tool names include:

```python
"fdtd_simulation_plan_production_preflight",
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_mcp_plan_tools.py::test_production_preflight_is_local_only_and_does_not_call_rpc \
  tests/test_mcp_registration.py \
  -q
```

Expected: FAIL because the tool is not registered.

- [ ] **Step 3: Register MCP tool**

Modify `src/tools/plans.py`.

Add this import:

```python
from ..production_sweep_design import build_production_sweep_design_packet
```

Add this tool after `fdtd_simulation_plan_real_preflight`:

```python
    @mcp.tool()
    def fdtd_simulation_plan_production_preflight(
        c2_review: dict,
        template_contract: dict,
        plan: Optional[dict] = None,
        max_tasks: int = 25,
    ) -> dict:
        """
        Build a local Stage C3 production sweep packet without calling RPC.

        This uses the C2 real-result review and Stage B1 contract to prepare
        the next bounded real sweep for human approval. It does not start FDTD.
        """
        return build_production_sweep_design_packet(
            c2_review,
            template_contract,
            plan=plan,
            max_tasks=max_tasks,
        )
```

- [ ] **Step 4: Run MCP tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_plan_tools.py tests/test_mcp_registration.py -q
```

Expected: all MCP plan and registration tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/tools/plans.py tests/test_mcp_plan_tools.py tests/test_mcp_registration.py
git commit -m "feat: add production sweep preflight mcp tool"
```

---

### Task 4: Document Stage C3 workflow

**Files:**
- Modify: `README.md`
- Modify: `SOP.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Modify: `DEV_LOG.md`

**Interfaces:**
- Consumes:
  - Stage C3 packet builder and CLI from Tasks 1-2
- Produces:
  - Project docs that identify Stage C3 as current checkpoint
  - Repeatable SOP for generating production sweep design packets

- [ ] **Step 1: Update README checkpoint**

In `README.md`, update the current checkpoint bullet to:

```markdown
- 当前 checkpoint：Stage C3 production sweep design packet。C2 已完成 C1 真实 2×2 evidence 审计，软件链 `pass`，但 phase span 约 `1.3273 rad`，不足以作为最终 2π phase library。C3 的目标是生成下一轮有界真实 sweep 的审批包，默认 25 tasks（5 ratio × 5 height，fixed period 470 nm，CPU，EXPRESS_MODE=0，include_models=false），并停在人工审批；不自动启动 FDTD。
```

- [ ] **Step 2: Add SOP section**

Append this section to `SOP.md`:

```markdown
## SOP-014 - Stage C3 production sweep design packet

1. 确认 C2 `review.json` 存在，且 `software_chain_verdict=pass`。
2. 确认 Stage B1 `templates/metasurface/base_model.contract.json` 仍为 `verified`。
3. 运行：
   ```bash
   .venv/bin/python scripts/build_production_sweep_packet.py \
     --review runtime/reviews/job_20260619_213418_metasurface_sweep/review.json \
     --contract templates/metasurface/base_model.contract.json \
     --output runtime/approvals/production_sweep_c3_packet.json
   ```
4. 审核 packet：`status=ready_for_human_approval`、`task_count=25`、CPU、`express_mode=0`、`include_models=false`、template SHA 和 contract fingerprint 匹配。
5. C3 只生成 packet，不调用 `/jobs/start`，不 resume，不重启 RPC，不修改 `.fsp`。
6. 如果用户批准该 exact packet，后续进入 Stage C4 才允许提交 `compiled_request` 启动真实 sweep。
7. 若需要高度超过 700 nm 或改变 mesh/boundary/source/template，必须另起模板/mesh review，不得复用 C3 默认 packet。
```

- [ ] **Step 3: Add Windows runbook note**

Append this section to `docs/WINDOWS_RUNBOOK.md`:

```markdown
## Stage C3 production sweep packet

On Windows, after pulling the latest code and ensuring `base_model.contract.json` and the C2 review artifact exist:

```cmd
cd /d F:\lumerical-fdtd-auto-design\fdtd-auto-design
scripts\windows\build_production_sweep_packet.bat
```

Expected output contains:

```text
production_sweep_c3 status=ready_for_human_approval task_count=25
```

This command is local-only. It must not start FDTD, call `/jobs/start`, resume a job, or modify `.fsp` files.
```

- [ ] **Step 4: Add DEV_LOG entry**

Append this section to `DEV_LOG.md`:

```markdown
## 2026-06-19 - Stage C3 production sweep design packet

- 目标：基于 C2 真实结果审计，生成下一轮有界真实 sweep 的审批包，而不是直接启动求解。
- 设计：默认 25 tasks，`sweep.axis=height`，ratio `[0.2, 0.35, 0.5, 0.65, 0.8]`，height `[500, 550, 600, 650, 700] nm`，fixed period `470 nm`，CPU，`EXPRESS_MODE=0`，`include_models=false`。
- 安全边界：高度不超过 `700 nm`，保持在 Stage B0.1 已探测的 mesh envelope 内；高于 700 nm 的 taller-pillar 扫描需要单独模板/mesh 审核。
- 约束：C3 不启动 FDTD、不创建 job、不 resume、不重启 RPC、不修改模板或 `.fsp`。
- 后续：人工审批 exact C3 packet 后，Stage C4 才能启动真实 production-discovery sweep。
```

- [ ] **Step 5: Commit docs**

Run:

```bash
git add README.md SOP.md docs/WINDOWS_RUNBOOK.md DEV_LOG.md
git commit -m "docs: document Stage C3 production sweep packet"
```

---

### Task 5: Generate C3 packet locally and verify no real-run operations

**Files:**
- Runtime output only: `runtime/approvals/production_sweep_c3_packet.json`
- No source file changes unless verification results are added to `DEV_LOG.md`.

**Interfaces:**
- Consumes:
  - `runtime/reviews/job_20260619_213418_metasurface_sweep/review.json`
  - `templates/metasurface/base_model.contract.json`
  - `scripts/build_production_sweep_packet.py`
- Produces:
  - `runtime/approvals/production_sweep_c3_packet.json`
  - final verification report

- [ ] **Step 1: Generate the packet**

Run:

```bash
.venv/bin/python scripts/build_production_sweep_packet.py \
  --review runtime/reviews/job_20260619_213418_metasurface_sweep/review.json \
  --contract templates/metasurface/base_model.contract.json \
  --output runtime/approvals/production_sweep_c3_packet.json
```

Expected output contains:

```text
production_sweep_c3 status=ready_for_human_approval task_count=25
```

If the local checkout does not have runtime C2 review or contract files, copy them from Windows first, using the existing C2 evidence workflow. Do not copy `.fsp` files.

- [ ] **Step 2: Inspect packet headline**

Run:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
p = json.loads(Path("runtime/approvals/production_sweep_c3_packet.json").read_text())
print("status", p["status"])
print("stage", p["stage"])
print("task_count", p["task_count"])
print("axis", p["sweep"]["axis"])
print("ratio_values", p["sweep"]["ratio_values"])
print("height_values_m", p["sweep"]["height_values_m"])
print("resource", p["execution"]["resource"])
print("express_mode", p["execution"]["express_mode"])
print("include_models", p["execution"]["include_models"])
PY
```

Expected output:

```text
status ready_for_human_approval
stage C3
task_count 25
axis height
ratio_values [0.2, 0.35, 0.5, 0.65, 0.8]
height_values_m [5e-07, 5.5e-07, 6e-07, 6.5e-07, 7e-07]
resource CPU
express_mode 0
include_models False
```

- [ ] **Step 3: Confirm runtime packet is git-ignored**

Run:

```bash
git check-ignore runtime/approvals/production_sweep_c3_packet.json
```

Expected: the path is printed.

- [ ] **Step 4: Run compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exit code `0`.

- [ ] **Step 5: Run full pytest**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. The expected count is previous `285` plus the new C3 tests.

- [ ] **Step 6: Forbidden-operation scan**

Run:

```bash
! rg -n "jobs/start|fdtd_simulation_plan_start\\(|fdtd_job_start|fdtd_job_resume|runjobs|runanalysis|\\.run\\(|\\.save\\(|setnamed|addfdtd|addrect|addcircle|addmesh|addplane|addpower" src/production_sweep_design.py scripts/build_production_sweep_packet.py tests/test_production_sweep_design.py
```

Expected: no matches.

- [ ] **Step 7: Confirm no model files were created or copied**

Run:

```bash
find runtime/approvals runtime/reviews -name '*.fsp' -print
```

Expected: no output.

- [ ] **Step 8: Record final verification if needed**

If the final test counts or packet fingerprint are not yet in `DEV_LOG.md`, append a short verification bullet under the Stage C3 entry:

```markdown
- 验证：`compileall` exit 0；`pytest -q` 全量通过；forbidden-operation scan 无匹配；生成 `runtime/approvals/production_sweep_c3_packet.json`，`status=ready_for_human_approval`，`task_count=25`。
```

Then commit:

```bash
git add DEV_LOG.md
git commit -m "docs: record Stage C3 verification"
```

- [ ] **Step 9: Final report**

Report these categories:

```text
Stage C3 final report
1. Commit hashes for each task
2. Files created and modified
3. compileall result
4. pytest result
5. forbidden-operation scan result
6. C3 packet path
7. C3 packet status, task_count, plan_fingerprint
8. Sweep definition: axis, ratios, heights, fixed period
9. Execution settings: CPU, express_mode, processes, capacity, hide, include_models
10. Source C2 review summary used
11. Template SHA and contract fingerprint
12. Acceptance criteria and operator stop criteria
13. Confirmation no FDTD start, no /jobs/start, no resume, no RPC restart, no .fsp modification
14. git status and origin/main sync state
15. Recommended next stage
```

Recommended next stage:

```text
Stage C4: approved production-discovery real sweep.

Only after the human approves the exact C3 packet may Stage C4 submit
compiled_request to /jobs/start, poll the resulting job, retrieve
evidence-only outputs, and run a C4 result review. If the human does not
approve, no real run occurs.
```

---

## Self-Review

**Spec coverage:** The plan creates a C3 production sweep approval packet, uses C2 evidence, preserves all real-run approval gates, adds CLI/MCP/docs, and stops before any real run.

**Placeholder scan:** The plan contains exact file paths, function names, tests, commands, expected outputs, and commit messages.

**Type consistency:** The primary interfaces are consistent across tasks:

- `default_c3_production_plan() -> dict`
- `build_production_sweep_design_packet(c2_review: dict, template_contract: dict, plan: dict | None = None, max_tasks: int = 25) -> dict`
- `fdtd_simulation_plan_production_preflight(c2_review: dict, template_contract: dict, plan: Optional[dict] = None, max_tasks: int = 25) -> dict`

**Safety check:** C3 packet generation compiles a request shape but never calls RPC. Stage C4 is the first stage that may start a real job, and only after exact-packet approval.
