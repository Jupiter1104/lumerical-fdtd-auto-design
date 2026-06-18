import json
from pathlib import Path

import pytest

from src.job_store import JobError, JobStore


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_plan_creates_persistent_job_layout(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    request = {
        "mode": "mock",
        "job_type": "geometry-smoke",
        "tasks": [{"operation": "geometry-smoke", "input": {"hide": False}}],
    }

    result = store.plan(request)

    job_dir = tmp_path / "jobs" / result["job_id"]
    assert result["state"] == "planned"
    assert result["task_count"] == 1
    assert result["job_dir"] == str(job_dir)
    assert (job_dir / "manifest.json").exists()
    assert (job_dir / "status.json").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "run.log").exists()
    assert (job_dir / "inputs" / "request.json").exists()
    assert (job_dir / "tasks" / "task_0001.json").exists()
    assert (job_dir / "models").is_dir()
    assert (job_dir / "results").is_dir()
    assert (job_dir / "evidence").is_dir()

    manifest = read_json(job_dir / "manifest.json")
    status = read_json(job_dir / "status.json")
    task = read_json(job_dir / "tasks" / "task_0001.json")

    assert manifest["job_id"] == result["job_id"]
    assert manifest["mode"] == "mock"
    assert manifest["job_type"] == "geometry-smoke"
    assert manifest["code_version"] == "test-sha"
    assert status["state"] == "planned"
    assert status["task_counts"]["pending"] == 1
    assert task["task_id"] == "task_0001"
    assert task["state"] == "pending"
    assert task["operation"] == "geometry-smoke"
