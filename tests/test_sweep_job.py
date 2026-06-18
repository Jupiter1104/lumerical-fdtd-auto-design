import json
from pathlib import Path

from src.sweep_job import (
    build_sweep_tasks,
    normalize_sweep_input,
    run_mock_sample,
    write_job_artifacts,
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_normalize_sweep_input_expands_point_count_shorthand():
    normalized = normalize_sweep_input(
        {
            "sweep": {
                "config": {
                    "RATIO_PTS": 2,
                    "PERIOD_PTS": 2,
                    "BASE_HEIGHT": 700e-9,
                }
            }
        }
    )

    assert normalized["config"]["RATIO_LIST"] == [0.2, 0.8]
    assert normalized["config"]["PERIOD_LIST"] == [390e-9, 540e-9]
    assert normalized["config"]["BASE_HEIGHT"] == 700e-9


def test_build_sweep_tasks_expands_stable_ratio_period_grid():
    tasks = build_sweep_tasks(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "config": {
                    "SWEEP_Y_AXIS": "period",
                    "RATIO_LIST": [0.2, 0.8],
                    "PERIOD_LIST": [390e-9, 540e-9],
                    "BASE_HEIGHT": 700e-9,
                }
            },
        }
    )

    assert [task["input"] for task in tasks] == [
        {
            "sample_index": 0,
            "ratio": 0.2,
            "height": 700e-9,
            "period": 390e-9,
        },
        {
            "sample_index": 1,
            "ratio": 0.8,
            "height": 700e-9,
            "period": 390e-9,
        },
        {
            "sample_index": 2,
            "ratio": 0.2,
            "height": 700e-9,
            "period": 540e-9,
        },
        {
            "sample_index": 3,
            "ratio": 0.8,
            "height": 700e-9,
            "period": 540e-9,
        },
    ]
    assert {task["operation"] for task in tasks} == {"metasurface-sample"}


def test_build_sweep_tasks_expands_height_grid():
    tasks = build_sweep_tasks(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "config": {
                    "SWEEP_Y_AXIS": "height",
                    "RATIO_LIST": [0.5],
                    "HEIGHT_LIST": [600e-9, 800e-9],
                    "BASE_PERIOD": 470e-9,
                }
            },
        }
    )

    assert [task["input"] for task in tasks] == [
        {
            "sample_index": 0,
            "ratio": 0.5,
            "height": 600e-9,
            "period": 470e-9,
        },
        {
            "sample_index": 1,
            "ratio": 0.5,
            "height": 800e-9,
            "period": 470e-9,
        },
    ]


def test_run_mock_sample_writes_one_result_file(tmp_path):
    task = {
        "task_id": "task_0001",
        "mode": "mock",
        "operation": "metasurface-sample",
        "input": {
            "sample_index": 0,
            "ratio": 0.2,
            "height": 700e-9,
            "period": 390e-9,
        },
    }

    output = run_mock_sample(task, tmp_path)

    result = read_json(Path(output["result_file"]))
    assert result["task_id"] == "task_0001"
    assert result["synthetic"] is True
    assert result["transmission"] == 0.8


def test_write_job_artifacts_aggregates_results_and_svg(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    samples = [
        {
            "task_id": "task_0001",
            "sample_index": 0,
            "ratio": 0.2,
            "height": 700e-9,
            "period": 390e-9,
            "transmission": 0.7,
            "phase_rad": 0.1,
        },
        {
            "task_id": "task_0002",
            "sample_index": 1,
            "ratio": 0.8,
            "height": 700e-9,
            "period": 390e-9,
            "transmission": 0.8,
            "phase_rad": 1.2,
        },
    ]
    for sample in samples:
        (results_dir / f"{sample['task_id']}.json").write_text(
            json.dumps(sample),
            encoding="utf-8",
        )

    outputs = write_job_artifacts(
        tmp_path,
        job_id="job_test",
        expected_count=2,
        include_models=False,
    )

    assert Path(outputs["csv_file"]).exists()
    assert Path(outputs["quality_report"]["path"]).exists()
    assert Path(outputs["evidence"]["path"]).exists()
    assert (tmp_path / "evidence" / "transmission_heatmap.svg").exists()
    assert (tmp_path / "evidence" / "phase_heatmap.svg").exists()
    assert outputs["quality_report"]["conclusion"] == "pass"


def test_write_job_artifacts_warns_when_samples_are_missing(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    sample = {
        "task_id": "task_0001",
        "sample_index": 0,
        "ratio": 0.2,
        "height": 700e-9,
        "period": 390e-9,
        "transmission": 0.7,
        "phase_rad": 0.1,
    }
    (results_dir / "task_0001.json").write_text(
        json.dumps(sample),
        encoding="utf-8",
    )

    outputs = write_job_artifacts(
        tmp_path,
        job_id="job_test",
        expected_count=2,
        include_models=False,
    )

    report = read_json(Path(outputs["quality_report"]["path"]))
    assert report["conclusion"] == "warning"
    assert report["requires_human_review"] is True
    assert report["result_completeness"]["missing_count"] == 1


def test_write_job_artifacts_fails_when_no_valid_samples(tmp_path):
    (tmp_path / "results").mkdir()

    outputs = write_job_artifacts(
        tmp_path,
        job_id="job_test",
        expected_count=2,
        include_models=False,
    )

    report = read_json(Path(outputs["quality_report"]["path"]))
    assert report["conclusion"] == "fail"
    assert report["requires_human_review"] is True


def test_write_job_artifacts_warns_for_out_of_range_transmission(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    sample = {
        "task_id": "task_0001",
        "sample_index": 0,
        "ratio": 0.2,
        "height": 700e-9,
        "period": 390e-9,
        "transmission": 1.2,
        "phase_rad": 0.1,
    }
    (results_dir / "task_0001.json").write_text(
        json.dumps(sample),
        encoding="utf-8",
    )

    outputs = write_job_artifacts(
        tmp_path,
        job_id="job_test",
        expected_count=1,
        include_models=False,
    )

    report = read_json(Path(outputs["quality_report"]["path"]))
    assert report["conclusion"] == "warning"
    assert any(
        check["name"] == "transmission_range"
        for check in report["physical_checks"]
    )
