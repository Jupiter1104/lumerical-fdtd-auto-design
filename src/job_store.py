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

    def __init__(
        self,
        error_type: str,
        message: str,
        status_code: int,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json(data: dict) -> str:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def request_hash(request: dict) -> str:
    return hashlib.sha256(stable_json(request).encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_").lower()
    return slug or "job"


class JobStore:
    def __init__(
        self,
        root: Union[Path, str] = "jobs",
        code_version: str = "unknown",
    ):
        self.root = Path(root)
        self.code_version = code_version

    def plan(self, request: dict) -> dict:
        normalized = self._normalize_request(request)
        job_id = self._new_job_id(normalized["job_type"])
        return self._create_job(job_id, normalized, state="planned")

    def start(
        self,
        request: dict,
        executor: Optional[Callable[[dict, Path], dict]] = None,
    ) -> dict:
        normalized = self._normalize_request(request)
        if normalized["mode"] == "real":
            approval = normalized["approval"]
            if (
                approval.get("approved") is not True
                or approval.get("approved_for") != "real_run"
            ):
                raise JobError(
                    "approval_required",
                    "Real jobs require explicit approval.",
                    403,
                )

        existing = self._find_idempotent_job(normalized)
        if existing:
            return existing

        job_id = self._new_job_id(normalized["job_type"])
        self._create_job(job_id, normalized, state="queued")
        self._remember_idempotency(normalized, job_id)
        self._run_job(job_id, executor)
        return self.get(job_id)

    def get(self, job_id: str) -> dict:
        job_dir = self._job_dir(job_id)
        manifest = self._read_json(job_dir / "manifest.json")
        status = self._read_json(job_dir / "status.json")
        summary = self._read_json(job_dir / "summary.json")
        return {
            "job_id": job_id,
            "state": status["state"],
            "task_count": summary["task_counts"]["total"],
            "job_dir": manifest["paths"]["job_dir"],
            "manifest": manifest,
            "status": status,
            "summary": summary,
        }

    def list_tasks(self, job_id: str) -> dict:
        return {"job_id": job_id, "tasks": self._tasks(job_id)}

    def resume(
        self,
        job_id: str,
        executor: Optional[Callable[[dict, Path], dict]] = None,
    ) -> dict:
        tasks = self._tasks(job_id)
        selected = [
            task["task_id"]
            for task in tasks
            if task["state"] in {"pending", "failed"}
        ]
        if executor is not None and selected:
            self._run_job(job_id, executor, only_task_ids=set(selected))
        return {"job_id": job_id, "task_ids": selected}

    def _normalize_request(self, request: dict) -> dict:
        if not isinstance(request, dict):
            raise JobError("validation_error", "JSON body must be an object.", 400)

        mode = request.get("mode", "mock")
        job_type = request.get("job_type", "geometry-smoke")
        if mode not in {"plan", "mock", "real"}:
            raise JobError(
                "validation_error",
                "mode must be one of plan, mock, or real.",
                400,
            )
        if job_type != "geometry-smoke":
            raise JobError(
                "validation_error",
                "job_type must be geometry-smoke in v1.",
                400,
            )

        tasks = request.get("tasks") or [
            {
                "operation": "geometry-smoke",
                "input": {"hide": bool(request.get("hide", False))},
            }
        ]
        if not isinstance(tasks, list) or not tasks:
            raise JobError(
                "validation_error",
                "tasks must be a non-empty list.",
                400,
            )

        return {
            "mode": mode,
            "job_type": job_type,
            "idempotency_key": request.get("idempotency_key"),
            "approval": request.get("approval")
            or {"approved": False, "approved_for": None},
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
        (job_dir / "run.log").write_text(
            f"{created_at} Job {state}.\n",
            encoding="utf-8",
        )
        return {
            "job_id": job_id,
            "state": state,
            "task_count": len(request["tasks"]),
            "job_dir": str(job_dir),
        }

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, path)

    def _read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _job_dir(self, job_id: str) -> Path:
        job_dir = self.root / job_id
        if not (job_dir / "manifest.json").exists():
            raise JobError(
                "job_not_found",
                f"Job not found: {job_id}",
                404,
                {"job_id": job_id},
            )
        return job_dir

    def _tasks(self, job_id: str) -> list:
        tasks_dir = self._job_dir(job_id) / "tasks"
        return [
            self._read_json(path)
            for path in sorted(tasks_dir.glob("task_*.json"))
        ]

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
            "finished_at": now
            if state in {"succeeded", "failed", "partial"}
            else None,
        }
        self._write_json(status_path, status)
        return status

    def _write_summary(self, job_id: str) -> dict:
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
        self._write_json(self._job_dir(job_id) / "summary.json", summary)
        return summary

    def _run_job(
        self,
        job_id: str,
        executor: Optional[Callable[[dict, Path], dict]] = None,
        only_task_ids: Optional[Set[str]] = None,
    ) -> None:
        self._write_status(job_id, "running", "Job running.")
        selected_tasks = []
        for task in self._tasks(job_id):
            if only_task_ids is None or task["task_id"] in only_task_ids:
                selected_tasks.append(task)

        for task in selected_tasks:
            self._run_task(job_id, task, executor)

        counts = self._task_counts(self._tasks(job_id))
        if counts["failed"]:
            state = "partial" if counts["succeeded"] else "failed"
        elif counts["pending"] or counts["running"]:
            state = "partial"
        else:
            state = "succeeded"
        self._write_status(job_id, state, f"Job {state}.")
        self._write_summary(job_id)

    def _run_task(
        self,
        job_id: str,
        task: dict,
        executor: Optional[Callable[[dict, Path], dict]],
    ) -> None:
        job_dir = self._job_dir(job_id)
        task_path = job_dir / "tasks" / f"{task['task_id']}.json"
        task["state"] = "running"
        task["attempts"] += 1
        task["updated_at"] = utc_now()
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
            raise JobError(
                "idempotency_conflict",
                "idempotency_key was already used with different input.",
                409,
            )
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
