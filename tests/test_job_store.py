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


def test_update_manifest_merges_top_level_metadata(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.plan({"mode": "mock", "job_type": "geometry-smoke"})

    manifest = store.update_manifest(
        job["job_id"],
        {"template": {"sha256": "abc", "size_bytes": 3}},
    )

    assert manifest["job_id"] == job["job_id"]
    assert manifest["job_type"] == "geometry-smoke"
    assert manifest["template"] == {"sha256": "abc", "size_bytes": 3}
    assert store.get(job["job_id"])["manifest"]["template"]["sha256"] == "abc"


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


def test_plan_accepts_metasurface_sweep_and_creates_sample_tasks(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    result = store.plan({"mode": "mock", "job_type": "metasurface-sweep"})

    job_dir = tmp_path / "jobs" / result["job_id"]
    tasks = [
        read_json(path)
        for path in sorted((job_dir / "tasks").glob("task_*.json"))
    ]
    manifest = read_json(job_dir / "manifest.json")

    assert result["state"] == "planned"
    assert result["task_count"] == 4
    assert manifest["job_type"] == "metasurface-sweep"
    assert {task["operation"] for task in tasks} == {"metasurface-sample"}
    assert tasks[0]["input"]["ratio"] == 0.2
    assert tasks[-1]["input"]["period"] == 540e-9


def test_mock_metasurface_start_writes_one_result_per_sample(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    result = store.start({"mode": "mock", "job_type": "metasurface-sweep"})

    summary = read_json(tmp_path / "jobs" / result["job_id"] / "summary.json")

    assert summary["task_counts"]["succeeded"] == 4
    assert len(summary["results"]) == 4
    assert all(item["synthetic"] is True for item in summary["results"])


def test_enqueue_creates_queued_job_without_executing(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    result = store.enqueue(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "config": {
                    "RATIO_LIST": [0.2, 0.8],
                    "PERIOD_LIST": [390e-9, 540e-9],
                }
            },
            "approval": {"approved": True, "approved_for": "real_run"},
        }
    )

    assert result["state"] == "queued"
    assert result["task_count"] == 4
    assert all(
        task["state"] == "pending"
        for task in store.list_tasks(result["job_id"])["tasks"]
    )


def test_update_task_persists_phase_outputs_and_error(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.plan({"mode": "mock", "job_type": "geometry-smoke"})

    task = store.update_task(
        job["job_id"],
        "task_0001",
        state="running",
        phase="generating",
        outputs={"model_file": "models/task_0001.fsp"},
        error=None,
    )

    assert task["state"] == "running"
    assert task["phase"] == "generating"
    assert task["outputs"]["model_file"].endswith("task_0001.fsp")


def test_recover_interrupted_jobs_marks_running_state_retriable(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.plan(
        {
            "mode": "mock",
            "job_type": "geometry-smoke",
            "tasks": [
                {"operation": "geometry-smoke", "input": {}},
                {"operation": "geometry-smoke", "input": {}},
            ],
        }
    )
    job_id = job["job_id"]
    store.update_task(
        job_id,
        "task_0001",
        state="succeeded",
        phase="complete",
    )
    store.update_task(
        job_id,
        "task_0002",
        state="running",
        phase="solving",
    )
    store._write_status(job_id, "running", "Job running.")

    recovered = store.recover_interrupted_jobs()

    assert recovered == [job_id]
    state = store.get(job_id)
    tasks = store.list_tasks(job_id)["tasks"]
    assert state["status"]["state"] == "partial"
    assert tasks[0]["state"] == "succeeded"
    assert tasks[1]["state"] == "failed"
    assert tasks[1]["error"]["type"] == "interrupted"


import hashlib


def create_real_metasurface_job_with_template(store, tmp_path):
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"original-template")
    job = store.enqueue(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "template": str(template),
                "config": {
                    "RATIO_LIST": [0.2],
                    "PERIOD_LIST": [390e-9],
                },
            },
            "approval": {
                "approved": True,
                "approved_for": "real_run",
            },
        }
    )
    store.update_manifest(
        job["job_id"],
        {
            "template": {
                "path": str(template),
                "sha256": hashlib.sha256(
                    template.read_bytes()
                ).hexdigest(),
                "size_bytes": template.stat().st_size,
                "modified_at": template.stat().st_mtime,
            }
        },
    )
    return job, template


def test_real_metasurface_resume_allows_unchanged_template(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job, _ = create_real_metasurface_job_with_template(store, tmp_path)

    resumed = store.resume(job["job_id"])

    assert resumed["task_ids"] == ["task_0001"]


def test_real_metasurface_resume_rejects_changed_template(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job, template = create_real_metasurface_job_with_template(store, tmp_path)
    template.write_bytes(b"changed-template")

    with pytest.raises(JobError) as error:
        store.resume(job["job_id"])

    assert error.value.error_type == "resume_conflict"
    assert error.value.status_code == 409


def test_real_metasurface_resume_rejects_missing_template(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job, template = create_real_metasurface_job_with_template(store, tmp_path)
    template.unlink()

    with pytest.raises(JobError) as error:
        store.resume(job["job_id"])

    assert error.value.error_type == "resume_conflict"


def test_old_real_metasurface_job_without_fingerprint_cannot_resume(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    job = store.enqueue(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {"template": str(template)},
            "approval": {
                "approved": True,
                "approved_for": "real_run",
            },
        }
    )

    with pytest.raises(JobError) as error:
        store.resume(job["job_id"])

    assert error.value.error_type == "resume_conflict"


def test_mock_resume_does_not_require_template_fingerprint(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.plan({"mode": "mock", "job_type": "metasurface-sweep"})

    resumed = store.resume(job["job_id"])

    assert len(resumed["task_ids"]) == 4


from unittest.mock import patch


def test_jobs_plan_notifies_after_persistent_files_exist(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with patch("src.job_store.notify_job_state") as notify:
        job = store.plan(
            {"mode": "mock", "job_type": "geometry-smoke"}
        )

    job_dir = tmp_path / "jobs" / job["job_id"]
    notify.assert_called_once_with(job_dir, "planned")
    assert (job_dir / "status.json").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "run.log").exists()


def test_mock_start_notifies_succeeded_once(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with patch("src.job_store.notify_job_state") as notify:
        job = store.start(
            {"mode": "mock", "job_type": "geometry-smoke"}
        )

    notify.assert_called_once_with(
        tmp_path / "jobs" / job["job_id"],
        "succeeded",
    )


def test_finalize_notifies_partial_after_summary_is_written(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.plan(
        {
            "mode": "mock",
            "job_type": "geometry-smoke",
            "tasks": [
                {"operation": "geometry-smoke", "input": {}},
                {"operation": "geometry-smoke", "input": {}},
            ],
        }
    )
    store.update_task(job["job_id"], "task_0001", state="succeeded")
    store.update_task(job["job_id"], "task_0002", state="failed")

    with patch("src.job_store.notify_job_state") as notify:
        result = store.finalize(job["job_id"])

    assert result["state"] == "partial"
    notify.assert_called_once_with(
        tmp_path / "jobs" / job["job_id"],
        "partial",
    )


def test_fail_marks_unfinished_tasks_failed_and_notifies(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.enqueue(
        {
            "mode": "real",
            "job_type": "geometry-smoke",
            "approval": {
                "approved": True,
                "approved_for": "real_run",
            },
        }
    )

    with patch("src.job_store.notify_job_state") as notify:
        result = store.fail(
            job["job_id"], RuntimeError("solver crashed")
        )

    task = store.list_tasks(job["job_id"])["tasks"][0]
    assert result["state"] == "failed"
    assert task["state"] == "failed"
    assert task["error"]["type"] == "RuntimeError"
    assert task["error"]["message"] == "solver crashed"
    notify.assert_called_once_with(
        tmp_path / "jobs" / job["job_id"],
        "failed",
    )
