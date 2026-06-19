"""Tests for Stage C2 real result review module."""

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
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
        {
            "job_id": JOB_ID,
            "state": "succeeded",
            "message": "Job succeeded.",
        },
    )
    write_json(
        job_dir / "summary.json",
        {
            "job_id": JOB_ID,
            "task_counts": {
                "total": 4,
                "pending": 0,
                "running": 0,
                "succeeded": 4,
                "failed": 0,
            },
            "results": [],
        },
    )
    write_json(
        job_dir / "quality_report.json",
        {
            "job_id": JOB_ID,
            "result_completeness": {
                "valid_count": 4,
                "missing_count": 0,
                "total_count": 4,
            },
            "physical_checks": [
                {"name": "transmission_range", "status": "pass"}
            ],
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
            "download_policy": {
                "include_models": False,
                "default_payload": "evidence-only",
            },
        },
    )
    (job_dir / "evidence" / "transmission_heatmap.svg").write_text(
        "<svg />\n", encoding="utf-8"
    )
    (job_dir / "evidence" / "phase_heatmap.svg").write_text(
        "<svg />\n", encoding="utf-8"
    )
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
            "compiled_request": {
                "mode": "real",
                "sweep": {"include_models": False},
            },
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
    assert (
        review["physical_review"]["conclusion"]
        == "human_review_required"
    )
    assert review["task_counts"] == {
        "total": 4,
        "succeeded": 4,
        "failed": 0,
    }
    assert (
        review["chain_consistency"]["template_sha256"]["status"]
        == "pass"
    )
    assert (
        review["chain_consistency"]["plan_fingerprint"]["status"]
        == "pass"
    )
    assert (
        review["chain_consistency"]["model_files_excluded"]["status"]
        == "pass"
    )
    assert review["metrics"]["transmission"]["min"] == 0.7300105242892926
    assert review["metrics"]["transmission"]["max"] == 0.9679605819741104
    assert (
        review["metrics"]["transmission"]["mean"]
        == 0.9001426292124059
    )
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
    review = build_real_result_review(
        load_real_result_evidence(job_dir, preflight_path)
    )
    markdown = render_real_result_review_markdown(review)

    assert "# Real 2x2 SimulationPlan Result Review" in markdown
    assert "Software-chain verdict: pass" in markdown
    assert "Phase span: 1.3272514058176679 rad" in markdown
    assert "not a final phase library" in markdown


def test_collect_real_result_review_cli_writes_json_and_markdown(tmp_path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent
    job_dir, preflight_path = write_c1_fixture(tmp_path)
    output_dir = tmp_path / "review"

    result = subprocess.run(
        [
            sys.executable,
            str(
                root
                / "scripts"
                / "collect_real_result_review.py"
            ),
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
    review = json.loads(
        (output_dir / "review.json").read_text(encoding="utf-8")
    )
    markdown = (output_dir / "real_2x2_review.md").read_text(
        encoding="utf-8"
    )
    assert review["software_chain_verdict"] == "pass"
    assert "status=pass" in result.stdout
    assert "Software-chain verdict: pass" in markdown
