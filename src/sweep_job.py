"""Metasurface sweep job helpers.

This module is pure Python and safe to import on Mac. Real solver work is
delegated to the already-deployed sweep RPC service on Windows port 5003.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests


DEFAULT_SWEEP_CONFIG = {
    "SWEEP_Y_AXIS": "period",
    "RATIO_PTS": 2,
    "PERIOD_PTS": 2,
    "FDTD_PROCESSES": 1,
    "FDTD_CAPACITY": 1,
}
DEFAULT_PHASES = [1, 2, 3]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _as_positive_int(value, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(number, 0)


def normalize_sweep_input(request: dict) -> dict:
    sweep = request.get("sweep") or {}
    config = dict(DEFAULT_SWEEP_CONFIG)
    config.update(sweep.get("config") or {})
    config["RATIO_PTS"] = _as_positive_int(config.get("RATIO_PTS"), 2)
    config["PERIOD_PTS"] = _as_positive_int(config.get("PERIOD_PTS"), 2)
    config["FDTD_PROCESSES"] = _as_positive_int(config.get("FDTD_PROCESSES"), 1) or 1
    config["FDTD_CAPACITY"] = _as_positive_int(config.get("FDTD_CAPACITY"), 1) or 1
    config["SWEEP_Y_AXIS"] = str(config.get("SWEEP_Y_AXIS") or "period")

    phases = sweep.get("phases", DEFAULT_PHASES)
    if not isinstance(phases, list) or not phases:
        phases = list(DEFAULT_PHASES)
    phases = [int(phase) for phase in phases if int(phase) in {1, 2, 3, 4}]
    if not phases:
        phases = list(DEFAULT_PHASES)

    return {
        "config": config,
        "phases": phases,
        "hide": bool(sweep.get("hide", True)),
        "template": str(sweep.get("template") or "base_model.fsp"),
        "include_models": bool(sweep.get("include_models", False)),
    }


def build_sweep_tasks(request: dict) -> list:
    return [
        {
            "operation": "metasurface-sweep",
            "input": normalize_sweep_input(request),
        }
    ]


def _sample_counts(config: dict) -> dict:
    ratio_pts = _as_positive_int(config.get("RATIO_PTS"), 2)
    period_pts = _as_positive_int(config.get("PERIOD_PTS"), 2)
    total = ratio_pts * period_pts
    return {"ratio_pts": ratio_pts, "period_pts": period_pts, "total": total}


def run_mock_sweep(task: dict, job_dir: Path) -> dict:
    sweep_input = task.get("input", {})
    counts = _sample_counts(sweep_input.get("config", {}))
    total = counts["total"]
    run_result = {
        "solver_status": "done",
        "message": f"{total}/{total} valid, 0 missing",
        "valid_count": total,
        "missing_count": 0,
        "total_count": total,
        "phases": sweep_input.get("phases", DEFAULT_PHASES),
        "result_files": ["results/sweep_summary.json"],
        "figure_files": ["figures/mock_transmission_heatmap.png"]
        if 4 in sweep_input.get("phases", [])
        else [],
        "model_files": [],
        "remote_task_id": None,
    }
    return write_sweep_artifacts(job_dir, task, run_result)


def _quality_conclusion(run_result: dict) -> tuple:
    checks = []
    valid_count = int(run_result.get("valid_count") or 0)
    missing_count = int(run_result.get("missing_count") or 0)
    solver_state = run_result.get("solver_status") or "unknown"

    if solver_state not in {"done", "succeeded"}:
        checks.append(
            {
                "name": "solver_completed",
                "status": "fail",
                "message": f"Solver status is {solver_state}.",
            }
        )
    if valid_count <= 0:
        checks.append(
            {
                "name": "valid_samples",
                "status": "fail",
                "message": "No valid sweep samples were produced.",
            }
        )
    if missing_count > 0:
        checks.append(
            {
                "name": "missing_samples",
                "status": "warning",
                "message": f"{missing_count} sweep samples are missing.",
            }
        )
    if not checks:
        checks.append(
            {
                "name": "basic_completeness",
                "status": "pass",
                "message": "All requested sweep samples are present.",
            }
        )

    statuses = {check["status"] for check in checks}
    if "fail" in statuses:
        return "fail", checks
    if "warning" in statuses:
        return "warning", checks
    return "pass", checks


def write_sweep_artifacts(job_dir: Path, task: dict, run_result: dict) -> dict:
    job_dir = Path(job_dir)
    job_id = job_dir.name
    sweep_input = task.get("input", {})
    generated_at = utc_now()
    conclusion, checks = _quality_conclusion(run_result)

    sweep_summary = {
        "job_id": job_id,
        "task_id": task.get("task_id"),
        "generated_at": generated_at,
        "mode": task.get("mode"),
        "config": sweep_input.get("config", {}),
        "phases": run_result.get("phases", sweep_input.get("phases", DEFAULT_PHASES)),
        "remote_task_id": run_result.get("remote_task_id"),
        "solver_status": run_result.get("solver_status"),
        "message": run_result.get("message"),
        "valid_count": int(run_result.get("valid_count") or 0),
        "missing_count": int(run_result.get("missing_count") or 0),
        "total_count": int(run_result.get("total_count") or 0),
        "result_files": run_result.get("result_files", []),
        "figure_files": run_result.get("figure_files", []),
        "model_files": run_result.get("model_files", []),
    }
    quality_report = {
        "job_id": job_id,
        "task_id": task.get("task_id"),
        "generated_at": generated_at,
        "solver_status": {
            "state": run_result.get("solver_status"),
            "message": run_result.get("message"),
            "remote_task_id": run_result.get("remote_task_id"),
        },
        "result_completeness": {
            "valid_count": sweep_summary["valid_count"],
            "missing_count": sweep_summary["missing_count"],
            "total_count": sweep_summary["total_count"],
        },
        "physical_checks": checks,
        "conclusion": conclusion,
        "requires_human_review": True,
    }
    evidence_index = {
        "job_id": job_id,
        "task_id": task.get("task_id"),
        "generated_at": generated_at,
        "summary_files": [
            "summary.json",
            "quality_report.json",
            "results/sweep_summary.json",
        ],
        "result_files": run_result.get("result_files", []),
        "figure_files": run_result.get("figure_files", []),
        "model_files": run_result.get("model_files", [])
        if sweep_input.get("include_models", False)
        else [],
        "download_policy": {
            "include_models": bool(sweep_input.get("include_models", False)),
            "default_payload": "evidence-only",
        },
    }

    sweep_summary_path = job_dir / "results" / "sweep_summary.json"
    quality_path = job_dir / "quality_report.json"
    evidence_path = job_dir / "evidence" / "index.json"
    _write_json(sweep_summary_path, sweep_summary)
    _write_json(quality_path, quality_report)
    _write_json(evidence_path, evidence_index)

    return {
        "sweep_summary": {"path": str(sweep_summary_path)},
        "quality_report": {
            "path": str(quality_path),
            "conclusion": quality_report["conclusion"],
            "requires_human_review": True,
        },
        "evidence": {
            "path": str(evidence_path),
            "download_policy": evidence_index["download_policy"],
        },
        "remote_task_id": run_result.get("remote_task_id"),
    }


def _parse_counts(message: str) -> dict:
    match = re.search(r"(\d+)\s*/\s*(\d+)\s+valid.*?(\d+)\s+missing", message or "")
    if not match:
        return {"valid_count": 0, "total_count": 0, "missing_count": 0}
    return {
        "valid_count": int(match.group(1)),
        "total_count": int(match.group(2)),
        "missing_count": int(match.group(3)),
    }


def _request_json(session, method: str, url: str, **kwargs) -> dict:
    response = session.request(method, url, **kwargs)
    payload = response.json()
    if response.status_code >= 400 or payload.get("ok") is False:
        raise RuntimeError(f"{method} {url} failed: {payload}")
    return payload


def run_deployed_sweep(
    task: dict,
    job_dir: Path,
    base_url: str,
    poll_interval: float = 10.0,
    timeout_seconds: float = 3600.0,
    session: Optional[requests.Session] = None,
) -> dict:
    http = session or requests.Session()
    base = base_url.rstrip("/")
    sweep_input = task.get("input", {})

    health = _request_json(http, "GET", f"{base}/health", timeout=30)
    if not (health.get("fdtd_connected") and health.get("matlab_connected")):
        _request_json(
            http,
            "POST",
            f"{base}/session/start",
            json={"hide": bool(sweep_input.get("hide", True))},
            timeout=120,
        )

    _request_json(
        http,
        "POST",
        f"{base}/sweep/config",
        json=sweep_input.get("config", {}),
        timeout=60,
    )
    started = _request_json(
        http,
        "POST",
        f"{base}/sweep/run",
        json={"phases": sweep_input.get("phases", DEFAULT_PHASES)},
        timeout=120,
    )
    remote_task_id = started.get("task_id")
    deadline = time.time() + timeout_seconds
    final_task = {}

    while time.time() < deadline:
        status = _request_json(
            http,
            "GET",
            f"{base}/sweep/status",
            params={"task_id": remote_task_id},
            timeout=60,
        )
        final_task = status.get("task", {})
        if final_task.get("status") in {"done", "error"}:
            break
        time.sleep(poll_interval)
    else:
        raise RuntimeError(f"Sweep task {remote_task_id} timed out.")

    result_listing = _request_json(http, "GET", f"{base}/results", timeout=60)
    files = result_listing.get("files", {})
    message = final_task.get("message", "")
    counts = _parse_counts(message)
    run_result = {
        "solver_status": final_task.get("status", "unknown"),
        "message": message,
        "remote_task_id": remote_task_id,
        "phases": sweep_input.get("phases", DEFAULT_PHASES),
        "result_files": [f"results/{name}" for name in files.get("results", [])],
        "figure_files": [f"figures/{name}" for name in files.get("figures", [])],
        "model_files": [f"models/{name}" for name in files.get("models", [])],
        **counts,
    }
    outputs = write_sweep_artifacts(job_dir, task, run_result)
    if run_result["solver_status"] == "error":
        raise RuntimeError(message or f"Sweep task {remote_task_id} failed.")
    return outputs
