"""Native metasurface sweep execution using the shared FDTD session."""

import json
from pathlib import Path


def sample_model_path(job_dir: Path, task_id: str) -> Path:
    return job_dir / "models" / f"{task_id}.fsp"


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
        job_dir = Path(job["job_dir"])
        request = json.loads(
            (job_dir / "inputs" / "request.json").read_text(encoding="utf-8")
        )
        sweep = request["sweep"]
        template = Path(sweep["template"]).resolve()
        if not template.is_file():
            raise FileNotFoundError(f"Sweep template not found: {template}")

        tasks = [
            task
            for task in self.store.list_tasks(job_id)["tasks"]
            if task["state"] in {"pending", "failed"}
        ]
        fdtd = self._fdtd(sweep["hide"])
        self.store.mark_running(job_id)

        if 1 in sweep["phases"]:
            self._generate_models(job_id, job_dir, template, sweep, tasks, fdtd)
        if 2 in sweep["phases"]:
            self._run_queue(job_id, tasks, fdtd)
        return self.store.get(job_id)

    def _generate_models(
        self,
        job_id: str,
        job_dir: Path,
        template: Path,
        sweep: dict,
        tasks: list,
        fdtd,
    ) -> None:
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
                    f"Warning: could not set FDTD resources: {exc}",
                )

            for task in tasks:
                task_id = task["task_id"]
                sample = task["input"]
                self.store.update_task(
                    job_id,
                    task_id,
                    state="running",
                    phase="generating",
                )
                fdtd.load(str(template))
                fdtd.switchtolayout()
                fdtd.setnamed("FDTD", "express mode", 1)
                fdtd.setnamed("::model", "ratio", sample["ratio"])
                fdtd.setnamed("::model", "height", sample["height"])
                fdtd.setnamed("::model", "period", sample["period"])
                model_path = sample_model_path(job_dir, task_id).resolve()
                fdtd.save(str(model_path))
                fdtd.addjob(str(model_path))
                self.store.update_task(
                    job_id,
                    task_id,
                    state="running",
                    phase="queued",
                    outputs={"model_file": str(model_path)},
                )
        finally:
            fdtd.redrawon()

    def _run_queue(self, job_id: str, tasks: list, fdtd) -> None:
        for task in tasks:
            self.store.update_task(
                job_id,
                task["task_id"],
                state="running",
                phase="solving",
            )
        fdtd.runjobs()
