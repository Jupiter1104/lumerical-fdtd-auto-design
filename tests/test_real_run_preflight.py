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
