"""Metasurface sweep job helpers.

This module is pure Python and safe to import on Mac. It owns sweep input
normalization, sample-grid expansion, and evidence artifacts.
"""

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape


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


def _read_sample_results(job_dir: Path) -> list:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((Path(job_dir) / "results").glob("task_*.json"))
    ]


def _write_csv(path: Path, samples: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "task_id",
        "sample_index",
        "ratio",
        "height",
        "period",
        "transmission",
        "phase_rad",
    ]
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for sample in samples:
            writer.writerow({key: sample.get(key) for key in fields})


def _cell_color(value: float, minimum: float, maximum: float) -> str:
    if maximum <= minimum:
        ratio = 0.5
    else:
        ratio = (value - minimum) / (maximum - minimum)
    ratio = max(0.0, min(1.0, ratio))
    red = int(255 * ratio)
    blue = int(255 * (1.0 - ratio))
    green = 96
    return f"#{red:02x}{green:02x}{blue:02x}"


def _write_heatmap_svg(path: Path, samples: list, value_key: str, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cell = 48
    margin_left = 96
    margin_top = 56
    ratios = sorted({float(sample["ratio"]) for sample in samples})
    periods = sorted({float(sample["period"]) for sample in samples})
    heights = sorted({float(sample["height"]) for sample in samples})
    y_key = "height" if len(heights) > 1 and len(periods) == 1 else "period"
    y_values = heights if y_key == "height" else periods
    values = [float(sample[value_key]) for sample in samples]
    minimum = min(values)
    maximum = max(values)
    by_point = {
        (float(sample["ratio"]), float(sample[y_key])): float(sample[value_key])
        for sample in samples
    }
    width = margin_left + max(1, len(ratios)) * cell + 24
    height = margin_top + max(1, len(y_values)) * cell + 40
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="16" y="28" font-size="16" font-family="sans-serif">'
        f"{escape(title)}</text>",
    ]
    for col, ratio in enumerate(ratios):
        x = margin_left + col * cell + cell / 2
        parts.append(
            f'<text x="{x}" y="48" text-anchor="middle" '
            f'font-size="10" font-family="monospace">{ratio:.3g}</text>'
        )
    for row, y_value in enumerate(y_values):
        y = margin_top + row * cell
        parts.append(
            f'<text x="88" y="{y + 28}" text-anchor="end" '
            f'font-size="10" font-family="monospace">{y_value:.3g}</text>'
        )
        for col, ratio in enumerate(ratios):
            x = margin_left + col * cell
            value = by_point.get((ratio, y_value))
            if value is None:
                fill = "#eeeeee"
                label = "n/a"
            else:
                fill = _cell_color(value, minimum, maximum)
                label = f"{value:.3g}"
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                f'fill="{fill}" stroke="#333" stroke-width="0.5"/>'
            )
            parts.append(
                f'<text x="{x + cell / 2}" y="{y + 28}" text-anchor="middle" '
                f'font-size="10" font-family="monospace">{escape(label)}</text>'
            )
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _native_quality(samples: list, expected_count: int) -> tuple:
    checks = []
    valid_count = len(samples)
    missing_count = max(expected_count - valid_count, 0)
    if not samples:
        checks.append(
            {
                "name": "valid_samples",
                "status": "fail",
                "message": "No valid sweep samples were produced.",
            }
        )
    elif missing_count:
        checks.append(
            {
                "name": "missing_samples",
                "status": "warning",
                "message": f"{missing_count} sweep samples are missing.",
            }
        )

    invalid_transmission = [
        sample
        for sample in samples
        if (
            not math.isfinite(float(sample["transmission"]))
            or float(sample["transmission"]) < -0.05
            or float(sample["transmission"]) > 1.05
        )
    ]
    if invalid_transmission:
        checks.append(
            {
                "name": "transmission_range",
                "status": "warning",
                "message": (
                    f"{len(invalid_transmission)} samples have transmission "
                    "outside the expected passive range."
                ),
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


def write_job_artifacts(
    job_dir: Path,
    *,
    job_id: str,
    expected_count: int,
    include_models: bool,
) -> dict:
    job_dir = Path(job_dir)
    samples = _read_sample_results(job_dir)
    generated_at = utc_now()
    conclusion, checks = _native_quality(samples, expected_count)

    csv_path = job_dir / "results" / "sweep_results.csv"
    summary_path = job_dir / "results" / "sweep_summary.json"
    quality_path = job_dir / "quality_report.json"
    evidence_path = job_dir / "evidence" / "index.json"
    transmission_svg = job_dir / "evidence" / "transmission_heatmap.svg"
    phase_svg = job_dir / "evidence" / "phase_heatmap.svg"

    _write_csv(csv_path, samples)
    if samples:
        _write_heatmap_svg(
            transmission_svg,
            samples,
            "transmission",
            "Transmission heatmap",
        )
        _write_heatmap_svg(phase_svg, samples, "phase_rad", "Phase heatmap")

    result_files = [
        str((job_dir / "results" / f"{sample['task_id']}.json").resolve())
        for sample in samples
    ]
    figure_files = []
    if transmission_svg.exists():
        figure_files.append(str(transmission_svg.resolve()))
    if phase_svg.exists():
        figure_files.append(str(phase_svg.resolve()))
    model_files = (
        [str(path.resolve()) for path in sorted((job_dir / "models").glob("*.fsp"))]
        if include_models
        else []
    )
    sweep_summary = {
        "job_id": job_id,
        "generated_at": generated_at,
        "valid_count": len(samples),
        "missing_count": max(expected_count - len(samples), 0),
        "total_count": expected_count,
        "result_files": result_files,
        "figure_files": figure_files,
        "model_files": model_files,
    }
    quality_report = {
        "job_id": job_id,
        "generated_at": generated_at,
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
        "generated_at": generated_at,
        "summary_files": [
            "summary.json",
            "quality_report.json",
            "results/sweep_summary.json",
            "results/sweep_results.csv",
        ],
        "result_files": result_files,
        "figure_files": figure_files,
        "model_files": model_files,
        "download_policy": {
            "include_models": include_models,
            "default_payload": "evidence-only",
        },
    }
    _write_json(summary_path, sweep_summary)
    _write_json(quality_path, quality_report)
    _write_json(evidence_path, evidence_index)
    return {
        "csv_file": str(csv_path),
        "sweep_summary": {"path": str(summary_path)},
        "quality_report": {
            "path": str(quality_path),
            "conclusion": conclusion,
            "requires_human_review": True,
        },
        "evidence": {
            "path": str(evidence_path),
            "download_policy": evidence_index["download_policy"],
        },
    }


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
