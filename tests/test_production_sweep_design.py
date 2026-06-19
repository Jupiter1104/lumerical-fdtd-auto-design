"""Tests for Stage C3 production sweep design packet builder."""

import json
from pathlib import Path

from tests.test_template_contract import valid_b1_contract


TEMPLATE_SHA = (
    "03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176"
)
# Contract fingerprint is generated from valid_b1_contract() — not hardcoded.
# Real Stage B1 fingerprint: bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1


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
    from src.production_sweep_design import (
        build_production_sweep_design_packet,
    )

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
    assert (
        packet["source_review"]["job_id"]
        == "job_20260619_213418_metasurface_sweep"
    )
    assert packet["source_review"]["software_chain_verdict"] == "pass"
    assert packet["template"]["sha256"] == TEMPLATE_SHA
    assert len(packet["template"]["contract_fingerprint"]) == 64
    assert (
        packet["template"]["contract_fingerprint"]
        == valid_b1_contract()["contract_fingerprint"]
    )
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
    assert (
        packet["compiled_request"]["job_type"]
        == "metasurface-sweep"
    )
    assert packet["failed_checks"] == []
    assert (
        packet["approval_gate"]["candidate_plan_approval"][
            "approved_for"
        ]
        == "simulation_plan"
    )
    assert (
        packet["approval_gate"]["candidate_real_run_approval"][
            "approved_for"
        ]
        == "real_run"
    )


def test_packet_rejects_failed_c2_review():
    from src.production_sweep_design import (
        build_production_sweep_design_packet,
    )

    review = valid_c2_review()
    review["software_chain_verdict"] = "fail"

    packet = build_production_sweep_design_packet(
        review, valid_b1_contract()
    )

    assert packet["ok"] is False
    assert packet["error"]["type"] == "source_review_not_passed"


def test_packet_rejects_task_count_above_c3_budget():
    from src.production_sweep_design import (
        build_production_sweep_design_packet,
    )

    plan = {
        "sweep": {
            "axis": "height",
            "ratio_values": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            "height_values_m": [
                5e-7, 5.5e-7, 6e-7, 6.5e-7, 7e-7,
            ],
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
    assert packet["error"]["details"] == {
        "task_count": 30,
        "maximum": 25,
    }


def test_packet_rejects_height_above_verified_mesh_envelope():
    from src.production_sweep_design import (
        build_production_sweep_design_packet,
    )

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


# --- CLI test (Task C3-2) ---


def test_production_sweep_packet_cli_writes_packet(tmp_path):
    import subprocess
    import sys

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
            str(
                root
                / "scripts"
                / "build_production_sweep_packet.py"
            ),
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
    assert (
        "production_sweep_c3 status=ready_for_human_approval"
        in result.stdout
    )
