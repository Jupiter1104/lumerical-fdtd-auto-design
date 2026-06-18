# Native Metasurface Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the deployed Autosweep RPC bridge with native asynchronous metasurface sweep execution inside the new persistent job service, verify a real 2×2 run on port 5004, then change the new service default port to 5000.

**Architecture:** `src/sweep_job.py` owns sweep input normalization, sample-grid expansion, quality reports, CSV, and SVG evidence. A new `src/native_sweep.py` owns the four lumapi phases. `JobStore` owns all disk state and recovery, while `rpc_server.py` only validates requests, starts one background sweep thread, and protects the shared FDTD session.

**Tech Stack:** Python 3.9-compatible code, Flask API v1, raw Lumerical v242 lumapi, standard-library CSV/JSON/SVG generation, pytest fake-lumapi tests, Windows PowerShell service scripts.

---

## File Structure

- Modify `src/sweep_job.py`
  - Remove the HTTP bridge and `requests` dependency.
  - Normalize lists and point-count shorthand.
  - Expand a sweep into one task per sample.
  - Aggregate sample result JSON into CSV, quality report, and SVG evidence.
- Create `src/native_sweep.py`
  - Validate the template.
  - Execute Phase 1 generation, Phase 2 `runjobs`, Phase 3 extraction, and Phase 4 evidence generation.
- Modify `src/job_store.py`
  - Add async enqueue/execute primitives.
  - Add safe task updates and run-log appends.
  - Recover interrupted jobs at startup.
- Modify `rpc_server.py`
  - Remove the deployed sweep bridge.
  - Add a single native sweep coordinator and background thread.
  - Return HTTP 202 for real sweep start/resume.
  - Reject destructive session/model/geometry calls while a real sweep is running.
- Modify `tests/test_sweep_job.py`
  - Replace bridge tests with grid, aggregation, quality, and SVG tests.
- Create `tests/test_native_sweep.py`
  - Fake-lumapi phase ordering, result extraction, partial failure, and resume tests.
- Modify `tests/test_job_store.py`
  - Enqueue, task update, interrupted recovery, and resume selection tests.
- Modify `tests/test_rpc_server_jobs.py`
  - Async 202 behavior, one-active-sweep lock, and no old-RPC dependency.
- Create `scripts/windows/install_metasurface_template.ps1`
  - Copy a user-selected template into the new project and record its SHA-256.
- Modify `scripts/windows/manage_rpc.ps1`
  - Keep 5004 through real verification, then switch default to 5000 in the final task.
- Modify project docs and logs.

---

## Task 1: Replace the bridge model with sample-grid tasks

**Files:**
- Modify: `tests/test_sweep_job.py`
- Modify: `src/sweep_job.py`

- [ ] **Step 1: Replace deployed-bridge tests with failing grid tests**

Keep the existing artifact tests, remove `FakeResponse`, `FakeSession`, and both `run_deployed_sweep` tests. Add:

```python
from src.sweep_job import build_sweep_tasks, normalize_sweep_input


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
```

- [ ] **Step 2: Run the focused tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_sweep_job.py -q
```

Expected: failures because current code returns one high-level `metasurface-sweep` task and has no expanded lists.

- [ ] **Step 3: Remove HTTP bridge imports and functions**

In `src/sweep_job.py`, remove:

```python
import re
import time
from typing import Optional

import requests
```

Delete the complete `_parse_counts`, `_request_json`, and
`run_deployed_sweep` function definitions.

- [ ] **Step 4: Add deterministic list expansion**

Add:

```python
DEFAULT_RATIO_MIN = 0.2
DEFAULT_RATIO_MAX = 0.8
DEFAULT_PERIOD_MIN = 390e-9
DEFAULT_PERIOD_MAX = 540e-9


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
```

Update `normalize_sweep_input()` so the config always contains:

```python
ratio_pts = _as_positive_int(config.get("RATIO_PTS"), 2)
period_pts = _as_positive_int(config.get("PERIOD_PTS"), 2)
config["RATIO_LIST"] = _float_list(
    config.get("RATIO_LIST"),
    _linspace(DEFAULT_RATIO_MIN, DEFAULT_RATIO_MAX, ratio_pts),
)
config["PERIOD_LIST"] = _float_list(
    config.get("PERIOD_LIST"),
    _linspace(DEFAULT_PERIOD_MIN, DEFAULT_PERIOD_MAX, period_pts),
)
config["BASE_HEIGHT"] = float(config.get("BASE_HEIGHT", 700e-9))
config["BASE_PERIOD"] = float(config.get("BASE_PERIOD", 470e-9))
```

- [ ] **Step 5: Expand one task per sample**

Replace `build_sweep_tasks()` with:

```python
def build_sweep_tasks(request: dict) -> list:
    sweep_input = normalize_sweep_input(request)
    config = sweep_input["config"]
    tasks = []

    if config["SWEEP_Y_AXIS"] == "period":
        y_values = config["PERIOD_LIST"]
        for period in y_values:
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
        height_list = _float_list(
            config.get("HEIGHT_LIST"),
            [config["BASE_HEIGHT"]],
        )
        for height in height_list:
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
```

- [ ] **Step 6: Preserve job-level sweep metadata**

Modify `JobStore._normalize_request()` later in Task 2 to retain normalized sweep metadata. For this task, make `run_mock_sweep()` work with a sample task:

```python
def run_mock_sample(task: dict, job_dir: Path) -> dict:
    sample = task["input"]
    result_path = Path(job_dir) / "results" / f"{task['task_id']}.json"
    result = {
        "task_id": task["task_id"],
        "ratio": sample["ratio"],
        "height": sample["height"],
        "period": sample["period"],
        "transmission": 0.8,
        "phase_rad": 0.0,
        "synthetic": True,
    }
    _write_json(result_path, result)
    return {"result_file": str(result_path), **result}
```

Remove the old job-level `run_mock_sweep()` call path.

- [ ] **Step 7: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_sweep_job.py -q
```

Expected: all focused tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/sweep_job.py tests/test_sweep_job.py
git commit -m "refactor: expand sweep into sample tasks"
```

---

## Task 2: Add asynchronous JobStore primitives and interrupted recovery

**Files:**
- Modify: `tests/test_job_store.py`
- Modify: `src/job_store.py`

- [ ] **Step 1: Add failing enqueue and update tests**

Append:

```python
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
```

- [ ] **Step 2: Add failing interrupted recovery test**

```python
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
    store.update_task(job_id, "task_0001", state="succeeded", phase="complete")
    store.update_task(job_id, "task_0002", state="running", phase="solving")
    store._write_status(job_id, "running", "Job running.")

    recovered = store.recover_interrupted_jobs()

    assert recovered == [job_id]
    state = store.get(job_id)
    tasks = store.list_tasks(job_id)["tasks"]
    assert state["status"]["state"] == "partial"
    assert tasks[0]["state"] == "succeeded"
    assert tasks[1]["state"] == "failed"
    assert tasks[1]["error"]["type"] == "interrupted"
```

- [ ] **Step 3: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py -q
```

Expected: failures because `enqueue`, `update_task`, and `recover_interrupted_jobs` do not exist.

- [ ] **Step 4: Retain normalized sweep metadata**

Update `_normalize_request()` return value:

```python
normalized = {
    "mode": mode,
    "job_type": job_type,
    "idempotency_key": request.get("idempotency_key"),
    "approval": request.get("approval")
    or {"approved": False, "approved_for": None},
    "tasks": tasks,
}
if job_type == "metasurface-sweep":
    normalized["sweep"] = normalize_sweep_input(request)
return normalized
```

Import `normalize_sweep_input` and `run_mock_sample`.

- [ ] **Step 5: Add a shared approval check and enqueue**

Add:

```python
    def _require_real_approval(self, request: dict) -> None:
        if request["mode"] != "real":
            return
        approval = request["approval"]
        if (
            approval.get("approved") is not True
            or approval.get("approved_for") != "real_run"
        ):
            raise JobError(
                "approval_required",
                "Real jobs require explicit approval.",
                403,
            )

    def enqueue(self, request: dict) -> dict:
        normalized = self._normalize_request(request)
        self._require_real_approval(normalized)
        existing = self._find_idempotent_job(normalized)
        if existing:
            return existing
        job_id = self._new_job_id(normalized["job_type"])
        self._create_job(job_id, normalized, state="queued")
        self._remember_idempotency(normalized, job_id)
        return self.get(job_id)
```

Refactor `start()` to call the same approval helper.

- [ ] **Step 6: Add task phase at creation**

In `_create_job()` task JSON:

```python
"phase": "pending",
```

- [ ] **Step 7: Add task update and run log**

Add:

```python
    def update_task(
        self,
        job_id: str,
        task_id: str,
        *,
        state: Optional[str] = None,
        phase: Optional[str] = None,
        outputs: Optional[dict] = None,
        error: Optional[dict] = None,
    ) -> dict:
        task_path = self._job_dir(job_id) / "tasks" / f"{task_id}.json"
        if not task_path.exists():
            raise JobError("task_not_found", f"Task not found: {task_id}", 404)
        task = self._read_json(task_path)
        if state is not None:
            if state not in TASK_STATES:
                raise JobError("validation_error", f"Invalid task state: {state}", 400)
            task["state"] = state
        if phase is not None:
            task["phase"] = phase
        if outputs is not None:
            task["outputs"].update(outputs)
        task["error"] = error
        task["updated_at"] = utc_now()
        self._write_json(task_path, task)
        return task

    def append_log(self, job_id: str, message: str) -> None:
        with (self._job_dir(job_id) / "run.log").open(
            "a",
            encoding="utf-8",
        ) as output:
            output.write(f"{utc_now()} {message}\n")
```

- [ ] **Step 8: Add job execution/finalization methods**

Add:

```python
    def mark_running(self, job_id: str) -> dict:
        self.append_log(job_id, "Job running.")
        return self._write_status(job_id, "running", "Job running.")

    def finalize(self, job_id: str) -> dict:
        counts = self._task_counts(self._tasks(job_id))
        if counts["failed"]:
            state = "partial" if counts["succeeded"] else "failed"
        elif counts["pending"] or counts["running"]:
            state = "partial"
        else:
            state = "succeeded"
        self._write_status(job_id, state, f"Job {state}.")
        self._write_summary(job_id)
        self.append_log(job_id, f"Job {state}.")
        return self.get(job_id)
```

- [ ] **Step 9: Add interrupted recovery**

```python
    def recover_interrupted_jobs(self) -> list:
        recovered = []
        if not self.root.exists():
            return recovered
        for job_dir in sorted(self.root.glob("job_*")):
            status_path = job_dir / "status.json"
            if not status_path.exists():
                continue
            status = self._read_json(status_path)
            if status["state"] != "running":
                continue
            job_id = job_dir.name
            for task in self._tasks(job_id):
                if task["state"] == "running":
                    self.update_task(
                        job_id,
                        task["task_id"],
                        state="failed",
                        phase=task.get("phase", "interrupted"),
                        error={
                            "type": "interrupted",
                            "message": "RPC service stopped while task was running.",
                            "details": {},
                        },
                    )
            self._write_status(job_id, "partial", "Job interrupted; resume required.")
            self._write_summary(job_id)
            self.append_log(job_id, "Recovered interrupted job.")
            recovered.append(job_id)
        return recovered
```

- [ ] **Step 10: Make mock sample execution work**

In `_run_task()`:

```python
if executor is None and task["operation"] == "metasurface-sample":
    outputs = run_mock_sample(task, job_dir)
```

- [ ] **Step 11: Run tests**

```bash
.venv/bin/python -m pytest tests/test_job_store.py tests/test_sweep_job.py -q
```

Expected: all selected tests pass.

- [ ] **Step 12: Commit**

```bash
git add src/job_store.py src/sweep_job.py tests/test_job_store.py tests/test_sweep_job.py
git commit -m "feat: add async sample job persistence"
```

---

## Task 3: Add native lumapi Phase 1 and Phase 2 runner

**Files:**
- Create: `src/native_sweep.py`
- Create: `tests/test_native_sweep.py`

- [ ] **Step 1: Create fake session and failing Phase 1 ordering test**

Create `tests/test_native_sweep.py`:

```python
import json
from pathlib import Path

from src.job_store import JobStore
from src.native_sweep import NativeSweepRunner


class FakeFdtd:
    def __init__(self):
        self.calls = []

    def clearjobs(self):
        self.calls.append(("clearjobs",))

    def redrawoff(self):
        self.calls.append(("redrawoff",))

    def redrawon(self):
        self.calls.append(("redrawon",))

    def setresource(self, *args):
        self.calls.append(("setresource",) + args)

    def load(self, path):
        self.calls.append(("load", path))

    def switchtolayout(self):
        self.calls.append(("switchtolayout",))

    def setnamed(self, name, prop, value):
        self.calls.append(("setnamed", name, prop, value))

    def save(self, path):
        self.calls.append(("save", path))
        Path(path).write_bytes(b"fsp")

    def addjob(self, path):
        self.calls.append(("addjob", path))

    def runjobs(self):
        self.calls.append(("runjobs",))


class FakeSession:
    def __init__(self, fdtd):
        self.fdtd = fdtd
        self.is_connected = True

    def start(self, hide=True):
        self.is_connected = True
        return {"hide": hide}


def create_real_job(tmp_path):
    template = tmp_path / "templates" / "base_model.fsp"
    template.parent.mkdir(parents=True)
    template.write_bytes(b"template")
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    job = store.enqueue(
        {
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "template": str(template),
                "phases": [1, 2],
                "config": {
                    "RATIO_LIST": [0.2, 0.8],
                    "PERIOD_LIST": [390e-9],
                },
            },
            "approval": {"approved": True, "approved_for": "real_run"},
        }
    )
    return store, job


def test_native_runner_generates_models_then_runs_queue_once(tmp_path):
    store, job = create_real_job(tmp_path)
    fdtd = FakeFdtd()
    runner = NativeSweepRunner(FakeSession(fdtd), store)

    runner.run(job["job_id"])

    names = [call[0] for call in fdtd.calls]
    assert names.count("clearjobs") == 1
    assert names.count("load") == 2
    assert names.count("save") == 2
    assert names.count("addjob") == 2
    assert names.count("runjobs") == 1
    first_load = names.index("load")
    first_save = names.index("save")
    assert names.index("clearjobs") < first_load < first_save < names.index("runjobs")
    assert all(
        task["phase"] == "solving"
        for task in store.list_tasks(job["job_id"])["tasks"]
    )
```

- [ ] **Step 2: Run test to verify RED**

```bash
.venv/bin/python -m pytest tests/test_native_sweep.py -q
```

Expected: `ModuleNotFoundError: No module named 'src.native_sweep'`.

- [ ] **Step 3: Create template fingerprint helpers**

Create `src/native_sweep.py`:

```python
"""Native four-phase metasurface sweep execution."""

import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_model_path(job_dir: Path, task_id: str) -> Path:
    return Path(job_dir) / "models" / f"{task_id}.fsp"
```

- [ ] **Step 4: Implement Phase 1 and 2**

Add:

```python
class NativeSweepRunner:
    def __init__(self, session, store):
        self.session = session
        self.store = store

    def _fdtd(self, hide: bool):
        if not self.session.is_connected:
            self.session.start(hide=hide)
        return self.session.fdtd

    def run(self, job_id: str) -> dict:
        job = self.store.get(job_id)
        request = json.loads(
            (
                Path(job["job_dir"])
                / "inputs"
                / "request.json"
            ).read_text(encoding="utf-8")
        )
        sweep = request["sweep"]
        phases = sweep["phases"]
        template = Path(sweep["template"]).resolve()
        if not template.exists():
            raise FileNotFoundError(f"Template not found: {template}")

        job_dir = Path(job["job_dir"])
        fdtd = self._fdtd(bool(sweep.get("hide", True)))
        tasks = [
            task
            for task in self.store.list_tasks(job_id)["tasks"]
            if task["state"] in {"pending", "failed"}
        ]
        self.store.mark_running(job_id)

        if 1 in phases:
            self._phase_generate(job_id, job_dir, template, sweep, tasks, fdtd)
        if 2 in phases:
            self._phase_solve(job_id, tasks, fdtd)
        return self.store.get(job_id)

    def _phase_generate(
        self,
        job_id,
        job_dir,
        template,
        sweep,
        tasks,
        fdtd,
    ):
        config = sweep["config"]
        fdtd.clearjobs()
        fdtd.redrawoff()
        try:
            try:
                fdtd.setresource(
                    "FDTD",
                    1,
                    "processes",
                    config["FDTD_PROCESSES"],
                )
                fdtd.setresource(
                    "FDTD",
                    1,
                    "capacity",
                    config["FDTD_CAPACITY"],
                )
            except Exception as exc:
                self.store.append_log(
                    job_id,
                    f"Resource warning: {exc}",
                )

            for task in tasks:
                task_id = task["task_id"]
                sample = task["input"]
                model_path = sample_model_path(job_dir, task_id)
                self.store.update_task(
                    job_id,
                    task_id,
                    state="running",
                    phase="generating",
                    error=None,
                )
                fdtd.load(str(template))
                fdtd.switchtolayout()
                try:
                    fdtd.setnamed("FDTD", "express mode", 1)
                except Exception as exc:
                    self.store.append_log(
                        job_id,
                        f"{task_id} express-mode warning: {exc}",
                    )
                fdtd.setnamed("::model", "ratio", float(sample["ratio"]))
                fdtd.setnamed("::model", "height", float(sample["height"]))
                fdtd.setnamed("::model", "period", float(sample["period"]))
                fdtd.save(str(model_path))
                fdtd.addjob(str(model_path))
                self.store.update_task(
                    job_id,
                    task_id,
                    state="running",
                    phase="queued",
                    outputs={"model_file": str(model_path)},
                    error=None,
                )
        finally:
            fdtd.redrawon()

    def _phase_solve(self, job_id, tasks, fdtd):
        for task in tasks:
            self.store.update_task(
                job_id,
                task["task_id"],
                state="running",
                phase="solving",
                error=None,
            )
        fdtd.runjobs()
```

- [ ] **Step 5: Run focused tests**

```bash
.venv/bin/python -m pytest tests/test_native_sweep.py -q
```

Expected: Phase 1/2 test passes.

- [ ] **Step 6: Commit**

```bash
git add src/native_sweep.py tests/test_native_sweep.py
git commit -m "feat: add native sweep generation and solve phases"
```

---

## Task 4: Add Phase 3 extraction with per-sample failure isolation

**Files:**
- Modify: `tests/test_native_sweep.py`
- Modify: `src/native_sweep.py`

- [ ] **Step 1: Extend fake lumapi for extraction**

Add methods:

```python
    def runanalysis(self, name):
        self.calls.append(("runanalysis", name))

    def haveresult(self, name, result):
        self.calls.append(("haveresult", name, result))
        return True

    def getresult(self, name, result):
        self.calls.append(("getresult", name, result))
        if result == "T":
            return {"T": [0.75]}
        return {"S21_Gn": [1j]}
```

- [ ] **Step 2: Add failing extraction test**

```python
def test_phase_three_writes_scalar_result_per_sample(tmp_path):
    store, job = create_real_job(tmp_path)
    request_path = (
        Path(job["job_dir"])
        / "inputs"
        / "request.json"
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["sweep"]["phases"] = [1, 2, 3]
    request_path.write_text(json.dumps(request), encoding="utf-8")
    runner = NativeSweepRunner(FakeSession(FakeFdtd()), store)

    runner.run(job["job_id"])

    tasks = store.list_tasks(job["job_id"])["tasks"]
    assert all(task["state"] == "succeeded" for task in tasks)
    for task in tasks:
        result = json.loads(
            Path(task["outputs"]["result_file"]).read_text(encoding="utf-8")
        )
        assert result["transmission"] == 0.75
        assert result["phase_rad"] > 1.5
```

- [ ] **Step 3: Add failing partial sample test**

Add:

```python
class FailingSecondResultFdtd(FakeFdtd):
    def __init__(self):
        super().__init__()
        self.t_reads = 0

    def getresult(self, name, result):
        if result == "T":
            self.t_reads += 1
            if self.t_reads == 2:
                raise RuntimeError("bad sample")
        return super().getresult(name, result)


def test_phase_three_isolates_single_sample_failure(tmp_path):
    store, job = create_real_job(tmp_path)
    request_path = Path(job["job_dir"]) / "inputs" / "request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["sweep"]["phases"] = [1, 2, 3]
    request_path.write_text(json.dumps(request), encoding="utf-8")
    runner = NativeSweepRunner(
        FakeSession(FailingSecondResultFdtd()),
        store,
    )

    result = runner.run(job["job_id"])

    tasks = store.list_tasks(job["job_id"])["tasks"]
    assert [task["state"] for task in tasks] == ["succeeded", "failed"]
    assert tasks[1]["error"]["message"] == "bad sample"
    assert result["state"] == "partial"
```

- [ ] **Step 4: Run tests to verify RED**

```bash
.venv/bin/python -m pytest tests/test_native_sweep.py -q
```

Expected: extraction tests fail because Phase 3 is absent.

- [ ] **Step 5: Implement extraction**

Add imports:

```python
import cmath
```

Add to `run()`:

```python
if 3 in phases:
    self._phase_extract(job_id, job_dir, tasks, fdtd)
```

Implement:

```python
    def _phase_extract(self, job_id, job_dir, tasks, fdtd):
        for task in tasks:
            task_id = task["task_id"]
            model_file = self.store.list_tasks(job_id)["tasks"][
                int(task_id.split("_")[1]) - 1
            ]["outputs"]["model_file"]
            self.store.update_task(
                job_id,
                task_id,
                state="running",
                phase="extracting",
                error=None,
            )
            try:
                fdtd.load(model_file)
                fdtd.runanalysis("::model::s_params")
                if not fdtd.haveresult("::model::s_params", "T"):
                    raise RuntimeError("Missing T result.")
                if not fdtd.haveresult("::model::s_params", "S"):
                    raise RuntimeError("Missing S result.")
                transmission = float(
                    fdtd.getresult("::model::s_params", "T")["T"][0]
                )
                s21 = fdtd.getresult(
                    "::model::s_params",
                    "S",
                )["S21_Gn"][0]
                phase_rad = float(cmath.phase(s21))
                result_path = job_dir / "results" / f"{task_id}.json"
                result = {
                    "task_id": task_id,
                    **task["input"],
                    "transmission": transmission,
                    "phase_rad": phase_rad,
                }
                result_path.write_text(
                    json.dumps(result, indent=2) + "\n",
                    encoding="utf-8",
                )
                self.store.update_task(
                    job_id,
                    task_id,
                    state="succeeded",
                    phase="complete",
                    outputs={
                        "result_file": str(result_path),
                        "transmission": transmission,
                        "phase_rad": phase_rad,
                    },
                    error=None,
                )
            except Exception as exc:
                self.store.update_task(
                    job_id,
                    task_id,
                    state="failed",
                    phase="extracting",
                    error={
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                        "details": {},
                    },
                )
```

- [ ] **Step 6: Finalize job after runner phases**

At the end of `run()`:

```python
return self.store.finalize(job_id)
```

Wrap the run body so a pipeline-level exception marks still-running tasks failed and calls `finalize()` before re-raising.

- [ ] **Step 7: Run tests**

```bash
.venv/bin/python -m pytest tests/test_native_sweep.py tests/test_job_store.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/native_sweep.py tests/test_native_sweep.py
git commit -m "feat: extract native sweep sample results"
```

---

## Task 5: Add native aggregation, quality report, CSV, and SVG

**Files:**
- Modify: `tests/test_sweep_job.py`
- Modify: `src/sweep_job.py`
- Modify: `src/native_sweep.py`

- [ ] **Step 1: Add failing aggregation test**

```python
def test_write_job_artifacts_aggregates_results_and_svg(tmp_path):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    samples = [
        {
            "task_id": "task_0001",
            "ratio": 0.2,
            "height": 700e-9,
            "period": 390e-9,
            "transmission": 0.7,
            "phase_rad": 0.1,
        },
        {
            "task_id": "task_0002",
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
```

- [ ] **Step 2: Add warning/fail quality tests**

Test:

- one missing sample produces `warning`;
- zero valid samples produces `fail`;
- transmission above `1.05` produces at least `warning`;
- `requires_human_review` remains true.

- [ ] **Step 3: Run tests to verify RED**

```bash
.venv/bin/python -m pytest tests/test_sweep_job.py -q
```

Expected: failure because `write_job_artifacts` is absent.

- [ ] **Step 4: Implement CSV and SVG helpers**

Add standard-library imports:

```python
import csv
import math
from xml.sax.saxutils import escape
```

Implement:

```python
def _read_sample_results(job_dir: Path) -> list:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((Path(job_dir) / "results").glob("task_*.json"))
    ]


def _write_csv(path: Path, samples: list) -> None:
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
```

Implement `_write_heatmap_svg(path, samples, value_key, title)` using:

- unique sorted ratio values as columns;
- unique sorted period or height values as rows;
- 48×48 colored cells;
- text title and numeric values;
- no external plotting dependency.

- [ ] **Step 5: Implement job artifacts**

Add:

```python
def write_job_artifacts(
    job_dir: Path,
    *,
    job_id: str,
    expected_count: int,
    include_models: bool,
) -> dict:
```

It must write:

- `results/sweep_results.csv`
- `results/sweep_summary.json`
- `quality_report.json`
- `evidence/transmission_heatmap.svg`
- `evidence/phase_heatmap.svg`
- `evidence/index.json`

Quality conclusion:

```python
if not samples:
    conclusion = "fail"
elif len(samples) < expected_count:
    conclusion = "warning"
elif any(
    not math.isfinite(sample["transmission"])
    or sample["transmission"] < -0.05
    or sample["transmission"] > 1.05
    for sample in samples
):
    conclusion = "warning"
else:
    conclusion = "pass"
```

- [ ] **Step 6: Call aggregation as Phase 4**

In `NativeSweepRunner.run()`:

```python
if 4 in phases:
    write_job_artifacts(
        job_dir,
        job_id=job_id,
        expected_count=len(
            self.store.list_tasks(job_id)["tasks"]
        ),
        include_models=bool(sweep.get("include_models", False)),
    )
```

If Phase 4 is omitted, still write a minimal quality/evidence index after Phase 3, but omit SVG files and set a quality warning explaining that visualization was not requested.

- [ ] **Step 7: Run tests**

```bash
.venv/bin/python -m pytest tests/test_sweep_job.py tests/test_native_sweep.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/sweep_job.py src/native_sweep.py tests/test_sweep_job.py tests/test_native_sweep.py
git commit -m "feat: add native sweep quality and svg evidence"
```

---

## Task 6: Add async coordinator and Flask API behavior

**Files:**
- Modify: `tests/test_rpc_server_jobs.py`
- Modify: `tests/test_rpc_server_contract.py`
- Modify: `rpc_server.py`

- [ ] **Step 1: Replace bridge route tests with async tests**

Remove tests that monkeypatch `run_deployed_sweep` or assert port 5005.

Add:

```python
def test_real_sweep_start_returns_202_before_runner_finishes(
    server_module,
    fake_session,
    tmp_path,
):
    started = []
    release = threading.Event()

    class BlockingRunner:
        def run(self, job_id):
            started.append(job_id)
            release.wait(timeout=2)

    app = server_module.create_app(
        fake_session,
        job_store=server_module.JobStore(tmp_path / "jobs"),
        sweep_runner=BlockingRunner(),
    )
    client = app.test_client()

    response = client.post(
        "/jobs/start",
        json={
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "template": str(tmp_path / "base_model.fsp"),
                "config": {
                    "RATIO_LIST": [0.2],
                    "PERIOD_LIST": [390e-9],
                },
            },
            "approval": {"approved": True, "approved_for": "real_run"},
        },
    )

    assert response.status_code == 202
    assert response.get_json()["state"] == "queued"
    assert started
    release.set()
```

Create the template file before posting.

- [ ] **Step 2: Add one-active-sweep test**

Start a blocking sweep, then post a second approved real sweep. Assert HTTP 409 and `error.type == "sweep_already_running"`.

- [ ] **Step 3: Add destructive endpoint protection test**

While the blocking runner is active, assert `/model/load`, `/geometry/rectangle`, and `/session/close` return 409 `sweep_running`.

- [ ] **Step 4: Run tests to verify RED**

```bash
.venv/bin/python -m pytest tests/test_rpc_server_jobs.py tests/test_rpc_server_contract.py -q
```

Expected: failures because `create_app` has no `sweep_runner`, real start is synchronous, and routes are not protected.

- [ ] **Step 5: Remove bridge imports and executor**

In `rpc_server.py`, remove the `run_deployed_sweep` import and the complete
`_metasurface_sweep_executor` function.

- [ ] **Step 6: Add `SweepCoordinator`**

Import:

```python
from src.native_sweep import NativeSweepRunner
```

Add:

```python
class SweepCoordinator:
    def __init__(self, runner):
        self.runner = runner
        self._lock = threading.Lock()
        self._active_job_id = None

    @property
    def is_running(self):
        with self._lock:
            return self._active_job_id is not None

    def start(self, job_id: str):
        with self._lock:
            if self._active_job_id is not None:
                raise RpcError(
                    "sweep_already_running",
                    f"Sweep {self._active_job_id} is already running.",
                    409,
                )
            self._active_job_id = job_id

        def worker():
            try:
                self.runner.run(job_id)
            finally:
                with self._lock:
                    self._active_job_id = None

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
```

- [ ] **Step 7: Inject or construct native runner**

Change signature:

```python
def create_app(
    session_manager=None,
    job_store=None,
    sweep_runner=None,
) -> Flask:
```

Inside:

```python
jobs = job_store or JobStore()
jobs.recover_interrupted_jobs()
runner = sweep_runner or NativeSweepRunner(session, jobs)
sweeps = SweepCoordinator(runner)
```

- [ ] **Step 8: Validate template before enqueue**

Add:

```python
def _validate_sweep_template(data: dict):
    sweep = data.get("sweep") or {}
    template = Path(
        sweep.get("template")
        or "templates/metasurface/base_model.fsp"
    )
    if not template.exists():
        raise RpcError(
            "template_not_found",
            f"Sweep template not found: {template}",
            400,
            {"template": str(template)},
        )
```

- [ ] **Step 9: Make real sweep start asynchronous**

In `/jobs/start`:

```python
if (
    data.get("mode") == "real"
    and data.get("job_type") == "metasurface-sweep"
):
    _validate_sweep_template(data)
    if sweeps.is_running:
        raise RpcError(
            "sweep_already_running",
            "A real sweep is already running.",
            409,
        )
    job = jobs.enqueue(data)
    sweeps.start(job["job_id"])
    return _success(job, status_code=202)
```

Keep current synchronous behavior for mock and geometry-smoke.

- [ ] **Step 10: Make resume asynchronous**

For a real metasurface job:

1. load manifest/request;
2. verify template fingerprint unchanged;
3. verify selected pending/failed tasks exist;
4. call `sweeps.start(job_id)`;
5. return HTTP 202 with selected task IDs.

- [ ] **Step 11: Protect destructive routes**

Add:

```python
def _reject_during_sweep():
    if sweeps.is_running:
        raise RpcError(
            "sweep_running",
            "Operation is unavailable while a real sweep is running.",
            409,
        )
```

Call it at the start of:

- session start/close;
- model save/load;
- debug eval/setv;
- simulation run;
- geometry add routes.

Read-only health/status/jobs GET remain available.

- [ ] **Step 12: Run tests**

```bash
.venv/bin/python -m pytest tests/test_rpc_server_jobs.py tests/test_rpc_server_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 13: Commit**

```bash
git add rpc_server.py tests/test_rpc_server_jobs.py tests/test_rpc_server_contract.py
git commit -m "feat: run native sweeps asynchronously"
```

---

## Task 7: Add template installation and fingerprinting

**Files:**
- Create: `scripts/windows/install_metasurface_template.ps1`
- Create: `scripts/windows/install_metasurface_template.bat`
- Create: `templates/metasurface/README.md`
- Modify: `src/native_sweep.py`
- Modify: `src/job_store.py`
- Test: `tests/test_native_sweep.py`

- [ ] **Step 1: Add failing fingerprint test**

```python
def test_runner_records_template_fingerprint(tmp_path):
    store, job = create_real_job(tmp_path)
    runner = NativeSweepRunner(FakeSession(FakeFdtd()), store)

    runner.run(job["job_id"])

    manifest = store.get(job["job_id"])["manifest"]
    assert manifest["template"]["sha256"]
    assert manifest["template"]["size_bytes"] > 0
```

- [ ] **Step 2: Add manifest metadata update**

Add `JobStore.update_manifest(job_id, values)` that merges top-level keys atomically.

At runner start:

```python
stat = template.stat()
self.store.update_manifest(
    job_id,
    {
        "template": {
            "path": str(template),
            "sha256": file_sha256(template),
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
        }
    },
)
```

- [ ] **Step 3: Create PowerShell installer**

Create:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$Source
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$DestinationDir = Join-Path $ProjectRoot "templates\metasurface"
$Destination = Join-Path $DestinationDir "base_model.fsp"

if (-not (Test-Path -LiteralPath $Source)) {
    throw "Template not found: $Source"
}

New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
Copy-Item -LiteralPath $Source -Destination $Destination -Force
$hash = Get-FileHash -Algorithm SHA256 -LiteralPath $Destination
$item = Get-Item -LiteralPath $Destination

Write-Host "[OK] Template installed"
Write-Host "Path:   $Destination"
Write-Host "Bytes:  $($item.Length)"
Write-Host "SHA256: $($hash.Hash)"
```

Create the `.bat` wrapper:

```bat
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_metasurface_template.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
```

- [ ] **Step 4: Document the template**

`templates/metasurface/README.md` states the required objects/properties, installation command, and that `.fsp` is intentionally ignored by Git.

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python -m pytest tests/test_native_sweep.py tests/test_job_store.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/windows/install_metasurface_template.ps1 scripts/windows/install_metasurface_template.bat templates/metasurface/README.md src/native_sweep.py src/job_store.py tests/test_native_sweep.py
git commit -m "feat: add controlled metasurface template install"
```

---

## Task 8: Update docs and remove bridge claims

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `REQUIREMENTS.md`
- Modify: `TECH_STACK.md`
- Modify: `SOP.md`
- Modify: `PITFALLS.md`
- Modify: `docs/RPC_API_V1.md`
- Modify: `src/knowledge/prompts/workflow.md`
- Modify: `DEV_LOG.md`

- [ ] **Step 1: Remove current-runtime bridge language**

Run:

```bash
rg -n "5005|FDTD_SWEEP_RPC_URL|run_deployed_sweep|bridge|旧 Autosweep" AGENTS.md README.md REQUIREMENTS.md TECH_STACK.md SOP.md PITFALLS.md docs/RPC_API_V1.md src rpc_server.py scripts
```

Current operational docs and code must not instruct the new project to call the old service. Historical DEV_LOG entries may retain factual history.

- [ ] **Step 2: Document native architecture**

Update status:

```md
- 当前代码状态：新 `5004` API v1 原生执行 metasurface sweep；每个参数点是独立持久 task，real start 异步返回 job ID，结果生成 CSV、质量报告和 SVG evidence。旧 Autosweep 不再是运行依赖。
```

- [ ] **Step 3: Document template installation**

Add to SOP:

```cmd
scripts\windows\install_metasurface_template.bat "E:\CLAUDE_workspace\Lumerical_autosweep\base_model.fsp"
```

Clarify this is a one-time data migration, not a runtime dependency.

- [ ] **Step 4: Document resume and interruption**

State:

- service restart converts running work to interrupted/partial;
- user explicitly resumes;
- completed samples are not recomputed;
- changed template fingerprint requires a new job.

- [ ] **Step 5: Record prior failed bridge run**

In `DEV_LOG.md`, record:

- failed job `job_20260618_202255_metasurface_sweep`;
- old lumapi stale-session root cause;
- architectural decision to replace bridge with native execution;
- no claim that real native sweep has passed yet.

- [ ] **Step 6: Check docs**

```bash
git diff --check
rg -n "真实执行通过.*5005|桥接旧|FDTD_SWEEP_RPC_URL" AGENTS.md README.md REQUIREMENTS.md TECH_STACK.md SOP.md docs/RPC_API_V1.md src rpc_server.py scripts || true
```

Expected: no operational bridge claims.

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md README.md REQUIREMENTS.md TECH_STACK.md SOP.md PITFALLS.md docs/RPC_API_V1.md src/knowledge/prompts/workflow.md DEV_LOG.md
git commit -m "docs: document native async sweep workflow"
```

---

## Task 9: Full local verification and Windows sync

**Files:**
- All implementation files.

- [ ] **Step 1: Compile**

```bash
.venv/bin/python -m compileall rpc_server.py src scripts tests
```

Expected: exit 0.

- [ ] **Step 2: Run full tests**

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass; count exceeds the previous 92.

- [ ] **Step 3: Verify no runtime bridge dependency**

```bash
rg -n "requests|run_deployed_sweep|FDTD_SWEEP_RPC_URL|127.0.0.1:5005" src/sweep_job.py src/native_sweep.py rpc_server.py
```

Expected: no output.

- [ ] **Step 4: Verify repository cleanliness**

```bash
git diff --check
git status --short
```

- [ ] **Step 5: Push and sync Windows**

```bash
git push origin main
ssh -o BatchMode=yes 32482@192.168.31.26 'cd /f/lumerical-fdtd-auto-design/fdtd-auto-design && git pull --ff-only && git rev-parse --short HEAD'
```

- [ ] **Step 6: Install the template**

Ask the user to run:

```cmd
F:\lumerical-fdtd-auto-design\fdtd-auto-design\scripts\windows\install_metasurface_template.bat "E:\CLAUDE_workspace\Lumerical_autosweep\base_model.fsp"
```

- [ ] **Step 7: Restart 5004 locally**

Ask the user to double-click:

```text
F:\lumerical-fdtd-auto-design\fdtd-auto-design\scripts\windows\restart_rpc.bat
```

- [ ] **Step 8: Verify health and mock 2×2**

Use `/jobs/start` mock and verify four sample tasks, quality report, CSV/evidence paths, and final job success.

---

## Task 10: Real 2×2 native sweep verification on 5004

**Files:**
- No code changes unless verification reveals a reproducible bug.

- [ ] **Step 1: Present approval summary**

Report:

- 4 samples;
- phases `[1,2,3,4]`;
- template path and fingerprint;
- headless mode;
- processes/capacity 1;
- new job output directory;
- license and overwrite risk;
- no old RPC dependency.

Wait for explicit approval.

- [ ] **Step 2: Start the real job**

POST to `http://127.0.0.1:5004/jobs/start`.

Expected: HTTP 202 within 2 seconds with `queued` job and 4 tasks.

- [ ] **Step 3: Poll disk-backed status**

Poll:

- `GET /jobs/<job_id>`
- `GET /jobs/<job_id>/tasks`

Do not submit another real run while state is queued/running.

- [ ] **Step 4: Verify artifacts**

Verify:

- 4 sample tasks succeeded;
- 4 model files exist;
- 4 result JSON files exist;
- `results/sweep_results.csv`;
- `results/sweep_summary.json`;
- `quality_report.json`;
- two SVG heatmaps;
- `evidence/index.json`;
- default evidence excludes model contents.

- [ ] **Step 5: Record exact evidence**

Update `DEV_LOG.md` with job ID, duration, valid/failed counts, quality conclusion, template SHA-256, and artifact paths. Commit and push.

---

## Task 11: Switch the new service default port to 5000

**Files:**
- Modify: `rpc_server.py`
- Modify: `scripts/windows/manage_rpc.ps1`
- Modify: `scripts/v1_smoke_test.py`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `TECH_STACK.md`
- Modify: `SOP.md`
- Modify: `docs/RPC_API_V1.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Modify: `DEV_LOG.md`

This task is allowed only after Task 10 passes.

- [ ] **Step 1: Add/update default-port tests**

Create `tests/test_default_ports.py`:

```python
import re
from pathlib import Path


def test_server_and_windows_manager_default_to_port_5000():
    server = Path("rpc_server.py").read_text(encoding="utf-8")
    manager = Path("scripts/windows/manage_rpc.ps1").read_text(
        encoding="utf-8"
    )

    assert "default=5000" in server
    assert "help=\"Server port (default: 5000)\"" in server
    assert re.search(
        r"\$Port\s*=\s*if\s*\(\$env:FDTD_RPC_PORT\).*?"
        r"else\s*\{\s*5000\s*\}",
        manager,
        re.DOTALL,
    )
```

- [ ] **Step 2: Verify the test fails while defaults remain 5004/5003**

Run:

```bash
.venv/bin/python -m pytest tests/test_default_ports.py -q
```

Expected: fail because `rpc_server.py` still defaults to 5003 and the Windows
manager still defaults to 5004.

- [ ] **Step 3: Change defaults**

- `rpc_server.py --port` default: `5000`.
- `manage_rpc.ps1` fallback port: `5000`.
- smoke defaults and current operational docs: `5000`.
- environment override `FDTD_RPC_PORT` remains supported.

- [ ] **Step 4: Run full local verification**

```bash
.venv/bin/python -m compileall rpc_server.py src scripts tests
.venv/bin/python -m pytest -q
git diff --check
```

- [ ] **Step 5: Commit, push, sync**

```bash
git add rpc_server.py scripts/windows/manage_rpc.ps1 scripts/v1_smoke_test.py AGENTS.md README.md TECH_STACK.md SOP.md docs/RPC_API_V1.md docs/WINDOWS_RUNBOOK.md DEV_LOG.md tests
git commit -m "feat: promote native rpc service to port 5000"
git push origin main
```

- [ ] **Step 6: Restart on 5000**

Ask the user to double-click `restart_rpc.bat`.

- [ ] **Step 7: Final smoke**

Verify:

- `http://127.0.0.1:5000/health`;
- mock 2×2 job;
- no listener is required on 5004;
- do not repeat a real sweep without a new approval.

---

## Self-Review Checklist

- Native execution: Tasks 3–6.
- Sample-level persistent tasks: Tasks 1–4.
- Async HTTP 202: Task 6.
- Interrupted recovery and resume: Tasks 2 and 6.
- Template migration/fingerprint: Task 7.
- CSV/quality/SVG evidence: Task 5.
- Old RPC removed from runtime: Tasks 1, 6, 8, 9.
- Real 2×2 on 5004: Task 10.
- Default port 5000 only after real verification: Task 11.
- No unresolved fill-in-later implementation steps.
- Signatures used consistently:
  - `build_sweep_tasks(request) -> list`
  - `JobStore.enqueue(request) -> dict`
  - `JobStore.update_task(...) -> dict`
  - `JobStore.finalize(job_id) -> dict`
  - `NativeSweepRunner.run(job_id) -> dict`
  - `write_job_artifacts(...) -> dict`
