# Persistent Job Feishu Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send one Feishu message when a persistent `/jobs/plan` job is created and when a persistent mock/real job reaches `succeeded`, `failed`, or `partial`, so the Agent can stop polling immediately after receiving `job_id`.

**Architecture:** Add a standard-library-only `src/job_notifications.py` module that reads existing job files, builds a text message, posts to `FDTD_FEISHU_WEBHOOK`, and atomically records successful sends in `notifications.json`. `JobStore` calls this module only after durable state and summary files exist. The real-sweep background coordinator converts uncaught runner exceptions into a durable failed job so failures also produce notifications.

**Tech Stack:** Python 3.10+ standard library (`json`, `os`, `threading`, `urllib.request`, `urllib.error`), existing `JobStore`, Flask RPC API v1, pytest.

## Global Constraints

- Notify only operations that have already created a persistent `job_id`.
- `/jobs/plan` sends one `planned` notification after the job is fully persisted.
- Mock/real jobs send only terminal notifications: `succeeded`, `failed`, or `partial`.
- Ordinary SimulationPlan validation, approval, and local preflight do not notify.
- Read the complete Webhook only from `FDTD_FEISHU_WEBHOOK`.
- Never persist or log the Webhook URL.
- Use no third-party dependency, database, message queue, polling daemon, or new MCP tool.
- Notification failure must never change or prevent the correct job state.
- Do not add `DONE` or `FAILED` markers; `status.json` remains authoritative.
- Tests must not access Feishu or start FDTD.
- After submitting a long job, the documented Agent behavior is to return `job_id` and stop polling unless the user explicitly asks for one status check.

---

## File Structure

- Create `src/job_notifications.py`: notification formatting, HTTP POST, atomic idempotency record, safe logging.
- Create `tests/test_job_notifications.py`: isolated notification behavior and security tests.
- Create `tests/conftest.py`: clear the real Webhook from every pytest process unless a test explicitly supplies a fake value.
- Modify `src/job_store.py`: call notifications after planned and terminal state persistence; add one durable failed-job transition for background runner exceptions.
- Modify `rpc_server.py`: let `SweepCoordinator` convert uncaught real-sweep exceptions into a failed persistent job.
- Modify `tests/test_job_store.py`: integration tests for planned/mock/failed/partial notification triggers.
- Modify `tests/test_rpc_server_jobs.py`: background real-sweep exception regression test.
- Modify `README.md`, `SOP.md`, `docs/WINDOWS_RUNBOOK.md`, `DEV_LOG.md`: configuration and no-poll workflow.

### Interfaces

`src/job_notifications.py` produces:

```python
FEISHU_WEBHOOK_ENV = "FDTD_FEISHU_WEBHOOK"
NOTIFIABLE_STATES = {"planned", "succeeded", "failed", "partial"}

def build_job_notification_text(job_dir: Path, state: str) -> str: ...

def notify_job_state(
    job_dir: Path,
    state: str,
    *,
    timeout: float = 10.0,
) -> dict: ...
```

`src/job_store.py` produces:

```python
def fail(self, job_id: str, error: BaseException) -> dict: ...
```

The notification result envelope is:

```python
{"sent": True, "state": "succeeded"}
{"sent": False, "state": "succeeded", "reason": "already_sent"}
{"sent": False, "state": "succeeded", "reason": "webhook_not_configured"}
{"sent": False, "state": "succeeded", "reason": "delivery_failed"}
```

---

### Task 1: Add the isolated Feishu notification module

**Files:**
- Create: `src/job_notifications.py`
- Create: `tests/test_job_notifications.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: existing `manifest.json`, `status.json`, `summary.json`, optional `quality_report.json`.
- Produces: `build_job_notification_text(job_dir, state)` and `notify_job_state(job_dir, state, timeout=10.0)`.

- [ ] **Step 1: Write notification fixtures and failing formatting tests**

Create `tests/conftest.py` first so the complete suite can never inherit and call a real user Webhook:

```python
import pytest


@pytest.fixture(autouse=True)
def clear_real_feishu_webhook(monkeypatch):
    monkeypatch.delenv("FDTD_FEISHU_WEBHOOK", raising=False)
```

Create `tests/test_job_notifications.py`:

```python
import json
from pathlib import Path


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_job(
    root: Path,
    *,
    mode: str = "real",
    state: str = "succeeded",
) -> Path:
    job_dir = root / "job_20260619_230000_metasurface_sweep"
    write_json(
        job_dir / "manifest.json",
        {
            "job_id": job_dir.name,
            "mode": mode,
            "paths": {"job_dir": str(job_dir)},
        },
    )
    write_json(
        job_dir / "status.json",
        {
            "job_id": job_dir.name,
            "state": state,
            "task_counts": {
                "total": 25,
                "pending": 0,
                "running": 0,
                "succeeded": 24,
                "failed": 1,
                "skipped": 0,
            },
        },
    )
    write_json(
        job_dir / "summary.json",
        {
            "job_id": job_dir.name,
            "task_counts": {
                "total": 25,
                "pending": 0,
                "running": 0,
                "succeeded": 24,
                "failed": 1,
                "skipped": 0,
            },
        },
    )
    write_json(
        job_dir / "quality_report.json",
        {"conclusion": "warning"},
    )
    (job_dir / "run.log").write_text("", encoding="utf-8")
    return job_dir


def test_build_terminal_text_contains_required_job_evidence(tmp_path):
    from src.job_notifications import build_job_notification_text

    job_dir = write_job(tmp_path, state="partial")

    text = build_job_notification_text(job_dir, "partial")

    assert "FDTD job partial" in text
    assert "mode: real" in text
    assert f"job: {job_dir.name}" in text
    assert "tasks: 24 succeeded / 1 failed / 25 total" in text
    assert "quality: warning" in text
    assert f"job_dir: {job_dir}" in text


def test_build_planned_text_uses_total_task_count(tmp_path):
    from src.job_notifications import build_job_notification_text

    job_dir = write_job(tmp_path, mode="mock", state="planned")

    text = build_job_notification_text(job_dir, "planned")

    assert "FDTD job planned" in text
    assert "mode: mock" in text
    assert "tasks: 25 total" in text
    assert "quality:" not in text
```

- [ ] **Step 2: Run formatting tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_notifications.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'src.job_notifications'`.

- [ ] **Step 3: Add failing delivery, idempotency, and safety tests**

Append to `tests/test_job_notifications.py`:

```python
import os
from unittest.mock import patch


def test_notify_posts_text_and_records_success_without_webhook(tmp_path):
    from src.job_notifications import (
        FEISHU_WEBHOOK_ENV,
        notify_job_state,
    )

    job_dir = write_job(tmp_path)
    webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/secret-value"

    with patch.dict(os.environ, {FEISHU_WEBHOOK_ENV: webhook}, clear=False):
        with patch(
            "src.job_notifications._post_feishu",
            return_value={"status": 200, "body": "{}"},
        ) as post:
            result = notify_job_state(job_dir, "succeeded")

    assert result == {"sent": True, "state": "succeeded"}
    post.assert_called_once()
    assert post.call_args.args[0] == webhook
    record = json.loads(
        (job_dir / "notifications.json").read_text(encoding="utf-8")
    )
    assert record["succeeded"]["sent"] is True
    assert webhook not in json.dumps(record)
    assert webhook not in (job_dir / "run.log").read_text(encoding="utf-8")


def test_notify_same_state_is_idempotent_after_success(tmp_path):
    from src.job_notifications import (
        FEISHU_WEBHOOK_ENV,
        notify_job_state,
    )

    job_dir = write_job(tmp_path)
    with patch.dict(
        os.environ,
        {FEISHU_WEBHOOK_ENV: "https://open.feishu.cn/test"},
        clear=False,
    ):
        with patch(
            "src.job_notifications._post_feishu",
            return_value={"status": 200, "body": "{}"},
        ) as post:
            first = notify_job_state(job_dir, "succeeded")
            second = notify_job_state(job_dir, "succeeded")

    assert first["sent"] is True
    assert second == {
        "sent": False,
        "state": "succeeded",
        "reason": "already_sent",
    }
    post.assert_called_once()


def test_notify_skips_without_webhook_and_does_not_create_success_record(
    tmp_path,
):
    from src.job_notifications import notify_job_state

    job_dir = write_job(tmp_path)
    with patch.dict(os.environ, {}, clear=True):
        with patch("src.job_notifications._post_feishu") as post:
            result = notify_job_state(job_dir, "succeeded")

    assert result["reason"] == "webhook_not_configured"
    assert not (job_dir / "notifications.json").exists()
    post.assert_not_called()


def test_delivery_failure_is_logged_without_leaking_webhook(tmp_path):
    from src.job_notifications import (
        FEISHU_WEBHOOK_ENV,
        notify_job_state,
    )

    job_dir = write_job(tmp_path)
    webhook = "https://open.feishu.cn/open-apis/bot/v2/hook/secret-value"
    with patch.dict(os.environ, {FEISHU_WEBHOOK_ENV: webhook}, clear=False):
        with patch(
            "src.job_notifications._post_feishu",
            side_effect=OSError("network unavailable"),
        ):
            result = notify_job_state(job_dir, "failed")

    log = (job_dir / "run.log").read_text(encoding="utf-8")
    assert result["reason"] == "delivery_failed"
    assert webhook not in log
    assert not (job_dir / "notifications.json").exists()


def test_non_notifiable_state_is_skipped(tmp_path):
    from src.job_notifications import notify_job_state

    job_dir = write_job(tmp_path, state="running")

    result = notify_job_state(job_dir, "running")

    assert result["reason"] == "state_not_notifiable"


def test_corrupt_notification_record_is_treated_as_unsent(tmp_path):
    from src.job_notifications import (
        FEISHU_WEBHOOK_ENV,
        notify_job_state,
    )

    job_dir = write_job(tmp_path)
    (job_dir / "notifications.json").write_text("{broken", encoding="utf-8")
    with patch.dict(
        os.environ,
        {FEISHU_WEBHOOK_ENV: "https://open.feishu.cn/test"},
        clear=False,
    ):
        with patch(
            "src.job_notifications._post_feishu",
            return_value={"status": 200, "body": "{}"},
        ):
            result = notify_job_state(job_dir, "succeeded")

    assert result["sent"] is True
    assert "notification record unreadable" in (
        job_dir / "run.log"
    ).read_text(encoding="utf-8")
```

- [ ] **Step 4: Implement the minimal notification module**

Create `src/job_notifications.py`:

```python
"""Best-effort Feishu notifications for persistent jobs."""

import json
import os
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


FEISHU_WEBHOOK_ENV = "FDTD_FEISHU_WEBHOOK"
NOTIFIABLE_STATES = {"planned", "succeeded", "failed", "partial"}
_NOTIFICATION_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_log(job_dir: Path, message: str) -> None:
    with (job_dir / "run.log").open("a", encoding="utf-8") as output:
        output.write(f"{_utc_now()} {message}\n")


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


def build_job_notification_text(job_dir: Path, state: str) -> str:
    job_dir = Path(job_dir)
    manifest = _read_json(job_dir / "manifest.json")
    summary = _read_json(job_dir / "summary.json")
    counts = summary.get("task_counts") or {}
    lines = [
        f"FDTD job {state}",
        f"mode: {manifest.get('mode', 'unknown')}",
        f"job: {manifest.get('job_id', job_dir.name)}",
    ]
    if state == "planned":
        lines.append(f"tasks: {counts.get('total', 0)} total")
    else:
        lines.append(
            "tasks: {succeeded} succeeded / {failed} failed / "
            "{total} total".format(
                succeeded=counts.get("succeeded", 0),
                failed=counts.get("failed", 0),
                total=counts.get("total", 0),
            )
        )
        quality = summary.get("quality_report") or {}
        lines.append(
            f"quality: {quality.get('conclusion', 'unavailable')}"
        )
    lines.append(f"job_dir: {job_dir}")
    return "\n".join(lines)


def _post_feishu(
    webhook_url: str,
    text: str,
    timeout: float = 10.0,
) -> dict:
    payload = {"msg_type": "text", "content": {"text": text}}
    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return {
            "status": response.status,
            "body": response.read().decode("utf-8", errors="replace"),
        }


def _read_notification_record(job_dir: Path) -> dict:
    path = job_dir / "notifications.json"
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except (OSError, ValueError, TypeError):
        _append_log(job_dir, "Feishu notification record unreadable; retrying.")
        return {}


def notify_job_state(
    job_dir: Path,
    state: str,
    *,
    timeout: float = 10.0,
) -> dict:
    job_dir = Path(job_dir)
    if state not in NOTIFIABLE_STATES:
        return {
            "sent": False,
            "state": state,
            "reason": "state_not_notifiable",
        }

    with _NOTIFICATION_LOCK:
        record = _read_notification_record(job_dir)
        if (record.get(state) or {}).get("sent") is True:
            return {
                "sent": False,
                "state": state,
                "reason": "already_sent",
            }

        webhook = os.environ.get(FEISHU_WEBHOOK_ENV, "").strip()
        if not webhook:
            _append_log(
                job_dir,
                f"Skipping Feishu notification: {FEISHU_WEBHOOK_ENV} is not set.",
            )
            return {
                "sent": False,
                "state": state,
                "reason": "webhook_not_configured",
            }

        try:
            text = build_job_notification_text(job_dir, state)
            response = _post_feishu(webhook, text, timeout=timeout)
            record[state] = {
                "sent": True,
                "sent_at": _utc_now(),
                "http_status": response["status"],
            }
            _write_json_atomic(job_dir / "notifications.json", record)
            _append_log(
                job_dir,
                f"Feishu notification sent for state={state}.",
            )
            return {"sent": True, "state": state}
        except Exception as exc:
            _append_log(
                job_dir,
                "Feishu notification failed for "
                f"state={state}: {exc.__class__.__name__}.",
            )
            return {
                "sent": False,
                "state": state,
                "reason": "delivery_failed",
            }
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_notifications.py -q
```

Expected: `8 passed`.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/job_notifications.py tests/conftest.py tests/test_job_notifications.py
git commit -m "feat: add persistent job notifications"
```

---

### Task 2: Trigger notifications from durable JobStore transitions

**Files:**
- Modify: `src/job_store.py`
- Modify: `tests/test_job_store.py`

**Interfaces:**
- Consumes: `notify_job_state(job_dir: Path, state: str) -> dict`.
- Produces: planned and terminal notification hooks plus `JobStore.fail(job_id, error)`.

- [ ] **Step 1: Add failing JobStore notification tests**

Append to `tests/test_job_store.py`:

```python
from unittest.mock import patch


def test_jobs_plan_notifies_after_persistent_files_exist(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with patch("src.job_store.notify_job_state") as notify:
        job = store.plan({"mode": "mock", "job_type": "geometry-smoke"})

    job_dir = tmp_path / "jobs" / job["job_id"]
    notify.assert_called_once_with(job_dir, "planned")
    assert (job_dir / "status.json").exists()
    assert (job_dir / "summary.json").exists()
    assert (job_dir / "run.log").exists()


def test_mock_start_notifies_succeeded_once(tmp_path):
    store = JobStore(tmp_path / "jobs", code_version="test-sha")

    with patch("src.job_store.notify_job_state") as notify:
        job = store.start({"mode": "mock", "job_type": "geometry-smoke"})

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
            "approval": {"approved": True, "approved_for": "real_run"},
        }
    )

    with patch("src.job_store.notify_job_state") as notify:
        result = store.fail(job["job_id"], RuntimeError("solver crashed"))

    task = store.list_tasks(job["job_id"])["tasks"][0]
    assert result["state"] == "failed"
    assert task["state"] == "failed"
    assert task["error"]["type"] == "RuntimeError"
    assert task["error"]["message"] == "solver crashed"
    notify.assert_called_once_with(
        tmp_path / "jobs" / job["job_id"],
        "failed",
    )
```

- [ ] **Step 2: Run JobStore tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_job_store.py::test_jobs_plan_notifies_after_persistent_files_exist \
  tests/test_job_store.py::test_mock_start_notifies_succeeded_once \
  tests/test_job_store.py::test_finalize_notifies_partial_after_summary_is_written \
  tests/test_job_store.py::test_fail_marks_unfinished_tasks_failed_and_notifies \
  -q
```

Expected: failures because `notify_job_state` is not imported/called and `JobStore.fail` does not exist.

- [ ] **Step 3: Import notification helper and add one terminal-state helper**

Modify the imports in `src/job_store.py`:

```python
from src.job_notifications import notify_job_state
```

Add this private method before `finalize()`:

```python
    def _finish(self, job_id: str, state: str) -> dict:
        self._write_status(job_id, state, f"Job {state}.")
        self._write_summary(job_id)
        self.append_log(job_id, f"Job {state}.")
        notify_job_state(self._job_dir(job_id), state)
        return self.get(job_id)
```

- [ ] **Step 4: Notify planned jobs after all files exist**

At the end of `_create_job()`, after `run.log` is written and before returning, add:

```python
        if state == "planned":
            notify_job_state(job_dir, "planned")
```

This intentionally follows the `/jobs/plan` operation and does not inspect the requested future execution mode. A persisted preview of a mock or real request is still a planned job and gets one planned notification.

- [ ] **Step 5: Route normal terminal transitions through `_finish`**

Replace the final lines of `finalize()`:

```python
        return self._finish(job_id, state)
```

Replace the final status/summary writes in `_run_job()`:

```python
        self._finish(job_id, state)
```

Do not notify from `_write_status()`. Queued and running transitions must remain silent.

- [ ] **Step 6: Add durable explicit failure handling**

Add after `finalize()`:

```python
    def fail(self, job_id: str, error: BaseException) -> dict:
        error_payload = {
            "type": error.__class__.__name__,
            "message": str(error),
            "details": {},
        }
        for task in self._tasks(job_id):
            if task["state"] in {"pending", "running"}:
                self.update_task(
                    job_id,
                    task["task_id"],
                    state="failed",
                    phase=task.get("phase", "failed"),
                    error=error_payload,
                )
        return self._finish(job_id, "failed")
```

Use this only for an uncaught job-level exception. Normal per-task failures continue through `finalize()` and may produce `partial`.

- [ ] **Step 7: Notify recovered partial jobs**

In `recover_interrupted_jobs()`, replace its direct final writes:

```python
            self._finish(job_id, "partial")
```

Keep the existing `"Recovered interrupted job."` log append after `_finish()`. Notification idempotency prevents a duplicate if the same terminal state was already delivered.

- [ ] **Step 8: Run focused JobStore tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_job_store.py tests/test_job_notifications.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 2**

```bash
git add src/job_store.py tests/test_job_store.py
git commit -m "feat: notify persistent job transitions"
```

---

### Task 3: Persist and notify uncaught background real-sweep failures

**Files:**
- Modify: `rpc_server.py`
- Modify: `tests/test_rpc_server_jobs.py`

**Interfaces:**
- Consumes: `JobStore.fail(job_id, error) -> dict`.
- Produces: a background real sweep that cannot remain indefinitely `running` after an uncaught runner exception.

- [ ] **Step 1: Add a failing RPC regression test**

Append to `tests/test_rpc_server_jobs.py`:

```python
def test_real_sweep_background_exception_marks_job_failed(
    server_module,
    fake_session,
    tmp_path,
):
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    finished = threading.Event()

    class FailingRunner:
        def run(self, job_id):
            try:
                raise RuntimeError("runner exploded")
            finally:
                finished.set()

    store = server_module.JobStore(
        tmp_path / "jobs",
        code_version="test-sha",
    )
    app = server_module.create_app(
        fake_session,
        job_store=store,
        sweep_runner=FailingRunner(),
    )
    app.config.update(TESTING=True)
    client = app.test_client()

    with patch("src.job_store.notify_job_state") as notify:
        response = client.post(
            "/jobs/start",
            json={
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
            },
        )
        job_id = response.get_json()["job_id"]
        assert finished.wait(timeout=1)
        for _ in range(50):
            state = store.get(job_id)["state"]
            if state == "failed":
                break
            threading.Event().wait(0.01)

    assert response.status_code == 202
    assert store.get(job_id)["state"] == "failed"
    task = store.list_tasks(job_id)["tasks"][0]
    assert task["error"]["type"] == "RuntimeError"
    notify.assert_called_once_with(
        tmp_path / "jobs" / job_id,
        "failed",
    )
```

Add this import near the top if absent:

```python
from unittest.mock import patch
```

- [ ] **Step 2: Run the regression test to verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_rpc_server_jobs.py::test_real_sweep_background_exception_marks_job_failed \
  -q
```

Expected: FAIL because the current `SweepCoordinator` only logs the exception and leaves the job queued/running.

- [ ] **Step 3: Give SweepCoordinator the JobStore failure callback**

Change `SweepCoordinator`:

```python
class SweepCoordinator:
    def __init__(self, runner, job_store: JobStore):
        self.runner = runner
        self.job_store = job_store
        self._lock = threading.Lock()
        self._active_job_id = None
```

Change the worker exception block:

```python
            except Exception as exc:
                logger.exception("Native sweep job failed: %s", job_id)
                self.job_store.fail(job_id, exc)
```

Change construction in `create_app()`:

```python
    sweeps = SweepCoordinator(runner, jobs)
```

- [ ] **Step 4: Run RPC and job tests**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_rpc_server_jobs.py \
  tests/test_job_store.py \
  tests/test_job_notifications.py \
  -q
```

Expected: all tests pass, including existing async sweep locking tests.

- [ ] **Step 5: Commit Task 3**

```bash
git add rpc_server.py tests/test_rpc_server_jobs.py
git commit -m "fix: persist background sweep failures"
```

---

### Task 4: Document the no-poll workflow and Windows configuration

**Files:**
- Modify: `README.md`
- Modify: `SOP.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Modify: `DEV_LOG.md`

**Interfaces:**
- Consumes: `FDTD_FEISHU_WEBHOOK`, persistent job terminal notification behavior.
- Produces: operator instructions and Agent handoff policy.

- [ ] **Step 1: Update README current workflow**

In `README.md`, update the current-state section to state:

```markdown
- 持久 job 已支持飞书状态通知：`/jobs/plan` 创建完成后通知 `planned`；mock/real 到达 `succeeded`、`failed` 或 `partial` 后通知。Agent 提交长任务并返回 `job_id` 后默认停止轮询，用户收到飞书后再要求结果分析。
```

Update the target chain:

```text
明确批准 real
  -> Windows 异步 job/task 执行
  -> 飞书通知终态
  -> 用户召回 Agent
  -> 结果提取与质量报告
```

- [ ] **Step 2: Add a concise SOP**

Append to `SOP.md`:

```markdown
## SOP-015 - 持久 job 飞书通知与 Agent 退出

1. Windows 用户环境设置 `FDTD_FEISHU_WEBHOOK`，Webhook 不写入 Git 或 job 输入。
2. 重启 RPC 服务，让 `pythonw.exe` 继承环境变量。
3. `/jobs/plan` 创建持久 job 后发送 `planned`；mock/real 到达 `succeeded`、`failed` 或 `partial` 后发送终态通知。
4. Agent 提交长任务并确认收到 `job_id` 后停止轮询；只有用户明确询问进度时才做一次只读查询。
5. 用户收到飞书后，让 Agent 读取 `status.json`、`summary.json`、`quality_report.json` 和 evidence-first 结果。
6. 飞书发送失败只查 `run.log`，不得据此重跑或改变 job 状态。
```

- [ ] **Step 3: Add Windows configuration and smoke procedure**

Append to `docs/WINDOWS_RUNBOOK.md`:

````markdown
## 飞书持久 Job 通知

设置用户环境变量：

```powershell
setx FDTD_FEISHU_WEBHOOK "https://open.feishu.cn/open-apis/bot/v2/hook/你的Webhook"
```

然后运行 `scripts\windows\restart_rpc.bat`。不要把 Webhook 写入仓库、请求 JSON 或日志。

不启动 FDTD 的 smoke：

```powershell
$body = @{
  mode = "mock"
  job_type = "geometry-smoke"
} | ConvertTo-Json
Invoke-RestMethod `
  -Uri "http://127.0.0.1:5000/jobs/start" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

成功标准：

- HTTP 返回持久 `job_id`。
- 飞书收到 `FDTD job succeeded`。
- job 目录的 `notifications.json` 只含发送状态和时间，不含 Webhook。
- `run.log` 含发送成功记录。
- 不启动真实 FDTD 求解。
````

- [ ] **Step 4: Record implementation verification in DEV_LOG**

Append a dated entry:

```markdown
## 2026-06-19 - Persistent job Feishu notifications

- 复用旧 Autosweep 的标准库飞书 Webhook 模式，接入新项目持久 JobStore。
- `/jobs/plan` 通知 planned；mock/real 通知 succeeded、failed、partial；普通 SimulationPlan 校验和 preflight 不通知。
- 通知采用 `notifications.json` 幂等记录，Webhook 只从 `FDTD_FEISHU_WEBHOOK` 读取，发送失败不影响 job 状态。
- Agent 工作流改为提交后返回 job_id 并停止轮询，收到飞书后再分析。
- 验证：记录 focused/full pytest、compileall 和 Windows mock smoke 的实际结果。
```

The implementer must replace the last verification line with actual command output before committing.

- [ ] **Step 5: Run documentation and secret scans**

Run:

```bash
! rg -n "open-apis/bot/v2/hook/[0-9a-fA-F-]{8,}" \
  README.md SOP.md docs src tests DEV_LOG.md
git diff --check
```

Expected: no real-looking Webhook is found; `git diff --check` exits 0.

- [ ] **Step 6: Commit Task 4**

```bash
git add README.md SOP.md docs/WINDOWS_RUNBOOK.md DEV_LOG.md
git commit -m "docs: document persistent job notifications"
```

---

### Task 5: Full offline verification and Windows mock notification smoke

**Files:**
- Modify only if verification reveals a defect directly caused by Tasks 1–4.
- Runtime-only: the new Windows mock job's `notifications.json`; do not commit.

**Interfaces:**
- Consumes: complete notification integration.
- Produces: verified offline suite and one non-FDTD Windows delivery check.

- [ ] **Step 1: Run compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exit 0.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass with no external network call and no FDTD launch.

- [ ] **Step 3: Run security and scope scans**

Run:

```bash
! rg -n "FDTD_FEISHU_WEBHOOK\\s*=\\s*['\\\"]https://" .
! rg -n "open-apis/bot/v2/hook/[0-9a-fA-F-]{8,}" .
! rg -n "requests|httpx|aiohttp" src/job_notifications.py
git diff --check
```

Expected: all commands exit 0. The literal environment-variable name and placeholder URL in documentation are allowed; no actual Webhook secret or third-party HTTP client is present.

- [ ] **Step 4: Push implementation before Windows sync**

Run:

```bash
git status --short --branch
git push origin main
```

Expected: clean worktree and `main` synchronized with `origin/main`.

- [ ] **Step 5: Configure Windows and restart RPC**

On Windows PowerShell:

```powershell
setx FDTD_FEISHU_WEBHOOK "https://open.feishu.cn/open-apis/bot/v2/hook/你的Webhook"
cd F:\lumerical-fdtd-auto-design\fdtd-auto-design
git pull --ff-only
scripts\windows\restart_rpc.bat
```

Expected: RPC health check passes on `127.0.0.1:5000`.

- [ ] **Step 6: Run one persistent mock smoke**

On Windows PowerShell:

```powershell
$body = @{
  mode = "mock"
  job_type = "geometry-smoke"
} | ConvertTo-Json
$response = Invoke-RestMethod `
  -Uri "http://127.0.0.1:5000/jobs/start" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
$response
```

Expected:

- response contains `ok=true`, `state=succeeded`, and a new `job_id`;
- Feishu receives one message;
- no FDTD solver is launched.

- [ ] **Step 7: Verify notification evidence without exposing the secret**

In the same Windows PowerShell session, use the returned ID directly:

```powershell
$job = Join-Path `
  "F:\lumerical-fdtd-auto-design\fdtd-auto-design\jobs" `
  $response.job_id
Get-Content "$job\notifications.json"
Get-Content "$job\run.log" -Tail 10
Select-String `
  -Path "$job\notifications.json","$job\run.log" `
  -Pattern "open-apis/bot/v2/hook"
```

Expected:

- `notifications.json` contains `succeeded.sent=true`;
- `run.log` records successful delivery;
- `Select-String` returns no match.

- [ ] **Step 8: Update DEV_LOG with actual verification results and commit**

Replace the provisional verification line in `DEV_LOG.md` with actual compileall, pytest, security scan, Windows HEAD, mock job ID, and delivery result.

```bash
git add DEV_LOG.md
git commit -m "docs: record job notification verification"
git push origin main
```

- [ ] **Step 9: Final status check**

Run:

```bash
git status --short --branch
git log -6 --oneline
```

Expected: clean worktree, synchronized with `origin/main`, and separate commits for notification core, JobStore integration, background failure handling, docs, and verification.

---

## Final Verification Checklist

- `src/job_notifications.py` uses only the Python standard library.
- `/jobs/plan` sends one planned notification after durable files exist.
- Mock and real jobs notify only `succeeded`, `failed`, or `partial`.
- Uncaught background real-sweep failures become durable failed jobs.
- Notification errors never change job state.
- `notifications.json` never contains the Webhook.
- Duplicate calls for the same job/state do not resend after success.
- Ordinary SimulationPlan validation/approval/preflight remains silent.
- Agent documentation says to stop polling after receiving `job_id`.
- Windows mock smoke sends a real Feishu message without launching FDTD.
