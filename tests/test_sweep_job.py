import json
from pathlib import Path

from src.sweep_job import (
    build_sweep_tasks,
    run_deployed_sweep,
    run_mock_sweep,
    write_sweep_artifacts,
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_sweep_tasks_uses_safe_defaults():
    request = {"job_type": "metasurface-sweep", "mode": "mock"}

    tasks = build_sweep_tasks(request)

    assert tasks == [
        {
            "operation": "metasurface-sweep",
            "input": {
                "config": {
                    "SWEEP_Y_AXIS": "period",
                    "RATIO_PTS": 2,
                    "PERIOD_PTS": 2,
                    "FDTD_PROCESSES": 1,
                    "FDTD_CAPACITY": 1,
                },
                "phases": [1, 2, 3],
                "hide": True,
                "template": "base_model.fsp",
                "include_models": False,
            },
        }
    ]


def test_mock_sweep_writes_summary_quality_and_evidence(tmp_path):
    task = build_sweep_tasks(
        {
            "job_type": "metasurface-sweep",
            "mode": "mock",
            "sweep": {
                "config": {"RATIO_PTS": 2, "PERIOD_PTS": 2},
                "phases": [1, 2, 3, 4],
            },
        }
    )[0]
    task["task_id"] = "task_0001"
    task["mode"] = "mock"

    outputs = run_mock_sweep(task, tmp_path)

    quality_path = tmp_path / "quality_report.json"
    sweep_summary_path = tmp_path / "results" / "sweep_summary.json"
    evidence_path = tmp_path / "evidence" / "index.json"

    assert quality_path.exists()
    assert sweep_summary_path.exists()
    assert evidence_path.exists()
    assert outputs["quality_report"]["path"] == str(quality_path)
    assert outputs["evidence"]["path"] == str(evidence_path)

    quality = read_json(quality_path)
    sweep_summary = read_json(sweep_summary_path)
    evidence = read_json(evidence_path)

    assert sweep_summary["valid_count"] == 4
    assert sweep_summary["missing_count"] == 0
    assert quality["conclusion"] == "pass"
    assert quality["requires_human_review"] is True
    assert evidence["download_policy"]["include_models"] is False


def test_quality_report_fails_when_no_valid_results(tmp_path):
    task = build_sweep_tasks(
        {
            "job_type": "metasurface-sweep",
            "mode": "mock",
            "sweep": {"config": {"RATIO_PTS": 0, "PERIOD_PTS": 2}},
        }
    )[0]
    task["task_id"] = "task_0001"
    task["mode"] = "mock"

    outputs = write_sweep_artifacts(
        job_dir=tmp_path,
        task=task,
        run_result={
            "solver_status": "done",
            "message": "0/0 valid, 0 missing",
            "valid_count": 0,
            "missing_count": 0,
            "total_count": 0,
            "phases": [1, 2, 3],
            "result_files": [],
            "figure_files": [],
            "model_files": [],
            "remote_task_id": None,
        },
    )

    quality = read_json(Path(outputs["quality_report"]["path"]))

    assert quality["conclusion"] == "fail"
    assert quality["solver_status"]["state"] == "done"
    assert "No valid sweep samples" in quality["physical_checks"][0]["message"]


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        if url.endswith("/health"):
            return FakeResponse(
                {"ok": True, "fdtd_connected": True, "matlab_connected": True}
            )
        if url.endswith("/sweep/config"):
            return FakeResponse({"ok": True})
        if url.endswith("/sweep/run"):
            return FakeResponse({"ok": True, "task_id": "sweep_fake"})
        if url.endswith("/sweep/status"):
            return FakeResponse(
                {
                    "ok": True,
                    "task": {
                        "status": "done",
                        "message": "4/4 valid, 0 missing",
                    },
                }
            )
        if url.endswith("/results"):
            return FakeResponse(
                {
                    "ok": True,
                    "files": {
                        "results": ["s_params.csv"],
                        "figures": ["heatmap.png"],
                        "models": ["sample_001.fsp"],
                    },
                }
            )
        raise AssertionError(url)


def test_run_deployed_sweep_bridges_5003_and_writes_evidence(tmp_path):
    task = build_sweep_tasks({"job_type": "metasurface-sweep", "mode": "real"})[0]
    task["task_id"] = "task_0001"
    task["mode"] = "real"
    session = FakeSession()

    outputs = run_deployed_sweep(
        task,
        tmp_path,
        base_url="http://127.0.0.1:5003",
        poll_interval=0,
        timeout_seconds=1,
        session=session,
    )

    quality = read_json(Path(outputs["quality_report"]["path"]))
    evidence = read_json(Path(outputs["evidence"]["path"]))

    assert outputs["remote_task_id"] == "sweep_fake"
    assert quality["conclusion"] == "pass"
    assert evidence["result_files"] == ["results/s_params.csv"]
    assert evidence["figure_files"] == ["figures/heatmap.png"]
    assert evidence["model_files"] == []
