"""Tests for recipe-sweep persistent job support (Task 8)."""

import json
from pathlib import Path

import pytest

from src.job_store import JobError, JobStore


# ── shared test fixtures ─────────────────────────────────────────────────

RECIPE = {
    "schema_version": "1.0",
    "parameters": {
        "period": {
            "type": "float",
            "default": 500e-9,
            "min": 300e-9,
            "max": 700e-9,
        },
        "duty_cycle": {
            "type": "float",
            "default": 0.5,
            "min": 0.1,
            "max": 0.9,
        },
    },
    "assumptions": [
        {
            "parameter": "period",
            "reason": "Typical visible wavelength grating period",
        },
        {
            "parameter": "duty_cycle",
            "reason": "Balanced fill factor for 1st-order efficiency",
        },
    ],
    "materials": [
        {"name": "substrate", "type": "SiO2", "properties": {"index": 1.45}},
        {"name": "grating", "type": "Si", "properties": {"index": 3.5}},
    ],
    "geometry": [
        {
            "type": "rectangle",
            "name": "substrate",
            "properties": {
                "x_span": "${period}",
                "y_span": "${period} * 0.5",
            },
        },
    ],
}

SWEEP_PLAN = {
    "schema_version": "1.0",
    "parameters": [
        {"name": "period", "values": [400e-9, 500e-9]},
        {"name": "duty_cycle", "values": [0.3, 0.7]},
    ],
    "max_tasks": 100,
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Step 1: plan layout tests ────────────────────────────────────────────


def test_plan_creates_recipe_sweep_directory_structure(tmp_path):
    """Verify that /jobs/plan with job_type=recipe-sweep writes the full layout."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    request = {
        "mode": "plan",
        "job_type": "recipe-sweep",
        "recipe": RECIPE,
        "sweep_plan": SWEEP_PLAN,
    }

    result = store.plan(request)

    job_dir = tmp_path / "jobs" / result["job_id"]
    assert result["state"] == "planned"
    assert result["task_count"] == 4  # 2 periods x 2 duty cycles
    assert result["job_dir"] == str(job_dir)

    # Standard layout
    assert (job_dir / "manifest.json").exists()
    assert (job_dir / "status.json").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "run.log").exists()
    assert (job_dir / "inputs" / "request.json").exists()

    # Recipe-sweep specific layout
    assert (job_dir / "inputs" / "recipe.json").exists()
    assert (job_dir / "inputs" / "sweep_plan.json").exists()
    assert (job_dir / "compiled" / "compile_report.json").exists()
    assert (job_dir / "compiled" / "scripts").is_dir()

    # Task stubs
    tasks_dir = job_dir / "tasks"
    task_files = sorted(tasks_dir.glob("task_*.json"))
    assert len(task_files) == 4

    # Compiled scripts
    scripts_dir = job_dir / "compiled" / "scripts"
    script_files = sorted(scripts_dir.glob("*.lsf"))
    assert len(script_files) == 4


def test_plan_task_json_includes_required_keys(tmp_path):
    """Each task JSON must have task_id, index, parameters, script_sha256,
    synthetic, status, model_path, metrics_path."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    result = store.plan(
        {
            "mode": "plan",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )

    job_dir = tmp_path / "jobs" / result["job_id"]
    task = read_json(job_dir / "tasks" / "task_0001.json")

    assert "task_id" in task
    assert "index" in task
    assert "parameters" in task
    assert "script_sha256" in task
    assert "synthetic" in task
    assert "status" in task
    assert "model_path" in task
    assert "metrics_path" in task

    # Verify types
    assert task["task_id"] == "task_0001"
    assert isinstance(task["index"], int)
    assert isinstance(task["parameters"], dict)
    assert task["script_sha256"].startswith("sha256:")
    assert task["synthetic"] is False  # planned, not yet run
    assert task["status"] == "pending"
    # model_path and metrics_path are None for planned jobs
    assert task["model_path"] is None
    assert task["metrics_path"] is None


def test_plan_writes_recipe_and_sweep_plan_to_inputs(tmp_path):
    """Inputs directory must contain the normalized recipe and sweep plan."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    result = store.plan(
        {
            "mode": "plan",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )

    job_dir = tmp_path / "jobs" / result["job_id"]
    saved_recipe = read_json(job_dir / "inputs" / "recipe.json")
    saved_sweep = read_json(job_dir / "inputs" / "sweep_plan.json")

    assert saved_recipe["schema_version"] == "1.0"
    assert "parameters" in saved_recipe
    assert saved_sweep["schema_version"] == "1.0"
    assert len(saved_sweep["parameters"]) == 2


def test_plan_writes_compile_report(tmp_path):
    """compiled/compile_report.json must contain sweep metadata."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    result = store.plan(
        {
            "mode": "plan",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )

    job_dir = tmp_path / "jobs" / result["job_id"]
    report = read_json(job_dir / "compiled" / "compile_report.json")

    assert report["ok"] is True
    assert "plan" in report
    assert report["plan"]["task_count"] == 4
    assert "recipe_fingerprint" in report["plan"]
    assert "sweep_fingerprint" in report["plan"]
    assert "packet_fingerprint" in report["plan"]


def test_plan_compiled_scripts_are_nonempty_lsf(tmp_path):
    """Each compiled script must be a non-empty .lsf file."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    result = store.plan(
        {
            "mode": "plan",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )

    job_dir = tmp_path / "jobs" / result["job_id"]
    for script_path in sorted((job_dir / "compiled" / "scripts").glob("*.lsf")):
        content = script_path.read_text(encoding="utf-8")
        assert len(content) > 0
        assert "# FDTD Device Recipe" in content
        # Verify script filename matches a task_id
        assert script_path.stem.startswith("task_")


def test_plan_rejects_invalid_recipe(tmp_path):
    """Plan must reject a recipe that fails validation."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with pytest.raises(JobError) as error:
        store.plan(
            {
                "mode": "plan",
                "job_type": "recipe-sweep",
                "recipe": {"not": "a valid recipe"},
                "sweep_plan": SWEEP_PLAN,
            }
        )

    assert error.value.error_type == "validation_error"
    assert error.value.status_code == 400


def test_plan_rejects_invalid_sweep_plan(tmp_path):
    """Plan must reject a sweep plan that fails validation."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with pytest.raises(JobError) as error:
        store.plan(
            {
                "mode": "plan",
                "job_type": "recipe-sweep",
                "recipe": RECIPE,
                "sweep_plan": {"not": "a valid sweep plan"},
            }
        )

    assert error.value.error_type == "validation_error"
    assert error.value.status_code == 400


def test_plan_rejects_unknown_sweep_parameter(tmp_path):
    """Sweep parameter not in recipe must be rejected."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    bad_sweep = {
        "schema_version": "1.0",
        "parameters": [
            {"name": "nonexistent_param", "values": [1.0, 2.0]},
        ],
        "max_tasks": 100,
    }

    with pytest.raises(JobError) as error:
        store.plan(
            {
                "mode": "plan",
                "job_type": "recipe-sweep",
                "recipe": RECIPE,
                "sweep_plan": bad_sweep,
            }
        )

    assert error.value.error_type == "validation_error"
    assert error.value.status_code == 400


# ── Step 2: mock start tests ─────────────────────────────────────────────


def test_mock_start_creates_job_and_writes_synthetic_metrics(tmp_path):
    """Mock start must create job structure and write synthetic metrics."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    result = store.start(
        {
            "mode": "mock",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )

    job_dir = tmp_path / "jobs" / result["job_id"]
    assert result["state"] == "succeeded"
    assert result["task_count"] == 4

    # Compiled scripts must exist
    assert (job_dir / "compiled" / "scripts").is_dir()
    assert len(list((job_dir / "compiled" / "scripts").glob("*.lsf"))) == 4

    # Inputs must exist
    assert (job_dir / "inputs" / "recipe.json").exists()
    assert (job_dir / "inputs" / "sweep_plan.json").exists()

    # Summary must be written
    summary = read_json(job_dir / "summary.json")
    assert summary["task_counts"]["succeeded"] == 4

    # Each task must have synthetic=True
    for task_path in sorted((job_dir / "tasks").glob("task_*.json")):
        task = read_json(task_path)
        assert task["synthetic"] is True
        assert task["status"] == "succeeded"


def test_mock_start_writes_metrics_paths(tmp_path):
    """Mock start must populate model_path and metrics_path on each task."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    result = store.start(
        {
            "mode": "mock",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )

    job_dir = tmp_path / "jobs" / result["job_id"]
    for task_path in sorted((job_dir / "tasks").glob("task_*.json")):
        task = read_json(task_path)
        assert task["model_path"] is not None
        assert task["metrics_path"] is not None
        # Check that metrics file exists on disk
        assert Path(task["metrics_path"]).exists()
        # Check that metrics file contains synthetic=True
        metrics = read_json(Path(task["metrics_path"]))
        assert metrics["synthetic"] is True


# ── Step 3: real start handshake tests ───────────────────────────────────


def test_real_start_requires_packet_fingerprint(tmp_path):
    """Real start must require a packet_fingerprint."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with pytest.raises(JobError) as error:
        store.start(
            {
                "mode": "real",
                "job_type": "recipe-sweep",
                "recipe": RECIPE,
                "sweep_plan": SWEEP_PLAN,
                "approval": {"approved": True, "approved_for": "real_run"},
                # no packet_fingerprint
            }
        )

    assert error.value.error_type == "validation_error"
    assert error.value.status_code == 400


def test_real_start_requires_approval(tmp_path):
    """Real start must require approval object."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with pytest.raises(JobError) as error:
        store.start(
            {
                "mode": "real",
                "job_type": "recipe-sweep",
                "recipe": RECIPE,
                "sweep_plan": SWEEP_PLAN,
                "packet_fingerprint": "sha256:deadbeef",
                # no approval
            }
        )

    assert error.value.error_type == "approval_required"
    assert error.value.status_code == 403


def test_real_start_rejects_wrong_packet_fingerprint(tmp_path):
    """Real start must reject a mismatched packet fingerprint."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with pytest.raises(JobError) as error:
        store.start(
            {
                "mode": "real",
                "job_type": "recipe-sweep",
                "recipe": RECIPE,
                "sweep_plan": SWEEP_PLAN,
                "packet_fingerprint": "sha256:00000000000000000000000000000000wrong",
                "approval": {"approved": True, "approved_for": "real_run"},
            }
        )

    assert error.value.error_type == "fingerprint_mismatch"
    assert error.value.status_code == 409


def test_real_start_with_valid_fingerprint_and_approval_returns_job(tmp_path):
    """Real start with correct fingerprint and approval creates queued job."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    # First, plan to get the packet_fingerprint
    plan_result = store.plan(
        {
            "mode": "plan",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )

    compile_report = read_json(
        tmp_path / "jobs" / plan_result["job_id"] / "compiled" / "compile_report.json"
    )
    packet_fp = compile_report["plan"]["packet_fingerprint"]

    # Now start with real mode using the correct fingerprint
    result = store.start(
        {
            "mode": "real",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
            "packet_fingerprint": packet_fp,
            "approval": {"approved": True, "approved_for": "real_run"},
        }
    )

    assert result["state"] == "queued"
    assert result["task_count"] == 4
    assert result["job_id"].startswith("job_")

    # Compiled scripts must exist
    job_dir = tmp_path / "jobs" / result["job_id"]
    assert (job_dir / "compiled" / "scripts").is_dir()
    assert (job_dir / "compiled" / "compile_report.json").exists()


def test_real_start_tasks_have_synthetic_false(tmp_path):
    """Real start tasks must have synthetic=False (not mock)."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    # Plan first to get fingerprint
    plan_result = store.plan(
        {
            "mode": "plan",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )
    compile_report = read_json(
        tmp_path / "jobs" / plan_result["job_id"] / "compiled" / "compile_report.json"
    )
    packet_fp = compile_report["plan"]["packet_fingerprint"]

    result = store.start(
        {
            "mode": "real",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
            "packet_fingerprint": packet_fp,
            "approval": {"approved": True, "approved_for": "real_run"},
        }
    )

    job_dir = tmp_path / "jobs" / result["job_id"]
    for task_path in sorted((job_dir / "tasks").glob("task_*.json")):
        task = read_json(task_path)
        assert task["synthetic"] is False
        assert task["status"] == "pending"


def test_idempotency_works_for_recipe_sweep(tmp_path):
    """Idempotency keys must work for recipe-sweep jobs."""
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    plan_result = store.plan(
        {
            "mode": "plan",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )
    compile_report = read_json(
        tmp_path / "jobs" / plan_result["job_id"] / "compiled" / "compile_report.json"
    )
    packet_fp = compile_report["plan"]["packet_fingerprint"]

    request = {
        "mode": "real",
        "job_type": "recipe-sweep",
        "recipe": RECIPE,
        "sweep_plan": SWEEP_PLAN,
        "packet_fingerprint": packet_fp,
        "approval": {"approved": True, "approved_for": "real_run"},
        "idempotency_key": "recipe-sweep-key-1",
    }

    first = store.start(request)
    second = store.start(request)

    assert second["job_id"] == first["job_id"]
    assert len(list((tmp_path / "jobs").glob("job_*"))) == 2  # plan job + start job


def test_plan_notifies_with_feishu_webhook_set(tmp_path, monkeypatch):
    """Plan must send Feishu notification when webhook is configured."""
    monkeypatch.setenv("FDTD_FEISHU_WEBHOOK", "https://hooks.example.com/test")
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    result = store.plan(
        {
            "mode": "plan",
            "job_type": "recipe-sweep",
            "recipe": RECIPE,
            "sweep_plan": SWEEP_PLAN,
        }
    )

    assert result["state"] == "planned"
    # Notification should have been attempted
    log_content = (tmp_path / "jobs" / result["job_id"] / "run.log").read_text(
        encoding="utf-8"
    )
    assert "Feishu notification" in log_content
