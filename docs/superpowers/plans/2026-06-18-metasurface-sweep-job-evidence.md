# Metasurface Sweep Job Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `metasurface-sweep` to the persistent `/jobs/*` state machine, bridge real execution to the deployed `5003` sweep baseline, and write `quality_report.json` plus evidence-first indexes.

**Architecture:** Keep `JobStore` as the persistence owner. Add a focused `src/sweep_job.py` module for sweep request normalization, mock artifacts, deployed `5003` bridge execution, quality report generation, and evidence indexing. `rpc_server.py` only selects the correct executor; it does not contain sweep business logic.

**Tech Stack:** Python 3.9-compatible code, Flask API v1, `requests` for the local `5003` bridge, pytest offline tests, Windows v242 raw lumapi remains isolated behind the existing deployed sweep service.

---

## File Structure

- Modify `src/job_store.py`
  - Allow `job_type="metasurface-sweep"`.
  - Build default sweep tasks from request payload.
  - Include `quality_report` and `evidence` in `summary.json` when files exist.
- Create `src/sweep_job.py`
  - Normalize sweep request fields.
  - Build one high-level sweep task.
  - Run mock sweep and write artifacts.
  - Bridge real sweep to deployed `5003` via HTTP.
  - Generate `quality_report.json`, `results/sweep_summary.json`, and `evidence/index.json`.
- Modify `rpc_server.py`
  - Select `geometry-smoke`, mock sweep, or real deployed sweep executor.
  - Read deployed sweep URL from `FDTD_SWEEP_RPC_URL`, default `http://127.0.0.1:5003`.
- Modify `requirements-dev.txt`
  - Ensure `requests` remains available for tests and bridge code.
- Modify tests:
  - `tests/test_sweep_job.py`
  - `tests/test_job_store.py`
  - `tests/test_rpc_server_jobs.py`
  - `tests/test_rpc_client_contract.py` only if route behavior needs extra coverage.
- Modify docs:
  - `README.md`
  - `TECH_STACK.md`
  - `SOP.md`
  - `docs/RPC_API_V1.md`
  - `DEV_LOG.md`

---

## Task 1: Add sweep artifact module tests

**Files:**
- Create: `tests/test_sweep_job.py`
- Create later: `src/sweep_job.py`

- [ ] **Step 1: Write failing tests for mock artifacts and quality reports**

Create `tests/test_sweep_job.py`:

```python
import json
from pathlib import Path

from src.sweep_job import (
    build_sweep_tasks,
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
```

- [ ] **Step 2: Run the new test to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_sweep_job.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'src.sweep_job'`.

---

## Task 2: Implement sweep artifact module

**Files:**
- Create: `src/sweep_job.py`
- Test: `tests/test_sweep_job.py`

- [ ] **Step 1: Create `src/sweep_job.py` with mock and artifact logic**

Create `src/sweep_job.py`:

```python
"""Metasurface sweep job helpers.

This module is pure Python and safe to import on Mac. Real solver work is
delegated to the already-deployed sweep RPC service on Windows port 5003.
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests


DEFAULT_SWEEP_CONFIG = {
    "SWEEP_Y_AXIS": "period",
    "RATIO_PTS": 2,
    "PERIOD_PTS": 2,
    "FDTD_PROCESSES": 1,
    "FDTD_CAPACITY": 1,
}
DEFAULT_PHASES = [1, 2, 3]


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


def normalize_sweep_input(request: dict) -> dict:
    sweep = request.get("sweep") or {}
    config = dict(DEFAULT_SWEEP_CONFIG)
    config.update(sweep.get("config") or {})
    config["RATIO_PTS"] = _as_positive_int(config.get("RATIO_PTS"), 2)
    config["PERIOD_PTS"] = _as_positive_int(config.get("PERIOD_PTS"), 2)
    config["FDTD_PROCESSES"] = _as_positive_int(config.get("FDTD_PROCESSES"), 1) or 1
    config["FDTD_CAPACITY"] = _as_positive_int(config.get("FDTD_CAPACITY"), 1) or 1
    config["SWEEP_Y_AXIS"] = str(config.get("SWEEP_Y_AXIS") or "period")

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
        "template": str(sweep.get("template") or "base_model.fsp"),
        "include_models": bool(sweep.get("include_models", False)),
    }


def build_sweep_tasks(request: dict) -> list:
    return [
        {
            "operation": "metasurface-sweep",
            "input": normalize_sweep_input(request),
        }
    ]


def _sample_counts(config: dict) -> dict:
    ratio_pts = _as_positive_int(config.get("RATIO_PTS"), 2)
    period_pts = _as_positive_int(config.get("PERIOD_PTS"), 2)
    total = ratio_pts * period_pts
    return {"ratio_pts": ratio_pts, "period_pts": period_pts, "total": total}


def run_mock_sweep(task: dict, job_dir: Path) -> dict:
    sweep_input = task.get("input", {})
    counts = _sample_counts(sweep_input.get("config", {}))
    total = counts["total"]
    run_result = {
        "solver_status": "done",
        "message": f"{total}/{total} valid, 0 missing",
        "valid_count": total,
        "missing_count": 0,
        "total_count": total,
        "phases": sweep_input.get("phases", DEFAULT_PHASES),
        "result_files": ["results/sweep_summary.json"],
        "figure_files": ["figures/mock_transmission_heatmap.png"]
        if 4 in sweep_input.get("phases", [])
        else [],
        "model_files": [],
        "remote_task_id": None,
    }
    return write_sweep_artifacts(job_dir, task, run_result)


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
        "summary_files": ["summary.json", "quality_report.json", "results/sweep_summary.json"],
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


def _parse_counts(message: str) -> dict:
    match = re.search(r"(\d+)\s*/\s*(\d+)\s+valid.*?(\d+)\s+missing", message or "")
    if not match:
        return {"valid_count": 0, "total_count": 0, "missing_count": 0}
    return {
        "valid_count": int(match.group(1)),
        "total_count": int(match.group(2)),
        "missing_count": int(match.group(3)),
    }


def _request_json(session, method: str, url: str, **kwargs) -> dict:
    response = session.request(method, url, **kwargs)
    payload = response.json()
    if response.status_code >= 400 or payload.get("ok") is False:
        raise RuntimeError(f"{method} {url} failed: {payload}")
    return payload


def run_deployed_sweep(
    task: dict,
    job_dir: Path,
    base_url: str,
    poll_interval: float = 10.0,
    timeout_seconds: float = 3600.0,
    session: Optional[requests.Session] = None,
) -> dict:
    http = session or requests.Session()
    base = base_url.rstrip("/")
    sweep_input = task.get("input", {})

    health = _request_json(http, "GET", f"{base}/health", timeout=30)
    if not (health.get("fdtd_connected") and health.get("matlab_connected")):
        _request_json(
            http,
            "POST",
            f"{base}/session/start",
            json={"hide": bool(sweep_input.get("hide", True))},
            timeout=120,
        )

    _request_json(
        http,
        "POST",
        f"{base}/sweep/config",
        json=sweep_input.get("config", {}),
        timeout=60,
    )
    started = _request_json(
        http,
        "POST",
        f"{base}/sweep/run",
        json={"phases": sweep_input.get("phases", DEFAULT_PHASES)},
        timeout=120,
    )
    remote_task_id = started.get("task_id")
    deadline = time.time() + timeout_seconds
    final_task = {}

    while time.time() < deadline:
        status = _request_json(
            http,
            "GET",
            f"{base}/sweep/status",
            params={"task_id": remote_task_id},
            timeout=60,
        )
        final_task = status.get("task", {})
        if final_task.get("status") in {"done", "error"}:
            break
        time.sleep(poll_interval)
    else:
        raise RuntimeError(f"Sweep task {remote_task_id} timed out.")

    result_listing = _request_json(http, "GET", f"{base}/results", timeout=60)
    files = result_listing.get("files", {})
    message = final_task.get("message", "")
    counts = _parse_counts(message)
    run_result = {
        "solver_status": final_task.get("status", "unknown"),
        "message": message,
        "remote_task_id": remote_task_id,
        "phases": sweep_input.get("phases", DEFAULT_PHASES),
        "result_files": [f"results/{name}" for name in files.get("results", [])],
        "figure_files": [f"figures/{name}" for name in files.get("figures", [])],
        "model_files": [f"models/{name}" for name in files.get("models", [])],
        **counts,
    }
    return write_sweep_artifacts(job_dir, task, run_result)
```

- [ ] **Step 2: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_sweep_job.py -q
```

Expected: `3 passed`.

- [ ] **Step 3: Commit**

```bash
git add src/sweep_job.py tests/test_sweep_job.py
git commit -m "feat: add sweep job evidence artifacts"
```

---

## Task 3: Extend `JobStore` for `metasurface-sweep`

**Files:**
- Modify: `src/job_store.py`
- Modify: `tests/test_job_store.py`

- [ ] **Step 1: Add failing `JobStore` tests**

Append to `tests/test_job_store.py`:

```python
def test_plan_accepts_metasurface_sweep_and_creates_default_task(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    result = store.plan({"mode": "mock", "job_type": "metasurface-sweep"})

    job_dir = tmp_path / "jobs" / result["job_id"]
    task = read_json(job_dir / "tasks" / "task_0001.json")
    manifest = read_json(job_dir / "manifest.json")

    assert result["state"] == "planned"
    assert manifest["job_type"] == "metasurface-sweep"
    assert task["operation"] == "metasurface-sweep"
    assert task["input"]["config"]["RATIO_PTS"] == 2
    assert task["input"]["phases"] == [1, 2, 3]


def test_summary_includes_quality_and_evidence_when_present(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")
    result = store.start({"mode": "mock", "job_type": "metasurface-sweep"})

    summary = read_json(tmp_path / "jobs" / result["job_id"] / "summary.json")

    assert summary["quality_report"]["conclusion"] == "pass"
    assert summary["quality_report"]["requires_human_review"] is True
    assert summary["evidence"]["download_policy"]["default_payload"] == "evidence-only"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py -q
```

Expected: fail because `job_type must be geometry-smoke in v1`.

- [ ] **Step 3: Update `JobStore` imports and supported job types**

Modify the top of `src/job_store.py`:

```python
from src.sweep_job import build_sweep_tasks, run_mock_sweep


SUPPORTED_JOB_TYPES = {"geometry-smoke", "metasurface-sweep"}
```

- [ ] **Step 4: Update `_normalize_request` to build sweep tasks**

Replace the `job_type` validation and `tasks` selection in `_normalize_request` with:

```python
        if job_type not in SUPPORTED_JOB_TYPES:
            raise JobError(
                "validation_error",
                f"job_type must be one of {sorted(SUPPORTED_JOB_TYPES)}.",
                400,
            )

        if request.get("tasks"):
            tasks = request["tasks"]
        elif job_type == "metasurface-sweep":
            tasks = build_sweep_tasks(request)
        else:
            tasks = [
                {
                    "operation": "geometry-smoke",
                    "input": {"hide": bool(request.get("hide", False))},
                }
            ]
```

- [ ] **Step 5: Use mock sweep executor by default for mock metasurface jobs**

Modify `_run_task` in `src/job_store.py` so the `executor is None` branch becomes:

```python
            if executor is None and task["operation"] == "metasurface-sweep":
                outputs = run_mock_sweep(task, job_dir)
            elif executor is None:
                outputs = {"mode": task["mode"], "operation": task["operation"]}
            else:
                outputs = executor(task, job_dir)
```

- [ ] **Step 6: Include quality and evidence in summary**

Replace `_write_summary` in `src/job_store.py` with:

```python
    def _write_summary(self, job_id: str) -> dict:
        job_dir = self._job_dir(job_id)
        tasks = self._tasks(job_id)
        summary = {
            "job_id": job_id,
            "task_counts": self._task_counts(tasks),
            "results": [
                task["outputs"]
                for task in tasks
                if task["state"] == "succeeded"
            ],
        }
        quality_path = job_dir / "quality_report.json"
        evidence_path = job_dir / "evidence" / "index.json"
        if quality_path.exists():
            summary["quality_report"] = self._read_json(quality_path)
        if evidence_path.exists():
            summary["evidence"] = self._read_json(evidence_path)
        self._write_json(job_dir / "summary.json", summary)
        return summary
```

- [ ] **Step 7: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py tests/test_sweep_job.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/job_store.py tests/test_job_store.py
git commit -m "feat: support metasurface sweep jobs"
```

---

## Task 4: Wire Flask `/jobs/*` to sweep executors

**Files:**
- Modify: `rpc_server.py`
- Modify: `tests/test_rpc_server_jobs.py`

- [ ] **Step 1: Add failing Flask route tests**

Append to `tests/test_rpc_server_jobs.py`:

```python
def test_jobs_start_mock_metasurface_sweep_writes_quality_and_evidence(client):
    response = client.post(
        "/jobs/start",
        json={"mode": "mock", "job_type": "metasurface-sweep"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"]["state"] == "succeeded"
    assert payload["summary"]["quality_report"]["conclusion"] == "pass"
    assert payload["summary"]["evidence"]["download_policy"]["default_payload"] == "evidence-only"


def test_jobs_start_real_metasurface_sweep_requires_approval(client):
    response = client.post(
        "/jobs/start",
        json={"mode": "real", "job_type": "metasurface-sweep"},
    )
    payload = response.get_json()

    assert response.status_code == 403
    assert payload["ok"] is False
    assert payload["error"]["type"] == "approval_required"
```

- [ ] **Step 2: Run route tests to verify RED or partial failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_rpc_server_jobs.py -q
```

Expected before Task 3 implementation: failure on unsupported job type. If Task 3 is complete, the mock test may already pass and the approval test should pass through existing approval logic.

- [ ] **Step 3: Add real sweep executor selection**

Modify `rpc_server.py` imports:

```python
from src.sweep_job import run_deployed_sweep
```

Add helper after `_geometry_smoke_executor`:

```python
def _metasurface_sweep_executor(base_url: str):
    def run(task: dict, job_dir: Path) -> dict:
        return run_deployed_sweep(task, job_dir, base_url=base_url)

    return run


def _job_executor(data: dict, session: SessionManager):
    if data.get("mode") != "real":
        return None
    if data.get("job_type") == "geometry-smoke":
        return _geometry_smoke_executor(session)
    if data.get("job_type") == "metasurface-sweep":
        return _metasurface_sweep_executor(
            os.environ.get("FDTD_SWEEP_RPC_URL", "http://127.0.0.1:5003")
        )
    return None
```

Replace executor selection in `/jobs/start` and `/jobs/<job_id>/resume`:

```python
        executor = _job_executor(data, session)
```

- [ ] **Step 4: Run route tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_rpc_server_jobs.py tests/test_rpc_server_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add rpc_server.py tests/test_rpc_server_jobs.py
git commit -m "feat: wire sweep jobs to rpc server"
```

---

## Task 5: Add deployed sweep bridge tests without Windows

**Files:**
- Modify: `tests/test_sweep_job.py`
- Modify: `src/sweep_job.py`

- [ ] **Step 1: Add a fake HTTP session test for `run_deployed_sweep`**

Append to `tests/test_sweep_job.py`:

```python
from src.sweep_job import run_deployed_sweep


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
            return FakeResponse({"ok": True, "fdtd_connected": True, "matlab_connected": True})
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
```

- [ ] **Step 2: Run bridge tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_sweep_job.py -q
```

Expected: all tests pass.

- [ ] **Step 3: If the fake bridge test fails, make the minimal fix**

Allowed fixes:

- Adjust `_request_json()` to accept the fake response shape.
- Adjust model-file filtering so evidence omits models when `include_models=false`.
- Adjust `_parse_counts()` only if the expected message format fails.

Do not add broader HTTP abstractions.

- [ ] **Step 4: Commit if code changed**

```bash
git add src/sweep_job.py tests/test_sweep_job.py
git commit -m "test: cover deployed sweep bridge"
```

---

## Task 6: Update docs and smoke instructions

**Files:**
- Modify: `README.md`
- Modify: `TECH_STACK.md`
- Modify: `SOP.md`
- Modify: `docs/RPC_API_V1.md`
- Modify: `DEV_LOG.md`

- [ ] **Step 1: Update README current status**

In `README.md`, change current status to say:

```md
- 当前代码状态：仓库内通用 `rpc_server.py`、Mac `RpcClient` 和 MCP 已统一为 API v1；Windows `5004` 已加载 close detach/timeout 修复和持久 `/jobs/*`。`geometry-smoke` 已真实通过；`metasurface-sweep` 已接入 job/task、quality report 和 evidence index，真实执行通过 `FDTD_SWEEP_RPC_URL` 桥接旧 `5003` sweep baseline。
```

- [ ] **Step 2: Update RPC API doc**

In `docs/RPC_API_V1.md`, update the job status bullets:

```md
- Job 状态：`/jobs/start` 支持短 `real geometry-smoke`；`metasurface-sweep` 已支持 `plan/mock/real` 的 job 形态、质量报告和 evidence index。真实 sweep 通过 `FDTD_SWEEP_RPC_URL` 桥接旧 `5003` baseline。
```

Update `/jobs/start` row:

```md
| POST | `/jobs/start` | 创建并执行 mock 或 real job；支持 `geometry-smoke` 和 `metasurface-sweep` |
```

Update known limits:

```md
- `metasurface-sweep` 首版把整个旧 sweep pipeline 作为一个高层 task；逐 sample resume、取消和并发队列仍是后续工作。
```

- [ ] **Step 3: Update TECH_STACK and SOP**

In `TECH_STACK.md`, update the `/jobs/*` bullet:

```md
- `/jobs/*` v1 已实现：plan、start、status、tasks、resume；支持 `geometry-smoke` 和 `metasurface-sweep`。真实 `metasurface-sweep` 通过环境变量 `FDTD_SWEEP_RPC_URL` 桥接已部署 `5003` Autosweep baseline。
```

In `SOP.md`, replace the stale line at the end of SOP-008 with:

```md
当前 `/jobs/*` v1 已实现：plan、start、status、tasks、resume。`geometry-smoke` 已真实通过；`metasurface-sweep` 已接入 quality report 和 evidence index，真实执行通过 `FDTD_SWEEP_RPC_URL` 桥接旧 `5003` baseline。首版 resume 仍是高层 task 级别，不是逐 sample 级别。
```

- [ ] **Step 4: Append DEV_LOG entry**

Append to `DEV_LOG.md`:

```md
## 2026-06-18 - 接入 metasurface sweep job evidence

- 目标：把旧 `5003` Autosweep 的 sweep/后处理能力接到新 `5004` 持久 job/task 状态机，并补质量报告和 evidence-first 回传。
- 修改：
  - 新增 `metasurface-sweep` job 类型。
  - 新增 `src/sweep_job.py`，负责 sweep task 构建、mock artifact、`5003` 桥接、quality report 和 evidence index。
  - `summary.json` 自动汇入 `quality_report.json` 和 `evidence/index.json`。
  - `rpc_server.py` 的 real sweep 通过 `FDTD_SWEEP_RPC_URL` 桥接旧 `5003` baseline。
- 验证：
  - 本地执行 `.venv/bin/python -m compileall rpc_server.py src scripts tests`，记录实际输出。
  - 本地执行 `.venv/bin/python -m pytest -q`，记录实际通过数量。
  - Windows 同步并重启后，执行 `mock metasurface-sweep` 和短 `real metasurface-sweep` smoke，记录实际 job ID、valid/missing 数量、quality conclusion 和 evidence path。
- 后续：
  - 把旧 sweep 内部 sample 映射为逐 task，实现 sample-level resume。
```

After running verification, replace the generic verification instructions in the DEV_LOG entry with the exact command outputs and Windows job evidence.

- [ ] **Step 5: Run docs consistency checks**

Run:

```bash
rg -n "真实执行仅限短|完整 sweep.*不在本版|下一阶段接入|长 sweep 仍走旧" README.md TECH_STACK.md SOP.md docs src/knowledge/prompts || true
git diff --check
```

Expected: stale statements are either gone or intentionally scoped to old docs/spec history; `git diff --check` has no output.

- [ ] **Step 6: Commit docs**

```bash
git add README.md TECH_STACK.md SOP.md docs/RPC_API_V1.md DEV_LOG.md
git commit -m "docs: document sweep job evidence"
```

---

## Task 7: Full local verification and push

**Files:**
- All changed code and docs.

- [ ] **Step 1: Compile**

Run:

```bash
.venv/bin/python -m compileall rpc_server.py src scripts tests
```

Expected: command exits `0`.

- [ ] **Step 2: Run full tests**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. The count should be greater than the previous `81 passed`.

- [ ] **Step 3: Check diff cleanliness**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files are modified before final commit, then worktree clean after commits.

- [ ] **Step 4: Push**

Run:

```bash
git push origin main
```

Expected: remote `main` advances.

---

## Task 8: Windows sync and real smoke

**Files:**
- No code edits unless verification finds a bug.

- [ ] **Step 1: Sync Windows clone**

Run from Mac over SSH:

```bash
ssh -o BatchMode=yes 32482@192.168.31.26 'cd /f/lumerical-fdtd-auto-design/fdtd-auto-design && git pull --ff-only && git rev-parse --short HEAD'
```

Expected: Windows HEAD matches Mac HEAD.

- [ ] **Step 2: Ask user to restart `5004` locally**

Say:

```text
请在 Windows 上双击 `F:\lumerical-fdtd-auto-design\fdtd-auto-design\scripts\windows\restart_rpc.bat`，让 5004 加载新代码。旧 5003 sweep baseline 也需要保持运行。
```

Wait for the user to confirm they clicked.

- [ ] **Step 3: Check both services**

Run:

```bash
ssh -o BatchMode=yes 32482@192.168.31.26 'curl -sS --max-time 5 http://127.0.0.1:5004/health && echo && curl -sS --max-time 5 http://127.0.0.1:5003/health && echo'
```

Expected:

- `5004` returns API v1 health.
- `5003` returns old sweep health with `ok=true`.

- [ ] **Step 4: Run mock sweep job on `5004`**

Run:

```bash
ssh -o BatchMode=yes 32482@192.168.31.26 'cd /f/lumerical-fdtd-auto-design/fdtd-auto-design && curl -sS --max-time 30 -X POST http://127.0.0.1:5004/jobs/start -H "Content-Type: application/json" -d "{\"mode\":\"mock\",\"job_type\":\"metasurface-sweep\"}"'
```

Expected: response state `succeeded`, summary includes `quality_report.conclusion=pass` and `evidence.download_policy.default_payload=evidence-only`.

- [ ] **Step 5: Run short real sweep job on `5004`**

Run only after explicit user approval for this real run:

```bash
ssh -o BatchMode=yes 32482@192.168.31.26 'cd /f/lumerical-fdtd-auto-design/fdtd-auto-design && curl -sS --max-time 900 -X POST http://127.0.0.1:5004/jobs/start -H "Content-Type: application/json" -d "{\"mode\":\"real\",\"job_type\":\"metasurface-sweep\",\"sweep\":{\"config\":{\"SWEEP_Y_AXIS\":\"period\",\"RATIO_PTS\":2,\"PERIOD_PTS\":2,\"FDTD_PROCESSES\":1,\"FDTD_CAPACITY\":1},\"phases\":[1,2,3],\"hide\":true,\"include_models\":false},\"approval\":{\"approved\":true,\"approved_for\":\"real_run\"}}"'
```

Expected:

- response status state is `succeeded`, or if old `5003` reports missing samples, `partial/failed` with task error and quality report.
- `jobs/<job_id>/quality_report.json` exists.
- `jobs/<job_id>/evidence/index.json` exists.
- default response does not include model bytes.

- [ ] **Step 6: Record Windows verification**

Patch `DEV_LOG.md` with the actual real sweep job ID, conclusion, valid/missing counts, and evidence path. Then:

```bash
git add DEV_LOG.md
git commit -m "docs: record windows sweep job smoke"
git push origin main
ssh -o BatchMode=yes 32482@192.168.31.26 'cd /f/lumerical-fdtd-auto-design/fdtd-auto-design && git pull --ff-only && git rev-parse --short HEAD'
```

Expected: Mac, GitHub, and Windows clone are aligned.

---

## Self-Review Checklist

- Spec coverage:
  - `metasurface-sweep` job type: Task 3.
  - quality report: Tasks 1, 2, 3, 6.
  - evidence-first index: Tasks 1, 2, 3, 6.
  - `5003` bridge: Tasks 4, 5, 8.
  - approval gate: existing JobStore behavior plus Task 4 tests.
  - docs and Windows verification: Tasks 6, 8.
- Placeholder scan:
  - No unresolved fill-in-later implementation steps.
- Type consistency:
  - `build_sweep_tasks(request) -> list`
  - `run_mock_sweep(task, job_dir) -> dict`
  - `run_deployed_sweep(task, job_dir, base_url, ...) -> dict`
  - `write_sweep_artifacts(job_dir, task, run_result) -> dict`
