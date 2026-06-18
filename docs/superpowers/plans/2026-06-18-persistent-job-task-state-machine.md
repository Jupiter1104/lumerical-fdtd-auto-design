# Persistent Job Task State Machine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first persistent job/task state machine for RPC API v1 so jobs survive process restarts, support idempotency, enforce real-run approval, and expose status through HTTP.

**Architecture:** Add a focused `src/job_store.py` module that owns disk persistence under `jobs/`. Wire it into `rpc_server.py` through injectable `JobStore`, keeping the existing session/model/geometry endpoints stable. Add client helpers after the server contract is tested.

**Tech Stack:** Python 3.9, Flask, pytest, JSON files, pathlib, existing RPC API v1 envelope.

---

## File Structure

- Create `src/job_store.py`
  - Owns job directory creation, JSON read/write, request hashing, idempotency index, task state updates, summary generation, and resume candidate selection.
  - Has no Flask dependency and no lumapi dependency.
- Create `tests/test_job_store.py`
  - Tests disk layout, planning, mock execution, idempotency, approval, and resume rules.
- Create `tests/test_rpc_server_jobs.py`
  - Tests `/jobs/*` endpoints with a temporary `JobStore` and fake `SessionManager`.
- Modify `rpc_server.py`
  - Inject `job_store` into `create_app`.
  - Add `/jobs/plan`, `/jobs/start`, `/jobs/<job_id>`, `/jobs/<job_id>/tasks`, `/jobs/<job_id>/resume`.
  - Add a tiny `geometry-smoke` executor that reuses existing `SessionManager` methods.
- Modify `src/rpc_client/client.py`
  - Add thin job endpoint methods.
- Modify `tests/test_rpc_client_contract.py`
  - Add client route coverage for job methods.
- Modify `.gitignore`
  - Add `jobs/`.
- Modify docs at the end
  - Update `docs/RPC_API_V1.md`, `README.md`, `TECH_STACK.md`, `SOP.md`, and `DEV_LOG.md` only after tests pass.

## Task 1: Add JobStore disk layout and plan mode

**Files:**
- Create: `src/job_store.py`
- Create: `tests/test_job_store.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing JobStore plan tests**

Add this file:

```python
# tests/test_job_store.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py::test_plan_creates_persistent_job_layout -q
```

Expected: fail with `ModuleNotFoundError: No module named 'src.job_store'`.

- [ ] **Step 3: Implement minimal JobStore plan support**

Create `src/job_store.py` with this structure:

```python
"""Persistent job/task storage for RPC API v1."""

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Set, Union


JOB_STATES = {"planned", "queued", "running", "succeeded", "failed", "partial"}
TASK_STATES = {"pending", "running", "succeeded", "failed", "skipped"}


class JobError(Exception):
    """Expected job-store error that can be mapped to the RPC v1 envelope."""

    def __init__(self, error_type: str, message: str, status_code: int, details: Optional[dict] = None):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_hash(request: dict) -> str:
    return hashlib.sha256(stable_json(request).encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_").lower()
    return slug or "job"


class JobStore:
    def __init__(self, root: Union[Path, str] = "jobs", code_version: str = "unknown"):
        self.root = Path(root)
        self.code_version = code_version

    def plan(self, request: dict) -> dict:
        normalized = self._normalize_request(request)
        job_id = self._new_job_id(normalized["job_type"])
        return self._create_job(job_id, normalized, state="planned")

    def _normalize_request(self, request: dict) -> dict:
        if not isinstance(request, dict):
            raise JobError("validation_error", "JSON body must be an object.", 400)
        mode = request.get("mode", "mock")
        job_type = request.get("job_type", "geometry-smoke")
        if mode not in {"plan", "mock", "real"}:
            raise JobError("validation_error", "mode must be one of plan, mock, or real.", 400)
        if job_type != "geometry-smoke":
            raise JobError("validation_error", "job_type must be geometry-smoke in v1.", 400)
        tasks = request.get("tasks") or [
            {"operation": "geometry-smoke", "input": {"hide": bool(request.get("hide", False))}}
        ]
        if not isinstance(tasks, list) or not tasks:
            raise JobError("validation_error", "tasks must be a non-empty list.", 400)
        return {
            "mode": mode,
            "job_type": job_type,
            "idempotency_key": request.get("idempotency_key"),
            "approval": request.get("approval") or {"approved": False, "approved_for": None},
            "tasks": tasks,
        }

    def _new_job_id(self, job_type: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"job_{timestamp}_{slugify(job_type)}"
        candidate = base
        counter = 2
        while (self.root / candidate).exists():
            candidate = f"{base}_{counter}"
            counter += 1
        return candidate

    def _create_job(self, job_id: str, request: dict, state: str) -> dict:
        job_dir = self.root / job_id
        paths = {
            "job_dir": str(job_dir),
            "tasks_dir": str(job_dir / "tasks"),
            "models_dir": str(job_dir / "models"),
            "results_dir": str(job_dir / "results"),
            "evidence_dir": str(job_dir / "evidence"),
        }
        for path in [
            job_dir,
            job_dir / "inputs",
            job_dir / "tasks",
            job_dir / "models",
            job_dir / "results",
            job_dir / "evidence",
        ]:
            path.mkdir(parents=True, exist_ok=False if path == job_dir else True)

        created_at = utc_now()
        digest = request_hash(request)
        manifest = {
            "job_id": job_id,
            "created_at": created_at,
            "mode": request["mode"],
            "job_type": request["job_type"],
            "idempotency_key": request.get("idempotency_key"),
            "request_hash": digest,
            "code_version": self.code_version,
            "rpc_api_version": "v1",
            "paths": paths,
            "approval": request["approval"],
        }
        self._write_json(job_dir / "manifest.json", manifest)
        self._write_json(job_dir / "inputs" / "request.json", request)
        for index, task_input in enumerate(request["tasks"], start=1):
            task_id = f"task_{index:04d}"
            task = {
                "task_id": task_id,
                "state": "pending",
                "mode": request["mode"],
                "operation": task_input.get("operation", request["job_type"]),
                "input": task_input.get("input", {}),
                "outputs": {},
                "error": None,
                "attempts": 0,
                "created_at": created_at,
                "updated_at": created_at,
            }
            self._write_json(job_dir / "tasks" / f"{task_id}.json", task)
        self._write_status(job_id, state, f"Job {state}.")
        self._write_summary(job_id)
        (job_dir / "run.log").write_text(f"{created_at} Job {state}.\\n", encoding="utf-8")
        return {
            "job_id": job_id,
            "state": state,
            "task_count": len(request["tasks"]),
            "job_dir": str(job_dir),
        }

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\\n", encoding="utf-8")
        os.replace(tmp_path, path)

    def _read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _job_dir(self, job_id: str) -> Path:
        job_dir = self.root / job_id
        if not (job_dir / "manifest.json").exists():
            raise JobError("job_not_found", f"Job not found: {job_id}", 404, {"job_id": job_id})
        return job_dir

    def _tasks(self, job_id: str) -> list:
        tasks_dir = self._job_dir(job_id) / "tasks"
        return [self._read_json(path) for path in sorted(tasks_dir.glob("task_*.json"))]

    def _task_counts(self, tasks: list) -> dict:
        counts = {state: 0 for state in TASK_STATES}
        for task in tasks:
            counts[task["state"]] += 1
        return {"total": len(tasks), **counts}

    def _write_status(self, job_id: str, state: str, message: str) -> dict:
        tasks = self._tasks(job_id)
        now = utc_now()
        status_path = self._job_dir(job_id) / "status.json"
        previous = self._read_json(status_path) if status_path.exists() else {}
        status = {
            "job_id": job_id,
            "state": state,
            "message": message,
            "task_counts": self._task_counts(tasks),
            "started_at": previous.get("started_at"),
            "updated_at": now,
            "finished_at": now if state in {"succeeded", "failed", "partial"} else None,
        }
        self._write_json(status_path, status)
        return status

    def _write_summary(self, job_id: str) -> dict:
        tasks = self._tasks(job_id)
        summary = {
            "job_id": job_id,
            "task_counts": self._task_counts(tasks),
            "results": [task["outputs"] for task in tasks if task["state"] == "succeeded"],
        }
        self._write_json(self._job_dir(job_id) / "summary.json", summary)
        return summary
```

- [ ] **Step 4: Add jobs to gitignore**

Add this line under runtime outputs in `.gitignore`:

```gitignore
jobs/
```

- [ ] **Step 5: Run task tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py::test_plan_creates_persistent_job_layout -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add .gitignore src/job_store.py tests/test_job_store.py
git commit -m "feat: add persistent job store plan mode"
```

## Task 2: Add start, approval, idempotency, and resume rules

**Files:**
- Modify: `src/job_store.py`
- Modify: `tests/test_job_store.py`

- [ ] **Step 1: Add failing tests**

Append these tests to `tests/test_job_store.py`:

```python
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
    store.start({"mode": "mock", "job_type": "geometry-smoke", "idempotency_key": "same-key"})

    with pytest.raises(JobError) as error:
        store.start(
            {
                "mode": "mock",
                "job_type": "geometry-smoke",
                "idempotency_key": "same-key",
                "tasks": [{"operation": "geometry-smoke", "input": {"hide": True}}],
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py -q
```

Expected: fail because `JobStore.start` and `JobStore.resume` do not exist.

- [ ] **Step 3: Implement start, idempotency, and resume**

Add these methods to `JobStore` in `src/job_store.py`:

```python
    def start(self, request: dict, executor: Optional[Callable[[dict, Path], dict]] = None) -> dict:
        normalized = self._normalize_request(request)
        if normalized["mode"] == "real":
            approval = normalized["approval"]
            if approval.get("approved") is not True or approval.get("approved_for") != "real_run":
                raise JobError("approval_required", "Real jobs require explicit approval.", 403)
        existing = self._find_idempotent_job(normalized)
        if existing:
            return existing
        job_id = self._new_job_id(normalized["job_type"])
        result = self._create_job(job_id, normalized, state="queued")
        self._remember_idempotency(normalized, job_id)
        self._run_job(job_id, executor)
        return self.get(job_id)

    def get(self, job_id: str) -> dict:
        job_dir = self._job_dir(job_id)
        return {
            "job_id": job_id,
            "manifest": self._read_json(job_dir / "manifest.json"),
            "status": self._read_json(job_dir / "status.json"),
            "summary": self._read_json(job_dir / "summary.json"),
        }

    def list_tasks(self, job_id: str) -> dict:
        return {"job_id": job_id, "tasks": self._tasks(job_id)}

    def resume(self, job_id: str, executor: Optional[Callable[[dict, Path], dict]] = None) -> dict:
        tasks = self._tasks(job_id)
        selected = [task["task_id"] for task in tasks if task["state"] in {"pending", "failed"}]
        if executor is not None and selected:
            self._run_job(job_id, executor, only_task_ids=set(selected))
        return {"job_id": job_id, "task_ids": selected}

    def _run_job(
        self,
        job_id: str,
        executor: Optional[Callable[[dict, Path], dict]] = None,
        only_task_ids: Optional[Set[str]] = None,
    ) -> None:
        self._write_status(job_id, "running", "Job running.")
        job_dir = self._job_dir(job_id)
        selected_tasks = []
        for task in self._tasks(job_id):
            if only_task_ids is None or task["task_id"] in only_task_ids:
                selected_tasks.append(task)
        for task in selected_tasks:
            self._run_task(job_id, task, executor)
        tasks = self._tasks(job_id)
        counts = self._task_counts(tasks)
        if counts["failed"]:
            state = "partial" if counts["succeeded"] else "failed"
        elif counts["pending"] or counts["running"]:
            state = "partial"
        else:
            state = "succeeded"
        self._write_status(job_id, state, f"Job {state}.")
        self._write_summary(job_id)

    def _run_task(self, job_id: str, task: dict, executor: Optional[Callable[[dict, Path], dict]]) -> None:
        job_dir = self._job_dir(job_id)
        task_path = job_dir / "tasks" / f"{task['task_id']}.json"
        now = utc_now()
        task["state"] = "running"
        task["attempts"] += 1
        task["updated_at"] = now
        task["error"] = None
        self._write_json(task_path, task)
        try:
            if executor is None:
                outputs = {"mode": task["mode"], "operation": task["operation"]}
            else:
                outputs = executor(task, job_dir)
            task["state"] = "succeeded"
            task["outputs"] = outputs or {}
            task["error"] = None
        except Exception as exc:
            task["state"] = "failed"
            task["error"] = {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "details": {},
            }
        task["updated_at"] = utc_now()
        self._write_json(task_path, task)

    def _index_path(self) -> Path:
        return self.root / "index.json"

    def _read_index(self) -> dict:
        path = self._index_path()
        if not path.exists():
            return {"idempotency_keys": {}}
        return self._read_json(path)

    def _write_index(self, index: dict) -> None:
        self._write_json(self._index_path(), index)

    def _find_idempotent_job(self, request: dict) -> Optional[dict]:
        key = request.get("idempotency_key")
        if not key:
            return None
        digest = request_hash(request)
        record = self._read_index()["idempotency_keys"].get(key)
        if record is None:
            return None
        if record["request_hash"] != digest:
            raise JobError("idempotency_conflict", "idempotency_key was already used with different input.", 409)
        return self.get(record["job_id"])

    def _remember_idempotency(self, request: dict, job_id: str) -> None:
        key = request.get("idempotency_key")
        if not key:
            return
        index = self._read_index()
        index["idempotency_keys"][key] = {
            "job_id": job_id,
            "request_hash": request_hash(request),
        }
        self._write_index(index)
```

- [ ] **Step 4: Run JobStore tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py -q
```

Expected: all `tests/test_job_store.py` tests pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/job_store.py tests/test_job_store.py
git commit -m "feat: add job start idempotency and resume"
```

## Task 3: Add HTTP `/jobs/*` endpoints

**Files:**
- Modify: `rpc_server.py`
- Create: `tests/test_rpc_server_jobs.py`

- [ ] **Step 1: Write failing RPC endpoint tests**

Create `tests/test_rpc_server_jobs.py`:

```python
import importlib
import sys

import pytest

from src.job_store import JobStore


@pytest.fixture
def server_module():
    sys.modules.pop("rpc_server", None)
    return importlib.import_module("rpc_server")


@pytest.fixture
def fake_session():
    class FakeSession:
        @property
        def is_connected(self):
            return False

        def status(self):
            return {"connected": False, "version": None, "model_file": None}

        def start(self, hide=False):
            return {"version": "v242", "hide": hide}

        def addfdtd(self, **kwargs):
            return {"message": "region added"}

        def addrect(self, **kwargs):
            return {"message": "rectangle added"}

        def save(self, file_path=None):
            return {"saved_to": file_path}

        def close(self):
            return {"message": "closed", "close_state": "closed"}

    return FakeSession()


@pytest.fixture
def client(server_module, fake_session, tmp_path):
    app = server_module.create_app(
        fake_session,
        job_store=JobStore(tmp_path / "jobs", code_version="test-sha"),
    )
    app.config.update(TESTING=True)
    return app.test_client()


def test_jobs_plan_endpoint_creates_planned_job(client):
    response = client.post("/jobs/plan", json={"mode": "mock", "job_type": "geometry-smoke"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["state"] == "planned"
    assert payload["task_count"] == 1
    assert payload["job_id"].startswith("job_")


def test_jobs_start_mock_endpoint_succeeds(client):
    response = client.post("/jobs/start", json={"mode": "mock", "job_type": "geometry-smoke"})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"]["state"] == "succeeded"
    assert payload["summary"]["task_counts"]["succeeded"] == 1


def test_jobs_start_real_requires_approval(client):
    response = client.post("/jobs/start", json={"mode": "real", "job_type": "geometry-smoke"})
    payload = response.get_json()

    assert response.status_code == 403
    assert payload["ok"] is False
    assert payload["error"]["type"] == "approval_required"


def test_jobs_get_and_tasks_endpoints_read_disk_state(client):
    started = client.post("/jobs/start", json={"mode": "mock", "job_type": "geometry-smoke"}).get_json()
    job_id = started["job_id"]

    job_response = client.get(f"/jobs/{job_id}")
    tasks_response = client.get(f"/jobs/{job_id}/tasks")

    assert job_response.status_code == 200
    assert job_response.get_json()["status"]["state"] == "succeeded"
    assert tasks_response.status_code == 200
    assert tasks_response.get_json()["tasks"][0]["state"] == "succeeded"


def test_jobs_resume_returns_selected_tasks(client):
    planned = client.post(
        "/jobs/plan",
        json={
            "mode": "mock",
            "job_type": "geometry-smoke",
            "tasks": [{"operation": "geometry-smoke", "input": {"hide": False}}],
        },
    ).get_json()

    response = client.post(f"/jobs/{planned['job_id']}/resume", json={})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["task_ids"] == ["task_0001"]
```

- [ ] **Step 2: Run endpoint tests to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_rpc_server_jobs.py -q
```

Expected: fail because `create_app` does not accept `job_store` and `/jobs/*` routes do not exist.

- [ ] **Step 3: Wire JobError and JobStore into rpc_server**

Modify imports near the top of `rpc_server.py`:

```python
from src.job_store import JobError, JobStore
```

Add this error handler inside `create_app` after the `RpcError` handler:

```python
    @app.errorhandler(JobError)
    def handle_job_error(error):
        return (
            jsonify(
                _error_payload(
                    error.error_type,
                    error.message,
                    error.details,
                )
            ),
            error.status_code,
        )
```

Change the signature:

```python
def create_app(
    session_manager: Optional[SessionManager] = None,
    job_store: Optional[JobStore] = None,
) -> Flask:
```

Add this inside `create_app` after `session = session_manager or SessionManager()`:

```python
    jobs = job_store or JobStore()
```

- [ ] **Step 4: Add job routes**

Add these routes before `return app` in `rpc_server.py`:

```python
    @app.post("/jobs/plan")
    def jobs_plan():
        return _success(jobs.plan(_json_body()))

    @app.post("/jobs/start")
    def jobs_start():
        data = _json_body()
        executor = _geometry_smoke_executor(session) if data.get("mode") == "real" else None
        return _success(jobs.start(data, executor=executor))

    @app.get("/jobs/<job_id>")
    def jobs_get(job_id):
        return _success(jobs.get(job_id))

    @app.get("/jobs/<job_id>/tasks")
    def jobs_tasks(job_id):
        return _success(jobs.list_tasks(job_id))

    @app.post("/jobs/<job_id>/resume")
    def jobs_resume(job_id):
        data = _json_body()
        executor = _geometry_smoke_executor(session) if data.get("mode") == "real" else None
        return _success(jobs.resume(job_id, executor=executor))
```

Define the executor helper above `create_app`:

```python
def _geometry_smoke_executor(session: SessionManager):
    def run(task: dict, job_dir: Path) -> dict:
        hide = bool(task.get("input", {}).get("hide", False))
        started_here = False
        if not session.is_connected:
            session.start(hide=hide)
            started_here = True
        try:
            session.addfdtd(
                dimension="3D",
                x=0.0,
                x_span=2e-6,
                y=0.0,
                y_span=2e-6,
                z=0.0,
                z_span=1e-6,
                mesh_accuracy=2,
            )
            session.addrect(
                name=f"{task['task_id']}_waveguide",
                x=0.0,
                x_span=1e-6,
                y=0.0,
                y_span=500e-9,
                z=0.0,
                z_span=220e-9,
                material="Si (Silicon) - Palik",
            )
            model_path = job_dir / "models" / f"{task['task_id']}.fsp"
            saved = session.save(str(model_path))
            return {
                "model_file": saved.get("saved_to", str(model_path)),
                "hide": hide,
            }
        finally:
            if started_here:
                session.close()

    return run
```

- [ ] **Step 5: Run endpoint tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rpc_server_jobs.py tests/test_rpc_server_contract.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add rpc_server.py tests/test_rpc_server_jobs.py
git commit -m "feat: expose persistent job endpoints"
```

## Task 4: Add client job helpers

**Files:**
- Modify: `src/rpc_client/client.py`
- Modify: `tests/test_rpc_client_contract.py`

- [ ] **Step 1: Add failing client route tests**

Add these parametrized cases to `test_client_uses_v1_routes` in `tests/test_rpc_client_contract.py`:

```python
        ("jobs_plan", ({"mode": "mock"},), "POST", "/jobs/plan", {"mode": "mock"}),
        ("jobs_start", ({"mode": "mock"},), "POST", "/jobs/start", {"mode": "mock"}),
        ("jobs_get", ("job_1",), "GET", "/jobs/job_1", None),
        ("jobs_tasks", ("job_1",), "GET", "/jobs/job_1/tasks", None),
        ("jobs_resume", ("job_1", {"mode": "mock"}), "POST", "/jobs/job_1/resume", {"mode": "mock"}),
```

- [ ] **Step 2: Run client test to verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_rpc_client_contract.py::test_client_uses_v1_routes -q
```

Expected: fail because `RpcClient` has no job helper methods.

- [ ] **Step 3: Add job helper methods**

Add this section to `RpcClient` before deployed sweep extensions:

```python
    # Persistent jobs

    def jobs_plan(self, request: dict) -> dict:
        return self._post("/jobs/plan", request)

    def jobs_start(self, request: dict) -> dict:
        return self._post("/jobs/start", request)

    def jobs_get(self, job_id: str) -> dict:
        return self._get(f"/jobs/{quote(job_id, safe='')}")

    def jobs_tasks(self, job_id: str) -> dict:
        return self._get(f"/jobs/{quote(job_id, safe='')}/tasks")

    def jobs_resume(self, job_id: str, request: Optional[dict] = None) -> dict:
        return self._post(f"/jobs/{quote(job_id, safe='')}/resume", request or {})
```

- [ ] **Step 4: Run client tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rpc_client_contract.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/rpc_client/client.py tests/test_rpc_client_contract.py
git commit -m "feat: add rpc client job helpers"
```

## Task 5: Update docs and MCP knowledge prompt

**Files:**
- Modify: `README.md`
- Modify: `TECH_STACK.md`
- Modify: `SOP.md`
- Modify: `docs/RPC_API_V1.md`
- Modify: `src/knowledge/prompts/workflow.md`
- Modify: `DEV_LOG.md`

- [ ] **Step 1: Update API documentation**

In `docs/RPC_API_V1.md`, add rows for:

```markdown
| POST | `/jobs/plan` | 创建 planned job，落盘 task 清单但不执行 |
| POST | `/jobs/start` | 创建并执行 mock 或短 real geometry-smoke job |
| GET | `/jobs/<job_id>` | 读取 manifest/status/summary |
| GET | `/jobs/<job_id>/tasks` | 读取 task 摘要 |
| POST | `/jobs/<job_id>/resume` | 仅重试 pending/failed task |
```

Add this limitation note:

```markdown
- 第一版 `/jobs/*` 只执行 `mock` 和短 `real geometry-smoke`；完整 sweep、优化、取消和并发队列不在本版。
```

- [ ] **Step 2: Update workflow prompt**

In `src/knowledge/prompts/workflow.md`, replace the statement that job/task endpoints are unavailable with:

```markdown
Job/task endpoints are available for persistent `mock` and short `real geometry-smoke` workflows. Full sweep, optimization, cancellation, and quality reports are still planned work and must not be assumed available.
```

- [ ] **Step 3: Update project status docs**

Update `README.md`, `TECH_STACK.md`, and `SOP.md` so they state:

```markdown
- `/jobs/*` v1 第一版已实现：plan、start、status、tasks、resume。
- 当前真实执行仅限短 `geometry-smoke`，长 sweep 仍走旧 `5003` 或下一阶段接入。
```

- [ ] **Step 4: Add DEV_LOG entry**

Append to `DEV_LOG.md`:

```markdown
## 2026-06-18 - 持久 job/task 状态机第一版

- 目标：让新 `5004` API v1 具备落盘 job/task、幂等、审批和 resume 地基。
- 修改：
  - 新增 `src/job_store.py`，负责 `jobs/` 目录、manifest/status/task/summary、幂等索引和 resume 选择。
  - `rpc_server.py` 增加 `/jobs/plan`、`/jobs/start`、`/jobs/<job_id>`、`/jobs/<job_id>/tasks`、`/jobs/<job_id>/resume`。
  - `RpcClient` 增加 job helper 方法。
- 验证：
  - `.venv/bin/python -m pytest -q`：通过。
- 后续：
  - Windows 同步后用短 `real geometry-smoke` 验证 job 目录和 `.fsp` 产物。
```

- [ ] **Step 5: Run doc scan**

Run:

```bash
rg -n "job/task endpoints are still planned|/jobs/\\*.*尚未实现|尚未实现.*jobs" README.md TECH_STACK.md SOP.md docs src/knowledge/prompts
```

Expected: no output.

- [ ] **Step 6: Commit**

Run:

```bash
git add README.md TECH_STACK.md SOP.md docs/RPC_API_V1.md src/knowledge/prompts/workflow.md DEV_LOG.md
git commit -m "docs: document persistent job endpoints"
```

## Task 6: Full local verification and optional Windows smoke

**Files:**
- No new code files.
- Optional doc update: `DEV_LOG.md` if Windows smoke is run.

- [ ] **Step 1: Run full local test suite**

Run:

```bash
.venv/bin/python -m compileall rpc_server.py src scripts tests
.venv/bin/python -m pytest -q
git diff --check
```

Expected:

```text
65 or more tests passed
```

The exact number increases after adding job tests.

- [ ] **Step 2: Inspect git status**

Run:

```bash
git status --short
git log --oneline -6
```

Expected: only intentional doc updates remain, or clean after commits.

- [ ] **Step 3: Push to GitHub**

Run:

```bash
git push origin main
```

Expected: push succeeds.

- [ ] **Step 4: Sync Windows clone**

Run from Mac over SSH:

```bash
ssh -o BatchMode=yes 32482@192.168.31.26 'cd /f/lumerical-fdtd-auto-design/fdtd-auto-design && git pull --ff-only && git rev-parse --short HEAD'
```

Expected: Windows clone fast-forwards to the pushed commit.

- [ ] **Step 5: Ask for local Windows restart**

Ask the user to double-click:

```cmd
F:\lumerical-fdtd-auto-design\fdtd-auto-design\scripts\windows\restart_rpc.bat
```

Do not start the GUI service repeatedly through SSH.

- [ ] **Step 6: Verify real geometry-smoke job after restart**

Run:

```bash
ssh -o BatchMode=yes 32482@192.168.31.26 'cd /f/lumerical-fdtd-auto-design/fdtd-auto-design && curl -sS --max-time 5 http://127.0.0.1:5004/health && echo && curl -sS -X POST http://127.0.0.1:5004/jobs/start -H "Content-Type: application/json" -d "{\"mode\":\"real\",\"job_type\":\"geometry-smoke\",\"approval\":{\"approved\":true,\"approved_for\":\"real_run\"}}"'
```

Expected:

```json
{"ok": true}
```

The response must include a `job_id`, status state `succeeded`, and a model path under `jobs/<job_id>/models/task_0001.fsp`.

- [ ] **Step 7: Confirm final health**

Run:

```bash
ssh -o BatchMode=yes 32482@192.168.31.26 'curl -sS --max-time 5 http://127.0.0.1:5004/status'
```

Expected:

```json
{"connected": false, "model_file": null, "ok": true, "version": null}
```

- [ ] **Step 8: Record Windows verification if run**

Append to `DEV_LOG.md`:

```markdown
- Windows 验证：`/jobs/start` real geometry-smoke 通过，生成 `jobs/<job_id>/models/task_0001.fsp`，final status `connected=false`。
```

Then commit:

```bash
git add DEV_LOG.md
git commit -m "docs: record windows job smoke"
git push origin main
```

## Self-Review

- Spec coverage:
  - Persistent job directory: Task 1.
  - Task JSON state: Task 1 and Task 2.
  - Restart-readable status: Task 2 and Task 3 through disk-backed `get`.
  - Idempotency key: Task 2.
  - Real approval gate: Task 2 and Task 3.
  - Resume only pending and failed: Task 2 and Task 3.
  - RPC v1 envelope: Task 3.
  - Client helpers: Task 4.
  - Docs and knowledge prompt: Task 5.
  - Local and Windows verification: Task 6.
- Placeholder scan:
  - This plan contains no deferred implementation markers.
  - Every code-changing task includes explicit code or exact text to add.
- Type consistency:
  - `JobStore.plan`, `JobStore.start`, `JobStore.get`, `JobStore.list_tasks`, and `JobStore.resume` are introduced before RPC routes call them.
  - Error mapping uses `JobError.error_type`, `JobError.message`, `JobError.details`, and `JobError.status_code` consistently.
  - Client helpers map one-to-one to server routes.
