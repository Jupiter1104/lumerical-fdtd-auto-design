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
        for key in (
            "sample_index", "ratio", "height", "period",
            "transmission", "phase_rad",
        ):
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


def load_real_result_evidence(
    job_dir: Path, preflight_path: Path | None = None
) -> dict:
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

    preflight = (
        _read_json(Path(preflight_path)) if preflight_path else None
    )
    return {
        "job_dir": str(job_dir),
        "preflight_path": str(preflight_path) if preflight_path else None,
        "manifest": _read_json(paths["manifest"]),
        "status": _read_json(paths["status"]),
        "summary": _read_json(paths["summary"]),
        "quality_report": _read_json(paths["quality_report"]),
        "sweep_summary": _read_json(paths["sweep_summary"]),
        "sweep_results": _float_rows(
            _read_csv(paths["sweep_results_csv"])
        ),
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
        (
            "Job state is succeeded."
            if status_doc.get("state") == "succeeded"
            else "Job state is not succeeded."
        ),
        {"actual": status_doc.get("state")},
    )
    checks["task_counts"] = _check(
        "task_counts",
        (
            "pass"
            if task_counts.get("total") == 4
            and task_counts.get("succeeded") == 4
            and task_counts.get("failed") == 0
            else "fail"
        ),
        "All four C1 tasks succeeded.",
        {"actual": task_counts},
    )
    completeness = quality.get("result_completeness") or {}
    checks["quality_report"] = _check(
        "quality_report",
        (
            "pass"
            if quality.get("conclusion") == "pass"
            and completeness.get("valid_count") == 4
            and completeness.get("missing_count") == 0
            else "fail"
        ),
        "Quality report passed with four valid samples.",
        {
            "conclusion": quality.get("conclusion"),
            "result_completeness": completeness,
        },
    )
    checks["template_sha256"] = _check(
        "template_sha256",
        (
            "pass"
            if template_sha == EXPECTED_TEMPLATE_SHA256
            and preflight_template.get("sha256")
            == EXPECTED_TEMPLATE_SHA256
            else "fail"
        ),
        "Template SHA matches the approved Stage C0 packet and C1 manifest.",
        {
            "manifest": template_sha,
            "preflight": preflight_template.get("sha256"),
        },
    )
    checks["contract_fingerprint"] = _check(
        "contract_fingerprint",
        (
            "pass"
            if preflight_template.get("contract_fingerprint")
            == EXPECTED_CONTRACT_FINGERPRINT
            else "fail"
        ),
        "Stage B1 contract fingerprint matches the approved packet.",
        {
            "preflight": preflight_template.get("contract_fingerprint")
        },
    )
    checks["plan_fingerprint"] = _check(
        "plan_fingerprint",
        (
            "pass"
            if preflight.get("plan_fingerprint")
            == EXPECTED_PLAN_FINGERPRINT
            else "fail"
        ),
        "SimulationPlan fingerprint matches the approved C0 packet.",
        {"preflight": preflight.get("plan_fingerprint")},
    )
    download_policy = evidence_index.get("download_policy") or {}
    checks["model_files_excluded"] = _check(
        "model_files_excluded",
        (
            "pass"
            if not evidence_index.get("model_files")
            and download_policy.get("include_models") is False
            else "fail"
        ),
        "Default evidence payload excludes per-point .fsp models.",
        {
            "model_files": evidence_index.get("model_files"),
            "download_policy": download_policy,
        },
    )
    return checks


def build_real_result_review(evidence: dict) -> dict:
    rows = evidence.get("sweep_results") or []
    transmissions = [
        float(row["transmission"])
        for row in rows
        if row.get("transmission") is not None
    ]
    phases = [
        float(row["phase_rad"])
        for row in rows
        if row.get("phase_rad") is not None
    ]
    phase_stat = _stat(phases)
    if phase_stat["span"] is not None:
        phase_stat["span_degrees"] = round(
            phase_stat["span"] * 180.0 / math.pi, 3
        )

    checks = _chain_consistency(evidence)
    missing_files = list(evidence.get("missing_files") or [])
    ok = not missing_files and all(
        check["status"] == "pass" for check in checks.values()
    )
    summary = evidence.get("summary") or {}
    task_counts = summary.get("task_counts") or {}
    review = {
        "ok": ok,
        "job_id": summary.get("job_id")
        or (evidence.get("status") or {}).get("job_id"),
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
                "Phase coverage is far below 2π, so this is "
                "not a final phase library."
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
        (
            f"- Task counts: {review['task_counts']['succeeded']} succeeded"
            f" / {review['task_counts']['failed']} failed"
            f" / {review['task_counts']['total']} total"
        ),
        "",
        "## Chain consistency",
        "",
    ]
    for name, check in checks.items():
        lines.append(
            f"- {name}: {check['status']} — {check['message']}"
        )
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            (
                f"- Transmission min/max/mean: {transmission['min']}"
                f" / {transmission['max']} / {transmission['mean']}"
            ),
            (
                f"- Phase span: {phase['span']} rad"
                f" ({phase.get('span_degrees')} degrees)"
            ),
            "",
            "## Physical interpretation",
            "",
            (
                "This 2×2 run is a real solver validation of the "
                "automation chain, not a final phase library. The phase "
                "span is far below 2π, so a larger approved sweep is "
                "required before design use."
            ),
            "",
        ]
    )
    return "\n".join(lines)
