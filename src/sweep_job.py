"""Metasurface sweep job helpers.

This module is pure Python and safe to import on Mac. It owns sweep input
normalization, sample-grid expansion, and evidence artifacts.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_SWEEP_CONFIG = {
    "SWEEP_Y_AXIS": "period",
    "RATIO_PTS": 2,
    "PERIOD_PTS": 2,
    "BASE_HEIGHT": 700e-9,
    "BASE_PERIOD": 470e-9,
    "FDTD_PROCESSES": 1,
    "FDTD_CAPACITY": 1,
}
DEFAULT_PHASES = [1, 2, 3]
DEFAULT_RATIO_MIN = 0.2
DEFAULT_RATIO_MAX = 0.8
DEFAULT_PERIOD_MIN = 390e-9
DEFAULT_PERIOD_MAX = 540e-9


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


def _linspace(start: float, stop: float, count: int) -> list:
    if count <= 0:
        return []
    if count == 1:
        return [float(start)]
    step = (stop - start) / (count - 1)
    return [float(start + step * index) for index in range(count)]


def _float_list(value, default: list) -> list:
    if value is None:
        return list(default)
    if not isinstance(value, list) or not value:
        raise ValueError("Sweep parameter lists must be non-empty lists.")
    return [float(item) for item in value]


def normalize_sweep_input(request: dict) -> dict:
    sweep = request.get("sweep") or {}
    config = dict(DEFAULT_SWEEP_CONFIG)
    config.update(sweep.get("config") or {})
    config["RATIO_PTS"] = _as_positive_int(config.get("RATIO_PTS"), 2)
    config["PERIOD_PTS"] = _as_positive_int(config.get("PERIOD_PTS"), 2)
    config["FDTD_PROCESSES"] = _as_positive_int(config.get("FDTD_PROCESSES"), 1) or 1
    config["FDTD_CAPACITY"] = _as_positive_int(config.get("FDTD_CAPACITY"), 1) or 1
    config["SWEEP_Y_AXIS"] = str(config.get("SWEEP_Y_AXIS") or "period")
    config["RATIO_LIST"] = _float_list(
        config.get("RATIO_LIST"),
        _linspace(
            DEFAULT_RATIO_MIN,
            DEFAULT_RATIO_MAX,
            config["RATIO_PTS"],
        ),
    )
    config["PERIOD_LIST"] = _float_list(
        config.get("PERIOD_LIST"),
        _linspace(
            DEFAULT_PERIOD_MIN,
            DEFAULT_PERIOD_MAX,
            config["PERIOD_PTS"],
        ),
    )
    config["BASE_HEIGHT"] = float(config.get("BASE_HEIGHT", 700e-9))
    config["BASE_PERIOD"] = float(config.get("BASE_PERIOD", 470e-9))
    if config["SWEEP_Y_AXIS"] == "height":
        config["HEIGHT_LIST"] = _float_list(
            config.get("HEIGHT_LIST"),
            [config["BASE_HEIGHT"]],
        )

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
        "template": str(
            sweep.get("template")
            or "templates/metasurface/base_model.fsp"
        ),
        "include_models": bool(sweep.get("include_models", False)),
    }


def build_sweep_tasks(request: dict) -> list:
    sweep_input = normalize_sweep_input(request)
    config = sweep_input["config"]
    tasks = []

    if config["SWEEP_Y_AXIS"] == "period":
        for period in config["PERIOD_LIST"]:
            for ratio in config["RATIO_LIST"]:
                tasks.append(
                    {
                        "operation": "metasurface-sample",
                        "input": {
                            "sample_index": len(tasks),
                            "ratio": ratio,
                            "height": config["BASE_HEIGHT"],
                            "period": period,
                        },
                    }
                )
    else:
        for height in config["HEIGHT_LIST"]:
            for ratio in config["RATIO_LIST"]:
                tasks.append(
                    {
                        "operation": "metasurface-sample",
                        "input": {
                            "sample_index": len(tasks),
                            "ratio": ratio,
                            "height": height,
                            "period": config["BASE_PERIOD"],
                        },
                    }
                )

    return tasks


def _sample_counts(config: dict) -> dict:
    ratio_pts = _as_positive_int(config.get("RATIO_PTS"), 2)
    period_pts = _as_positive_int(config.get("PERIOD_PTS"), 2)
    total = ratio_pts * period_pts
    return {"ratio_pts": ratio_pts, "period_pts": period_pts, "total": total}


def run_mock_sample(task: dict, job_dir: Path) -> dict:
    sample = task["input"]
    result_path = Path(job_dir) / "results" / f"{task['task_id']}.json"
    result = {
        "task_id": task["task_id"],
        **sample,
        "transmission": 0.8,
        "phase_rad": 0.0,
        "synthetic": True,
    }
    _write_json(result_path, result)
    return {"result_file": str(result_path), **result}


def run_mock_sweep(task: dict, job_dir: Path) -> dict:
    """Compatibility shim while JobStore transitions to sample operations."""
    return run_mock_sample(task, job_dir)


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
