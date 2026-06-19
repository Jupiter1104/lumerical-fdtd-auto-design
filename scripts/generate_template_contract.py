"""Generate Stage B1 template contract from strict profile and probe JSON."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.template_contract import (
    atomic_write_json,
    generate_template_contract,
    validate_template_contract,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="templates/metasurface/template-inspection-profile.json",
    )
    parser.add_argument(
        "--probe",
        default="templates/metasurface/base_model.probe.json",
    )
    parser.add_argument(
        "--output",
        default="templates/metasurface/base_model.contract.json",
    )
    return parser.parse_args()


def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    profile = read_json(args.profile)
    probe = read_json(args.probe)
    contract = generate_template_contract(profile, probe)
    atomic_write_json(args.output, contract)
    validation = validate_template_contract(contract)
    if validation["ok"]:
        print(
            "template_contract status=verified "
            f"fingerprint={contract['contract_fingerprint']}"
        )
        return 0
    print(
        "template_contract status=unverified "
        f"errors={validation['errors']}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
