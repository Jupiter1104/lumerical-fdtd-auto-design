# Real Result Review Evidence Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrieve the Stage C1 real 2×2 SimulationPlan evidence, build an auditable local review report, and separate software-chain pass/fail from human physical review.

**Architecture:** Stage C2 is an evidence and review layer only. It copies evidence-first artifacts from the already completed Windows job into a git-ignored local review directory, parses JSON/CSV evidence with pure Python, checks the preflight → real job → result chain for consistency, and writes `review.json` plus a human-readable Markdown report. It must not start, resume, or modify any FDTD job.

**Tech Stack:** Python 3.10+ standard library, pytest, existing `/jobs/*` evidence layout, existing `runtime/approvals/real_2x2_preflight.json`, Windows OpenSSH/scp for evidence retrieval, Markdown report output.

## Global Constraints

- Do not start FDTD, do not create a new real job, and do not call `/jobs/start`.
- Do not call `fdtd_simulation_plan_start(mode="real")`, `fdtd_job_start`, or `fdtd_job_resume`.
- Do not restart Windows RPC services.
- Do not modify `.fsp` files, do not save templates, and do not call `run`, `runjobs`, `runanalysis`, `save`, `set`, `setnamed`, `delete`, `add*`, `putv`, or `importdataset`.
- Do not modify `src/native_sweep.py`, `src/job_store.py`, or real-run execution behavior.
- Default evidence retrieval must exclude `models/*.fsp`; model files are debug assets and require separate explicit approval.
- Use only evidence from the completed C1 job: `job_20260619_213418_metasurface_sweep`.
- Expected C1 job state is `succeeded` with `4` succeeded tasks, `0` failed tasks, and quality conclusion `pass`.
- Expected C1 template SHA-256 is `03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176`.
- Expected C1 Stage B1 contract fingerprint is `bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1`.
- Expected C1 SimulationPlan fingerprint is `e8c957df2c8112c876142998ecb088fa9c78f4a6c34037834a1cddae24c87810`.
- Physical conclusion must remain human-reviewed: a 2×2 sweep is a software-chain validation, not a final metasurface design library.

---

## Current Baseline

Stage C1 real 2×2 run has already completed:

- RPC route used: `POST http://127.0.0.1:5501/jobs/start` through SSH tunnel to Windows `127.0.0.1:5000`.
- Response: HTTP `202`.
- Job ID: `job_20260619_213418_metasurface_sweep`.
- Job state: `succeeded`.
- Task counts: `4 succeeded / 0 failed / 4 total`.
- Quality report: `conclusion=pass`, `valid_count=4`, `missing_count=0`, `requires_human_review=true`.
- Evidence files on Windows:
  - `summary.json`
  - `quality_report.json`
  - `results/sweep_results.csv`
  - `results/sweep_summary.json`
  - `evidence/index.json`
  - `evidence/transmission_heatmap.svg`
  - `evidence/phase_heatmap.svg`
- Result table:
  - `task_0001`: ratio `0.2`, period `390e-9`, transmission `0.9672581224386152`, phase `-0.6737631333967985`
  - `task_0002`: ratio `0.8`, period `390e-9`, transmission `0.7300105242892926`, phase `-1.9698575481531564`
  - `task_0003`: ratio `0.2`, period `540e-9`, transmission `0.9679605819741104`, phase `-0.6426061423354885`
  - `task_0004`: ratio `0.8`, period `540e-9`, transmission `0.9353412881476056`, phase `-0.9494834757797856`

Derived C2 physical-review metrics:

- Transmission min: `0.7300105242892926`
- Transmission max: `0.9679605819741104`
- Transmission mean: `0.9001426292124059`
- Phase min: `-1.9698575481531564`
- Phase max: `-0.6426061423354885`
- Phase span: `1.3272514058176679` rad, about `76.046` degrees
- Review note: phase coverage is far below `2π`; do not use this 2×2 result as a final phase library.

## File Structure

- Create `src/real_result_review.py`: pure local parser, consistency checker, metrics calculator, and Markdown renderer.
- Create `tests/test_real_result_review.py`: unit tests for C1 evidence parsing, chain checks, metric calculations, and fail-closed behavior.
- Create `scripts/collect_real_result_review.py`: CLI that reads a local evidence directory and writes `review.json` plus `real_2x2_review.md`.
- Modify `README.md`: update checkpoint from C0/C1 to C2 evidence review and next C3 planning.
- Modify `SOP.md`: add Stage C2 real-result review workflow.
- Modify `DEV_LOG.md`: record C2 implementation, copied evidence files, metrics, and verification commands.
- Optional runtime output, not committed: `runtime/reviews/job_20260619_213418_metasurface_sweep/`.

---

### Task 1: Add pure real result review module

**Files:**
- Create: `src/real_result_review.py`
- Create: `tests/test_real_result_review.py`

**Interfaces:**
- Consumes:
  - `summary.json`
  - `status.json`
  - `manifest.json`
  - `quality_report.json`
  - `results/sweep_results.csv`
  - `results/sweep_summary.json`
  - `evidence/index.json`
  - optional preflight packet JSON
- Produces:
  - `load_real_result_evidence(job_dir: Path, preflight_path: Path | None = None) -> dict`
  - `build_real_result_review(evidence: dict) -> dict`
  - `render_real_result_review_markdown(review: dict) -> str`

- [ ] **Step 1: Write failing tests**

Create `tests/test_real_result_review.py` with this content:

```python
import json
from pathlib import Path


JOB_ID = "job_20260619_213418_metasurface_sweep"
PLAN_FINGERPRINT = (
    "e8c957df2c8112c876142998ecb088fa9c78f4a6c34037834a1cddae24c87810"
)
TEMPLATE_SHA = (
    "03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176"
)
CONTRACT_FINGERPRINT = (
    "bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1"
)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_c1_fixture(root: Path) -> tuple[Path, Path]:
    job_dir = root / JOB_ID
    write_json(
        job_dir / "manifest.json",
        {
            "job_id": JOB_ID,
            "job_type": "metasurface-sweep",
            "mode": "real",
            "template": {"sha256": TEMPLATE_SHA},
            "paths": {"job_dir": str(job_dir)},
        },
    )
    write_json(
        job_dir / "status.json",
        {"job_id": JOB_ID, "state": "succeeded", "message": "Job succeeded."},
    )
    write_json(
        job_dir / "summary.json",
        {
            "job_id": JOB_ID,
            "task_counts": {"total": 4, "pending": 0, "running": 0, "succeeded": 4, "failed": 0},
            "results": [],
        },
    )
    write_json(
        job_dir / "quality_report.json",
        {
            "job_id": JOB_ID,
            "result_completeness": {"valid_count": 4, "missing_count": 0, "total_count": 4},
            "physical_checks": [{"name": "transmission_range", "status": "pass"}],
            "conclusion": "pass",
            "requires_human_review": True,
        },
    )
    write_json(
        job_dir / "results" / "sweep_summary.json",
        {
            "job_id": JOB_ID,
            "valid_count": 4,
            "missing_count": 0,
            "total_count": 4,
            "result_files": [
                "results/task_0001.json",
                "results/task_0002.json",
                "results/task_0003.json",
                "results/task_0004.json",
            ],
            "figure_files": [
                "evidence/transmission_heatmap.svg",
                "evidence/phase_heatmap.svg",
            ],
            "model_files": [],
        },
    )
    (job_dir / "results").mkdir(parents=True, exist_ok=True)
    (job_dir / "results" / "sweep_results.csv").write_text(
        "\n".join(
            [
                "task_id,sample_index,ratio,height,period,transmission,phase_rad",
                "task_0001,0,0.2,7e-07,3.9e-07,0.9672581224386152,-0.6737631333967985",
                "task_0002,1,0.8,7e-07,3.9e-07,0.7300105242892926,-1.9698575481531564",
                "task_0003,2,0.2,7e-07,5.4e-07,0.9679605819741104,-0.6426061423354885",
                "task_0004,3,0.8,7e-07,5.4e-07,0.9353412881476056,-0.9494834757797856",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    write_json(
        job_dir / "evidence" / "index.json",
        {
            "job_id": JOB_ID,
            "summary_files": [
                "summary.json",
                "quality_report.json",
                "results/sweep_summary.json",
                "results/sweep_results.csv",
            ],
            "result_files": [
                "results/task_0001.json",
                "results/task_0002.json",
                "results/task_0003.json",
                "results/task_0004.json",
            ],
            "figure_files": [
                "evidence/transmission_heatmap.svg",
                "evidence/phase_heatmap.svg",
            ],
            "model_files": [],
            "download_policy": {"include_models": False, "default_payload": "evidence-only"},
        },
    )
    (job_dir / "evidence" / "transmission_heatmap.svg").write_text("<svg />\n", encoding="utf-8")
    (job_dir / "evidence" / "phase_heatmap.svg").write_text("<svg />\n", encoding="utf-8")
    preflight_path = root / "real_2x2_preflight.json"
    write_json(
        preflight_path,
        {
            "ok": True,
            "status": "ready_for_human_approval",
            "plan_fingerprint": PLAN_FINGERPRINT,
            "task_count": 4,
            "template": {
                "sha256": TEMPLATE_SHA,
                "contract_fingerprint": CONTRACT_FINGERPRINT,
            },
            "compiled_request": {"mode": "real", "sweep": {"include_models": False}},
        },
    )
    return job_dir, preflight_path


def test_build_real_result_review_for_c1_fixture(tmp_path):
    from src.real_result_review import (
        build_real_result_review,
        load_real_result_evidence,
    )

    job_dir, preflight_path = write_c1_fixture(tmp_path)
    evidence = load_real_result_evidence(job_dir, preflight_path)
    review = build_real_result_review(evidence)

    assert review["ok"] is True
    assert review["job_id"] == JOB_ID
    assert review["software_chain_verdict"] == "pass"
    assert review["physical_review"]["required"] is True
    assert review["physical_review"]["conclusion"] == "human_review_required"
    assert review["task_counts"] == {"total": 4, "succeeded": 4, "failed": 0}
    assert review["chain_consistency"]["template_sha256"]["status"] == "pass"
    assert review["chain_consistency"]["plan_fingerprint"]["status"] == "pass"
    assert review["chain_consistency"]["model_files_excluded"]["status"] == "pass"
    assert review["metrics"]["transmission"]["min"] == 0.7300105242892926
    assert review["metrics"]["transmission"]["max"] == 0.9679605819741104
    assert review["metrics"]["transmission"]["mean"] == 0.9001426292124059
    assert review["metrics"]["phase_rad"]["span"] == 1.3272514058176679
    assert review["metrics"]["phase_rad"]["span_degrees"] == 76.046


def test_review_fails_closed_when_quality_missing(tmp_path):
    from src.real_result_review import (
        build_real_result_review,
        load_real_result_evidence,
    )

    job_dir, preflight_path = write_c1_fixture(tmp_path)
    (job_dir / "quality_report.json").unlink()
    evidence = load_real_result_evidence(job_dir, preflight_path)
    review = build_real_result_review(evidence)

    assert review["ok"] is False
    assert review["software_chain_verdict"] == "fail"
    assert "quality_report" in review["missing_files"]


def test_render_real_result_review_markdown_contains_key_metrics(tmp_path):
    from src.real_result_review import (
        build_real_result_review,
        load_real_result_evidence,
        render_real_result_review_markdown,
    )

    job_dir, preflight_path = write_c1_fixture(tmp_path)
    review = build_real_result_review(load_real_result_evidence(job_dir, preflight_path))
    markdown = render_real_result_review_markdown(review)

    assert "# Real 2x2 SimulationPlan Result Review" in markdown
    assert "Software-chain verdict: pass" in markdown
    assert "Phase span: 1.3272514058176679 rad" in markdown
    assert "not a final phase library" in markdown
```

- [ ] **Step 2: Run tests and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_result_review.py -q
```

Expected: FAIL because `src.real_result_review` does not exist.

- [ ] **Step 3: Add minimal implementation**

Create `src/real_result_review.py` with this content:

```python
"""Pure local review helpers for completed real metasurface jobs."""

import csv
import json
import math
from pathlib import Path


EXPECTED_PLAN_FINGERPRINT = (
    "e8c957df2c8112c876142998ecb088fa9c78f4a6c34037834a1cddae24c87810"
)
EXPECTED_TEMPLATE_SHA256 = (
    "03ba1f3ea9db6e86caa9c5458bcf84b6adb92db6c0664e60f262e2f5edde0176"
)
EXPECTED_CONTRACT_FINGERPRINT = (
    "bdfe2fceccbaeeadd3bcc0c349708b15d56c3b0090349037e726f475f63413d1"
)


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _float_rows(rows: list[dict]) -> list[dict]:
    converted = []
    for row in rows:
        item = dict(row)
        for key in ("sample_index", "ratio", "height", "period", "transmission", "phase_rad"):
            if key in item and item[key] not in ("", None):
                item[key] = float(item[key])
        converted.append(item)
    return converted


def _stat(values: list[float]) -> dict:
    if not values:
        return {"min": None, "max": None, "mean": None, "span": None}
    minimum = min(values)
    maximum = max(values)
    return {
        "min": minimum,
        "max": maximum,
        "mean": sum(values) / len(values),
        "span": maximum - minimum,
    }


def _check(name: str, status: str, message: str, details=None) -> dict:
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details or {},
    }


def load_real_result_evidence(job_dir: Path, preflight_path: Path | None = None) -> dict:
    job_dir = Path(job_dir)
    paths = {
        "manifest": job_dir / "manifest.json",
        "status": job_dir / "status.json",
        "summary": job_dir / "summary.json",
        "quality_report": job_dir / "quality_report.json",
        "sweep_summary": job_dir / "results" / "sweep_summary.json",
        "sweep_results_csv": job_dir / "results" / "sweep_results.csv",
        "evidence_index": job_dir / "evidence" / "index.json",
    }
    missing_files = [
        name
        for name, path in paths.items()
        if name != "sweep_results_csv" and not path.exists()
    ]
    if not paths["sweep_results_csv"].exists():
        missing_files.append("sweep_results_csv")

    preflight = _read_json(Path(preflight_path)) if preflight_path else None
    return {
        "job_dir": str(job_dir),
        "preflight_path": str(preflight_path) if preflight_path else None,
        "manifest": _read_json(paths["manifest"]),
        "status": _read_json(paths["status"]),
        "summary": _read_json(paths["summary"]),
        "quality_report": _read_json(paths["quality_report"]),
        "sweep_summary": _read_json(paths["sweep_summary"]),
        "sweep_results": _float_rows(_read_csv(paths["sweep_results_csv"])),
        "evidence_index": _read_json(paths["evidence_index"]),
        "preflight": preflight,
        "missing_files": missing_files,
    }


def _chain_consistency(evidence: dict) -> dict:
    manifest = evidence.get("manifest") or {}
    quality = evidence.get("quality_report") or {}
    summary = evidence.get("summary") or {}
    status_doc = evidence.get("status") or {}
    evidence_index = evidence.get("evidence_index") or {}
    preflight = evidence.get("preflight") or {}

    task_counts = summary.get("task_counts") or {}
    template_sha = (manifest.get("template") or {}).get("sha256")
    preflight_template = preflight.get("template") or {}
    checks = {}
    checks["job_state"] = _check(
        "job_state",
        "pass" if status_doc.get("state") == "succeeded" else "fail",
        "Job state is succeeded." if status_doc.get("state") == "succeeded" else "Job state is not succeeded.",
        {"actual": status_doc.get("state")},
    )
    checks["task_counts"] = _check(
        "task_counts",
        "pass" if task_counts.get("total") == 4 and task_counts.get("succeeded") == 4 and task_counts.get("failed") == 0 else "fail",
        "All four C1 tasks succeeded.",
        {"actual": task_counts},
    )
    completeness = quality.get("result_completeness") or {}
    checks["quality_report"] = _check(
        "quality_report",
        "pass" if quality.get("conclusion") == "pass" and completeness.get("valid_count") == 4 and completeness.get("missing_count") == 0 else "fail",
        "Quality report passed with four valid samples.",
        {"conclusion": quality.get("conclusion"), "result_completeness": completeness},
    )
    checks["template_sha256"] = _check(
        "template_sha256",
        "pass" if template_sha == EXPECTED_TEMPLATE_SHA256 and preflight_template.get("sha256") == EXPECTED_TEMPLATE_SHA256 else "fail",
        "Template SHA matches the approved Stage C0 packet and C1 manifest.",
        {"manifest": template_sha, "preflight": preflight_template.get("sha256")},
    )
    checks["contract_fingerprint"] = _check(
        "contract_fingerprint",
        "pass" if preflight_template.get("contract_fingerprint") == EXPECTED_CONTRACT_FINGERPRINT else "fail",
        "Stage B1 contract fingerprint matches the approved packet.",
        {"preflight": preflight_template.get("contract_fingerprint")},
    )
    checks["plan_fingerprint"] = _check(
        "plan_fingerprint",
        "pass" if preflight.get("plan_fingerprint") == EXPECTED_PLAN_FINGERPRINT else "fail",
        "SimulationPlan fingerprint matches the approved C0 packet.",
        {"preflight": preflight.get("plan_fingerprint")},
    )
    download_policy = evidence_index.get("download_policy") or {}
    checks["model_files_excluded"] = _check(
        "model_files_excluded",
        "pass" if not evidence_index.get("model_files") and download_policy.get("include_models") is False else "fail",
        "Default evidence payload excludes per-point .fsp models.",
        {"model_files": evidence_index.get("model_files"), "download_policy": download_policy},
    )
    return checks


def build_real_result_review(evidence: dict) -> dict:
    rows = evidence.get("sweep_results") or []
    transmissions = [float(row["transmission"]) for row in rows if row.get("transmission") is not None]
    phases = [float(row["phase_rad"]) for row in rows if row.get("phase_rad") is not None]
    phase_stat = _stat(phases)
    if phase_stat["span"] is not None:
        phase_stat["span_degrees"] = round(phase_stat["span"] * 180.0 / math.pi, 3)

    checks = _chain_consistency(evidence)
    missing_files = list(evidence.get("missing_files") or [])
    ok = not missing_files and all(check["status"] == "pass" for check in checks.values())
    summary = evidence.get("summary") or {}
    task_counts = summary.get("task_counts") or {}
    review = {
        "ok": ok,
        "job_id": summary.get("job_id") or (evidence.get("status") or {}).get("job_id"),
        "software_chain_verdict": "pass" if ok else "fail",
        "missing_files": missing_files,
        "task_counts": {
            "total": task_counts.get("total"),
            "succeeded": task_counts.get("succeeded"),
            "failed": task_counts.get("failed"),
        },
        "chain_consistency": checks,
        "metrics": {
            "transmission": _stat(transmissions),
            "phase_rad": phase_stat,
            "sample_count": len(rows),
        },
        "physical_review": {
            "required": True,
            "conclusion": "human_review_required",
            "note": (
                "The real 2x2 run validates the software chain. "
                "Phase coverage is far below 2π, so this is not a final phase library."
            ),
        },
        "evidence_policy": "evidence-only",
    }
    return review


def render_real_result_review_markdown(review: dict) -> str:
    metrics = review["metrics"]
    transmission = metrics["transmission"]
    phase = metrics["phase_rad"]
    checks = review["chain_consistency"]
    lines = [
        "# Real 2x2 SimulationPlan Result Review",
        "",
        f"- Job ID: `{review['job_id']}`",
        f"- Software-chain verdict: {review['software_chain_verdict']}",
        f"- Physical review: {review['physical_review']['conclusion']}",
        f"- Task counts: {review['task_counts']['succeeded']} succeeded / {review['task_counts']['failed']} failed / {review['task_counts']['total']} total",
        "",
        "## Chain consistency",
        "",
    ]
    for name, check in checks.items():
        lines.append(f"- {name}: {check['status']} — {check['message']}")
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            f"- Transmission min/max/mean: {transmission['min']} / {transmission['max']} / {transmission['mean']}",
            f"- Phase span: {phase['span']} rad ({phase.get('span_degrees')} degrees)",
            "",
            "## Physical interpretation",
            "",
            (
                "This 2×2 run is a real solver validation of the automation chain, "
                "not a final phase library. The phase span is far below 2π, so a "
                "larger approved sweep is required before design use."
            ),
            "",
        ]
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_result_review.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/real_result_review.py tests/test_real_result_review.py
git commit -m "feat: review real metasurface result evidence"
```

---

### Task 2: Add local CLI for generating review artifacts

**Files:**
- Create: `scripts/collect_real_result_review.py`
- Modify: `tests/test_real_result_review.py`

**Interfaces:**
- Consumes:
  - `load_real_result_evidence(job_dir: Path, preflight_path: Path | None = None) -> dict`
  - `build_real_result_review(evidence: dict) -> dict`
  - `render_real_result_review_markdown(review: dict) -> str`
- Produces:
  - CLI command:
    `python scripts/collect_real_result_review.py --job-dir <dir> --preflight <file> --output-dir <dir>`
  - `review.json`
  - `real_2x2_review.md`

- [ ] **Step 1: Add failing CLI test**

Append this to `tests/test_real_result_review.py`:

```python
def test_collect_real_result_review_cli_writes_json_and_markdown(tmp_path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent
    job_dir, preflight_path = write_c1_fixture(tmp_path)
    output_dir = tmp_path / "review"

    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "collect_real_result_review.py"),
            "--job-dir",
            str(job_dir),
            "--preflight",
            str(preflight_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    review = json.loads((output_dir / "review.json").read_text(encoding="utf-8"))
    markdown = (output_dir / "real_2x2_review.md").read_text(encoding="utf-8")
    assert review["software_chain_verdict"] == "pass"
    assert "status=pass" in result.stdout
    assert "Software-chain verdict: pass" in markdown
```

- [ ] **Step 2: Run test and confirm RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_result_review.py::test_collect_real_result_review_cli_writes_json_and_markdown -q
```

Expected: FAIL because `scripts/collect_real_result_review.py` does not exist.

- [ ] **Step 3: Add CLI script**

Create `scripts/collect_real_result_review.py` with this content:

```python
#!/usr/bin/env python3
"""Generate a local review report from completed real-job evidence."""

import argparse
import json
from pathlib import Path

from src.real_result_review import (
    build_real_result_review,
    load_real_result_evidence,
    render_real_result_review_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build review.json and real_2x2_review.md from real job evidence."
    )
    parser.add_argument("--job-dir", required=True, help="Local copied job evidence directory.")
    parser.add_argument("--preflight", required=True, help="Local real_2x2_preflight.json path.")
    parser.add_argument("--output-dir", required=True, help="Directory for review outputs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = load_real_result_evidence(Path(args.job_dir), Path(args.preflight))
    review = build_real_result_review(evidence)
    (output_dir / "review.json").write_text(
        json.dumps(review, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
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
```

- [ ] **Step 4: Run CLI tests and help check**

Run:

```bash
.venv/bin/python -m pytest tests/test_real_result_review.py -q
.venv/bin/python scripts/collect_real_result_review.py --help
```

Expected:

- pytest reports `4 passed`.
- help output includes `Build review.json and real_2x2_review.md`.

- [ ] **Step 5: Commit**

```bash
git add scripts/collect_real_result_review.py tests/test_real_result_review.py
git commit -m "feat: add real result review cli"
```

---

### Task 3: Retrieve C1 evidence-only artifacts from Windows and generate the review

**Files:**
- Runtime output only: `runtime/reviews/job_20260619_213418_metasurface_sweep/`
- No source files modified in this task.

**Interfaces:**
- Consumes:
  - Windows project path: `F:\lumerical-fdtd-auto-design\fdtd-auto-design`
  - Windows job ID: `job_20260619_213418_metasurface_sweep`
  - CLI from Task 2
- Produces:
  - Local evidence copy under `runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/`
  - Local `review.json`
  - Local `real_2x2_review.md`

- [ ] **Step 1: Create local review directories**

Run:

```bash
mkdir -p runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/results
mkdir -p runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/evidence
mkdir -p runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/tasks
mkdir -p runtime/reviews/job_20260619_213418_metasurface_sweep/approval
```

Expected: directories exist under `runtime/reviews/job_20260619_213418_metasurface_sweep/`.

- [ ] **Step 2: Copy only evidence-first files from Windows**

Run these commands from the repository root:

```bash
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/runtime/approvals/real_2x2_preflight.json runtime/reviews/job_20260619_213418_metasurface_sweep/approval/real_2x2_preflight.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/manifest.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/manifest.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/status.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/status.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/summary.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/summary.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/quality_report.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/quality_report.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/results/sweep_results.csv runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/results/sweep_results.csv
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/results/sweep_summary.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/results/sweep_summary.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/evidence/index.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/evidence/index.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/evidence/transmission_heatmap.svg runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/evidence/transmission_heatmap.svg
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/evidence/phase_heatmap.svg runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/evidence/phase_heatmap.svg
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/tasks/task_0001.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/tasks/task_0001.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/tasks/task_0002.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/tasks/task_0002.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/tasks/task_0003.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/tasks/task_0003.json
scp 32482@192.168.31.26:F:/lumerical-fdtd-auto-design/fdtd-auto-design/jobs/job_20260619_213418_metasurface_sweep/tasks/task_0004.json runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy/tasks/task_0004.json
```

Expected: each command succeeds. No `models/*.fsp` file is copied.

- [ ] **Step 3: Verify no model files were copied**

Run:

```bash
find runtime/reviews/job_20260619_213418_metasurface_sweep -name '*.fsp' -print
```

Expected: no output.

- [ ] **Step 4: Generate review artifacts**

Run:

```bash
.venv/bin/python scripts/collect_real_result_review.py \
  --job-dir runtime/reviews/job_20260619_213418_metasurface_sweep/evidence_copy \
  --preflight runtime/reviews/job_20260619_213418_metasurface_sweep/approval/real_2x2_preflight.json \
  --output-dir runtime/reviews/job_20260619_213418_metasurface_sweep
```

Expected output contains:

```text
status=pass job_id=job_20260619_213418_metasurface_sweep software_chain_verdict=pass
```

- [ ] **Step 5: Inspect review headline values**

Run:

```bash
sed -n '1,120p' runtime/reviews/job_20260619_213418_metasurface_sweep/real_2x2_review.md
```

Expected output contains:

```text
Software-chain verdict: pass
Phase span: 1.3272514058176679 rad
not a final phase library
```

- [ ] **Step 6: Confirm runtime outputs remain git-ignored**

Run:

```bash
git check-ignore runtime/reviews/job_20260619_213418_metasurface_sweep/review.json
git check-ignore runtime/reviews/job_20260619_213418_metasurface_sweep/real_2x2_review.md
```

Expected: both paths are printed, proving they are ignored.

This task has no commit because it only creates git-ignored runtime evidence.

---

### Task 4: Document Stage C2 workflow and current checkpoint

**Files:**
- Modify: `README.md`
- Modify: `SOP.md`
- Modify: `DEV_LOG.md`

**Interfaces:**
- Consumes:
  - `runtime/reviews/job_20260619_213418_metasurface_sweep/review.json`
  - `runtime/reviews/job_20260619_213418_metasurface_sweep/real_2x2_review.md`
- Produces:
  - README checkpoint updated to Stage C2 complete
  - SOP entry for repeatable real-result review
  - DEV_LOG entry with evidence and metrics

- [ ] **Step 1: Update README current status**

In `README.md`, replace the current checkpoint sentence with this text:

```markdown
- 当前 checkpoint：Stage C2 real result review。C1 已完成真实 2×2 SimulationPlan run，job `job_20260619_213418_metasurface_sweep` 为 `succeeded`，4/4 task 成功，quality `pass`。C2 已将 evidence-only 结果复制到本地 git-ignored `runtime/reviews/` 并生成 `review.json` 与 `real_2x2_review.md`。软件链结论为 `pass`；物理结论仍需人工审核，且 2×2 phase span 约 `1.3273 rad`，不足以作为最终 2π phase library。
```

- [ ] **Step 2: Add SOP for Stage C2 review**

Append this section to `SOP.md`:

```markdown
## SOP-013 - Stage C2 real result review

1. 确认 Stage C1 job 已结束，且不会在 C2 启动、resume 或扩大任何真实仿真。
2. 从 Windows job 目录只复制 evidence-first 文件：`manifest.json`、`status.json`、`summary.json`、`quality_report.json`、`results/sweep_results.csv`、`results/sweep_summary.json`、`evidence/index.json`、关键 SVG 和 task JSON。
3. 默认不复制 `models/*.fsp`；只有调试或人工明确要求时才单独复制模型文件。
4. 将 C0 preflight packet 与 C1 evidence 放到 git-ignored `runtime/reviews/<job_id>/`。
5. 运行：
   ```bash
   .venv/bin/python scripts/collect_real_result_review.py \
     --job-dir runtime/reviews/<job_id>/evidence_copy \
     --preflight runtime/reviews/<job_id>/approval/real_2x2_preflight.json \
     --output-dir runtime/reviews/<job_id>
   ```
6. 审核 `review.json` 和 `real_2x2_review.md`：软件链可以自动判定 pass/fail；物理正确性必须由人审核。
7. 若报告建议扩大 sweep 或改变物理设置，必须进入新的 plan/preflight/approval 阶段，不能由 C2 自动启动。
```

- [ ] **Step 3: Add DEV_LOG entry**

Append this section to `DEV_LOG.md`:

```markdown
## 2026-06-19 - Stage C2 real result review plan

- 目标：为 C1 真实 2×2 SimulationPlan job 增加 evidence-only 拉取、本地审计和人类可读报告流程。
- 计划：新增 `src/real_result_review.py`、`scripts/collect_real_result_review.py` 和测试；只复制 JSON/CSV/SVG/task evidence，不复制逐点 `.fsp`；生成 `review.json` 和 `real_2x2_review.md`。
- 预期结论：软件链 `pass`；物理审核仍需人工判断。C1 的 phase span 约 `1.3273 rad`，不足以作为最终 2π phase library。
- 约束：C2 不启动 FDTD、不创建 job、不 resume、不重启 RPC、不修改模板或 `.fsp`。
```

- [ ] **Step 4: Commit documentation**

Run:

```bash
git add README.md SOP.md DEV_LOG.md
git commit -m "docs: document Stage C2 real result review"
```

---

### Task 5: Final verification and report

**Files:**
- No new source file required.
- Runtime review artifacts remain under `runtime/reviews/` and must not be committed.

**Interfaces:**
- Consumes all earlier task outputs.
- Produces final Stage C2 implementation report.

- [ ] **Step 1: Run compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exit code `0`.

- [ ] **Step 2: Run full pytest**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. The expected count is previous `281` plus the new C2 tests.

- [ ] **Step 3: Scan new C2 source for forbidden real-run operations**

Run:

```bash
! rg -n "jobs/start|fdtd_simulation_plan_start|fdtd_job_start|fdtd_job_resume|runjobs|runanalysis|\\.run\\(|\\.save\\(|setnamed|addfdtd|addrect|addcircle|addmesh|addplane|addpower" src/real_result_review.py scripts/collect_real_result_review.py tests/test_real_result_review.py
```

Expected: no matches.

- [ ] **Step 4: Confirm no runtime evidence is staged**

Run:

```bash
git status --short
git ls-files runtime/reviews
```

Expected:

- `git status --short` shows only intentional source/doc changes before commit, or clean after commits.
- `git ls-files runtime/reviews` prints no files.

- [ ] **Step 5: Verify final report artifacts exist locally**

Run:

```bash
test -f runtime/reviews/job_20260619_213418_metasurface_sweep/review.json
test -f runtime/reviews/job_20260619_213418_metasurface_sweep/real_2x2_review.md
```

Expected: both commands exit `0`.

- [ ] **Step 6: Final commit if verification changed docs**

If `DEV_LOG.md` was updated with actual final verification numbers after Task 4, run:

```bash
git add DEV_LOG.md
git commit -m "docs: record Stage C2 verification"
```

- [ ] **Step 7: Final report to user**

Report these exact categories:

```text
Stage C2 final report
1. Commit hashes for each task
2. Files created and modified
3. compileall result
4. pytest result
5. Forbidden-operation scan result
6. Evidence copied from Windows
7. Confirmation no .fsp model files were copied by default
8. review.json path and real_2x2_review.md path
9. Software-chain verdict
10. Quality conclusion and task counts
11. Transmission min/max/mean
12. Phase min/max/span
13. Physical-review conclusion
14. Explicit confirmation: no FDTD start, no /jobs/start, no resume, no RPC restart, no template modification
15. git status and origin/main sync state
16. Recommended next stage
```

Recommended next stage after C2:

```text
Stage C3: production sweep design packet.

Goal: use the C2 physical review to design a larger but still bounded real sweep, likely period/ratio grid expansion with explicit task budget, acceptance criteria, and a new preflight packet. C3 still should not auto-start FDTD; it prepares the next approved real run.
```

---

## Self-Review

**Spec coverage:** This plan covers C2 evidence retrieval, pure local review generation, chain consistency checks, software/physical conclusion separation, docs/SOP updates, and final verification. It does not start or modify a real FDTD run.

**Placeholder scan:** The plan contains concrete file paths, function signatures, code blocks, commands, expected outputs, and commit messages. It avoids ambiguous implementation instructions.

**Type consistency:** The produced functions are consistently named across tests, CLI, and report generation:

- `load_real_result_evidence(job_dir: Path, preflight_path: Path | None = None) -> dict`
- `build_real_result_review(evidence: dict) -> dict`
- `render_real_result_review_markdown(review: dict) -> str`

**Risk check:** The only network operation is evidence retrieval via `scp`, copying explicit JSON/CSV/SVG/task files. No command in the plan starts, resumes, or restarts the solver.
