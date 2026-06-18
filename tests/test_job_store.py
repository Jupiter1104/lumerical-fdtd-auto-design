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


def test_mock_start_marks_task_and_job_succeeded(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    result = store.start({"mode": "mock", "job_type": "geometry-smoke"})

    job_dir = tmp_path / "jobs" / result["job_id"]
    status = read_json(job_dir / "status.json")
    task = read_json(job_dir / "tasks" / "task_0001.json")
    summary = read_json(job_dir / "summary.json")

    assert result["state"] == "succeeded"
    assert status["state"] == "succeeded"
    assert status["task_counts"]["succeeded"] == 1
    assert task["state"] == "succeeded"
    assert task["attempts"] == 1
    assert task["outputs"]["mode"] == "mock"
    assert summary["task_counts"]["succeeded"] == 1


def test_real_start_requires_approval(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with pytest.raises(JobError) as error:
        store.start({"mode": "real", "job_type": "geometry-smoke"})

    assert error.value.error_type == "approval_required"
    assert error.value.status_code == 403


def test_idempotency_key_reuses_same_job_for_same_request(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    request = {
        "mode": "mock",
        "job_type": "geometry-smoke",
        "idempotency_key": "same-key",
    }

    first = store.start(request)
    second = store.start(request)

    assert second["job_id"] == first["job_id"]
    assert len(list((tmp_path / "jobs").glob("job_*"))) == 1


def test_idempotency_key_rejects_different_request(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    store.start(
        {
            "mode": "mock",
            "job_type": "geometry-smoke",
            "idempotency_key": "same-key",
        }
    )

    with pytest.raises(JobError) as error:
        store.start(
            {
                "mode": "mock",
                "job_type": "geometry-smoke",
                "idempotency_key": "same-key",
                "tasks": [
                    {
                        "operation": "geometry-smoke",
                        "input": {"hide": True},
                    }
                ],
            }
        )

    assert error.value.error_type == "idempotency_conflict"
    assert error.value.status_code == 409


def test_resume_selects_pending_and_failed_tasks_only(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    result = store.plan(
        {
            "mode": "mock",
            "job_type": "geometry-smoke",
            "tasks": [
                {"operation": "geometry-smoke", "input": {"index": 1}},
                {"operation": "geometry-smoke", "input": {"index": 2}},
                {"operation": "geometry-smoke", "input": {"index": 3}},
            ],
        }
    )
    job_id = result["job_id"]
    tasks_dir = tmp_path / "jobs" / job_id / "tasks"
    task_1 = read_json(tasks_dir / "task_0001.json")
    task_2 = read_json(tasks_dir / "task_0002.json")
    task_3 = read_json(tasks_dir / "task_0003.json")
    task_1["state"] = "succeeded"
    task_2["state"] = "failed"
    task_3["state"] = "pending"
    store._write_json(tasks_dir / "task_0001.json", task_1)
    store._write_json(tasks_dir / "task_0002.json", task_2)
    store._write_json(tasks_dir / "task_0003.json", task_3)

    resume = store.resume(job_id)

    assert resume["task_ids"] == ["task_0002", "task_0003"]
