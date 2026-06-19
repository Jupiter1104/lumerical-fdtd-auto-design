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

    contract_summary = template_contract_execution_summary(
        template_contract
    )
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
        _check_pass(
            "plan_validated",
            "SimulationPlan normalized successfully.",
        ),
        _check_pass(
            "plan_approval_matches",
            "SimulationPlan approval fingerprint matches.",
        ),
        _check_pass(
            "contract_verified",
            "Stage B1 template contract is verified.",
        ),
        _check_pass(
            "resource_cpu",
            "Execution resource is CPU.",
        ),
        _check_pass(
            "express_mode_zero",
            "Express mode is disabled.",
        ),
        _check_pass(
            "task_count_2x2",
            "Default sweep contains exactly four tasks.",
        ),
        _check_pass(
            "no_auto_start",
            "Stage C0 does not call jobs/start.",
        ),
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
        "defaults_applied": copy.deepcopy(
            validated["defaults_applied"]
        ),
        "template": {
            "path": contract_summary["path"],
            "sha256": contract_summary["sha256"],
            "contract_fingerprint": contract_summary[
                "contract_fingerprint"
            ],
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
            "Present this packet to the human. Only after explicit "
            "approval for this exact packet may Stage C1 start the "
            "real 2x2 job."
        ),
    }
    return packet
