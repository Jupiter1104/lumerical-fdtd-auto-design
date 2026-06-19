#!/usr/bin/env python3
"""Generate a local review report from completed real-job evidence."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.real_result_review import (
    build_real_result_review,
    load_real_result_evidence,
    render_real_result_review_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build review.json and real_2x2_review.md from real job evidence."
        )
    )
    parser.add_argument(
        "--job-dir",
        required=True,
        help="Local copied job evidence directory.",
    )
    parser.add_argument(
        "--preflight",
        required=True,
        help="Local real_2x2_preflight.json path.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for review outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = load_real_result_evidence(
        Path(args.job_dir), Path(args.preflight)
    )
    review = build_real_result_review(evidence)
    (output_dir / "review.json").write_text(
        json.dumps(review, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "real_2x2_review.md").write_text(
        render_real_result_review_markdown(review),
        encoding="utf-8",
    )
    status = "pass" if review["ok"] else "fail"
    print(
        "status={status} job_id={job_id} software_chain_verdict={verdict}".format(
            status=status,
            job_id=review.get("job_id"),
            verdict=review.get("software_chain_verdict"),
        )
    )
    return 0 if review["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
