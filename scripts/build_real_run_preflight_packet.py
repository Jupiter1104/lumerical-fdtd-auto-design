"""Build a real 2x2 SimulationPlan preflight approval packet."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.real_run_preflight import build_real_run_preflight_packet
from src.simulation_plan import (
    approve_simulation_plan,
    validate_simulation_plan,
)
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
