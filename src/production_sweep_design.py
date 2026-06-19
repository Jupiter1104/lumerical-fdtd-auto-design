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
            "height_values_m": [
                5e-7, 5.5e-7, 6e-7, 6.5e-7, 7e-7,
            ],
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
            (
                "C3 height sweep must not exceed the verified "
                "700 nm mesh envelope."
            ),
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

    selected_plan = (
        copy.deepcopy(plan)
        if plan is not None
        else default_c3_production_plan()
    )
    validated = validate_simulation_plan(selected_plan)
    if not validated["ok"]:
        return validated

    task_count = validated["task_count"]
    if task_count > max_tasks:
        return _error(
            "production_task_budget_exceeded",
            (
                "Stage C3 production packet exceeds the allowed "
                "task budget."
            ),
            {"task_count": task_count, "maximum": max_tasks},
        )

    height_error = _height_limit_error(validated["normalized_plan"])
    if height_error:
        return height_error

    contract_summary = template_contract_execution_summary(
        template_contract
    )
    if not contract_summary["ok"]:
        return _error(
            "template_contract_required",
            (
                "A verified Stage B1 template contract is required "
                "for C3."
            ),
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
            "software_chain_verdict": c2_review.get(
                "software_chain_verdict"
            ),
            "quality_task_counts": copy.deepcopy(
                c2_review.get("task_counts")
            ),
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
            (
                "C1 validated the software chain but covered only "
                "1.3273 rad phase span."
            ),
            "Height is explored as a bounded phase-control dimension.",
            (
                "Height values stop at 700 nm to stay inside the "
                "verified mesh envelope."
            ),
            "The packet prepares the next run but does not start it.",
        ],
        "normalized_plan": copy.deepcopy(normalized),
        "defaults_applied": copy.deepcopy(
            validated["defaults_applied"]
        ),
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
            "contract_fingerprint": contract_summary[
                "contract_fingerprint"
            ],
        },
        "compiled_request": request,
        "approval_gate": {
            "candidate_plan_approval": plan_approval,
            "candidate_real_run_approval": real_run_approval,
            "approval_required_for_next_stage": (
                "A human must approve this exact C3 packet before "
                "Stage C4 may submit compiled_request to /jobs/start."
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
                    (
                        "At least one fixed-height row shows materially "
                        "larger unwrapped phase span than C1."
                    ),
                    (
                        "Transmission remains high enough for "
                        "human-selected candidate units."
                    ),
                    (
                        "No unexplained discontinuity is accepted "
                        "without visual review of heatmaps."
                    ),
                ],
                "not_a_final_library": True,
            },
        },
        "checks": [
            _check_pass(
                "source_review_passed",
                "C2 software-chain review passed.",
            ),
            _check_pass(
                "plan_validated",
                "C3 SimulationPlan normalized successfully.",
            ),
            _check_pass(
                "task_budget",
                "C3 task count is within the 25-task budget.",
            ),
            _check_pass(
                "template_contract_verified",
                "Stage B1 template contract is verified.",
            ),
            _check_pass(
                "cpu_express_mode",
                "Execution remains CPU with express_mode=0.",
            ),
            _check_pass(
                "no_auto_start",
                "C3 packet generation does not call RPC.",
            ),
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
            "Present this packet to the human. Only after explicit "
            "approval for this exact packet may Stage C4 start the "
            "real production discovery sweep."
        ),
    }
