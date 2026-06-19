"""Tests for Stage C0 real run preflight packet builder."""

import json
from pathlib import Path

from src.template_contract import atomic_write_json


def _valid_b1_contract():
    from src.template_contract import generate_template_contract
    from tests.test_template_contract import (
        valid_b01_probe,
        valid_inspection_profile,
    )

    return generate_template_contract(
        valid_inspection_profile(),
        valid_b01_probe(),
    )


def _approved_default_plan():
    from src.simulation_plan import (
        approve_simulation_plan,
        validate_simulation_plan,
    )

    validated = validate_simulation_plan({})
    approval = approve_simulation_plan(
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]
    return validated, approval


def test_build_real_run_preflight_packet_for_default_2x2_plan():
    from src.real_run_preflight import build_real_run_preflight_packet

    validated, approval = _approved_default_plan()
    contract = _valid_b1_contract()

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
    assert (
        packet["template"]["sha256"]
        == contract["template"]["sha256"]
    )
    assert (
        packet["template"]["contract_fingerprint"]
        == contract["contract_fingerprint"]
    )
    assert packet["execution"]["resource"] == "CPU"
    assert packet["execution"]["express_mode"] == 0
    assert packet["execution"]["mesh_accuracy"] == 6
    assert packet["compiled_request"]["mode"] == "real"
    assert packet["human_approval_required"] is True
    assert packet["must_not_auto_start"] is True
    assert packet["failed_checks"] == []


def test_preflight_packet_rejects_missing_plan_approval():
    from src.real_run_preflight import build_real_run_preflight_packet

    packet = build_real_run_preflight_packet(
        {}, None, _valid_b1_contract()
    )

    assert packet["ok"] is False
    assert packet["error"]["type"] == "plan_approval_required"


def test_preflight_packet_rejects_unverified_contract():
    from src.real_run_preflight import build_real_run_preflight_packet

    validated, approval = _approved_default_plan()
    contract = _valid_b1_contract()
    contract["verified"] = False

    packet = build_real_run_preflight_packet(
        validated["normalized_plan"],
        approval,
        contract,
    )

    assert packet["ok"] is False
    assert packet["error"]["type"] == "template_contract_required"


def test_preflight_packet_rejects_task_count_not_equal_to_four():
    """Stage C0 is the first real 2x2 preflight — must reject non-4 tasks."""
    from src.real_run_preflight import build_real_run_preflight_packet

    # task_count=2: 1 ratio × 2 periods
    plan_2 = {
        "device": {"type": "metasurface_unit_cell"},
        "sweep": {
            "axis": "period",
            "ratio_values": [0.5],
            "period_values_m": [3.9e-7, 5.4e-7],
        },
    }
    validated_2, approval_2 = _approved_default_plan()
    # Use the smaller plan for validation but approved default plan
    from src.simulation_plan import (
        approve_simulation_plan,
        validate_simulation_plan,
    )
    v2 = validate_simulation_plan(plan_2)
    app2 = approve_simulation_plan(
        v2["normalized_plan"], v2["plan_fingerprint"]
    )["approval"]
    assert v2["task_count"] == 2  # precondition
    p2 = build_real_run_preflight_packet(
        v2["normalized_plan"], app2, _valid_b1_contract()
    )
    assert p2["ok"] is False
    assert p2["error"]["type"] == "preflight_task_count_mismatch"
    assert p2["error"]["details"]["expected"] == 4
    assert p2["error"]["details"]["actual"] == 2

    # task_count=6: 3 ratios × 2 periods
    plan_6 = {
        "device": {"type": "metasurface_unit_cell"},
        "sweep": {
            "axis": "period",
            "ratio_values": [0.2, 0.5, 0.8],
            "period_values_m": [3.9e-7, 5.4e-7],
        },
    }
    v6 = validate_simulation_plan(plan_6)
    app6 = approve_simulation_plan(
        v6["normalized_plan"], v6["plan_fingerprint"]
    )["approval"]
    assert v6["task_count"] == 6  # precondition
    p6 = build_real_run_preflight_packet(
        v6["normalized_plan"], app6, _valid_b1_contract()
    )
    assert p6["ok"] is False
    assert p6["error"]["type"] == "preflight_task_count_mismatch"
    assert p6["error"]["details"]["actual"] == 6


def test_default_plan_still_has_task_count_four():
    """Sanity check: default empty plan must remain task_count=4."""
    from src.real_run_preflight import build_real_run_preflight_packet

    validated, approval = _approved_default_plan()
    contract = _valid_b1_contract()
    assert validated["task_count"] == 4
    packet = build_real_run_preflight_packet(
        validated["normalized_plan"], approval, contract
    )
    assert packet["ok"] is True
    assert packet["task_count"] == 4
    assert packet["status"] == "ready_for_human_approval"


# --- CLI test (Task C0-5) ---


ROOT = Path(__file__).resolve().parent.parent


def test_preflight_cli_writes_packet(tmp_path):
    import subprocess
    import sys

    plan_path = tmp_path / "plan.json"
    approval_path = tmp_path / "plan_approval.json"
    contract_path = tmp_path / "contract.json"
    output_path = tmp_path / "packet.json"
    validated, approval = _approved_default_plan()
    atomic_write_json(plan_path, {})
    atomic_write_json(approval_path, approval)
    atomic_write_json(contract_path, _valid_b1_contract())

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_real_run_preflight_packet.py"),
            "--plan",
            str(plan_path),
            "--plan-approval",
            str(approval_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    packet = json.loads(output_path.read_text(encoding="utf-8"))
    assert packet["status"] == "ready_for_human_approval"
    assert "status=ready_for_human_approval" in result.stdout
