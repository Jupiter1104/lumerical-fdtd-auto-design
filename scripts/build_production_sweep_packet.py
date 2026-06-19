#!/usr/bin/env python3
"""Build a Stage C3 production sweep approval packet."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.production_sweep_design import (
    build_production_sweep_design_packet,
)
from src.template_contract import atomic_write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review",
        default=(
            "runtime/reviews/job_20260619_213418_metasurface_sweep/"
            "review.json"
        ),
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
