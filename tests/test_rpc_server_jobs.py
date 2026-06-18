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
    response = client.post(
        "/jobs/plan",
        json={"mode": "mock", "job_type": "geometry-smoke"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["state"] == "planned"
    assert payload["task_count"] == 1
    assert payload["job_id"].startswith("job_")


def test_jobs_start_mock_endpoint_succeeds(client):
    response = client.post(
        "/jobs/start",
        json={"mode": "mock", "job_type": "geometry-smoke"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"]["state"] == "succeeded"
    assert payload["summary"]["task_counts"]["succeeded"] == 1


def test_jobs_start_real_requires_approval(client):
    response = client.post(
        "/jobs/start",
        json={"mode": "real", "job_type": "geometry-smoke"},
    )
    payload = response.get_json()

    assert response.status_code == 403
    assert payload["ok"] is False
    assert payload["error"]["type"] == "approval_required"


def test_jobs_get_and_tasks_endpoints_read_disk_state(client):
    started = client.post(
        "/jobs/start",
        json={"mode": "mock", "job_type": "geometry-smoke"},
    ).get_json()
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
            "tasks": [
                {
                    "operation": "geometry-smoke",
                    "input": {"hide": False},
                }
            ],
        },
    ).get_json()

    response = client.post(f"/jobs/{planned['job_id']}/resume", json={})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["task_ids"] == ["task_0001"]


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
    assert (
        payload["summary"]["evidence"]["download_policy"]["default_payload"]
        == "evidence-only"
    )


def test_jobs_start_real_metasurface_sweep_requires_approval(client):
    response = client.post(
        "/jobs/start",
        json={"mode": "real", "job_type": "metasurface-sweep"},
    )
    payload = response.get_json()

    assert response.status_code == 403
    assert payload["ok"] is False
    assert payload["error"]["type"] == "approval_required"


def test_jobs_start_real_metasurface_sweep_uses_deployed_bridge(
    server_module,
    fake_session,
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_run_deployed_sweep(task, job_dir, base_url):
        calls.append({"task": task, "job_dir": job_dir, "base_url": base_url})
        quality_path = job_dir / "quality_report.json"
        evidence_path = job_dir / "evidence" / "index.json"
        server_module.JobStore(job_dir.parent)._write_json(
            quality_path,
            {
                "job_id": job_dir.name,
                "conclusion": "pass",
                "requires_human_review": True,
            },
        )
        server_module.JobStore(job_dir.parent)._write_json(
            evidence_path,
            {
                "job_id": job_dir.name,
                "download_policy": {"default_payload": "evidence-only"},
            },
        )
        return {
            "quality_report": {"path": str(quality_path), "conclusion": "pass"},
            "evidence": {"path": str(evidence_path)},
            "remote_task_id": "sweep_fake",
        }

    monkeypatch.setenv("FDTD_SWEEP_RPC_URL", "http://127.0.0.1:5999")
    monkeypatch.setattr(
        server_module,
        "run_deployed_sweep",
        fake_run_deployed_sweep,
        raising=False,
    )
    app = server_module.create_app(
        fake_session,
        job_store=server_module.JobStore(tmp_path / "jobs", code_version="test-sha"),
    )
    app.config.update(TESTING=True)
    client = app.test_client()

    response = client.post(
        "/jobs/start",
        json={
            "mode": "real",
            "job_type": "metasurface-sweep",
            "approval": {"approved": True, "approved_for": "real_run"},
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["status"]["state"] == "succeeded"
    assert payload["summary"]["quality_report"]["conclusion"] == "pass"
    assert calls[0]["base_url"] == "http://127.0.0.1:5999"
    assert calls[0]["task"]["operation"] == "metasurface-sweep"


def test_real_metasurface_sweep_defaults_to_port_5005(
    server_module,
    fake_session,
    tmp_path,
    monkeypatch,
):
    calls = []

    def fake_run_deployed_sweep(task, job_dir, base_url):
        calls.append(base_url)
        return {"remote_task_id": "sweep_fake"}

    monkeypatch.delenv("FDTD_SWEEP_RPC_URL", raising=False)
    monkeypatch.setattr(
        server_module,
        "run_deployed_sweep",
        fake_run_deployed_sweep,
    )

    executor = server_module._job_executor(
        {"mode": "real", "job_type": "metasurface-sweep"},
        fake_session,
    )
    executor(
        {
            "task_id": "task_0001",
            "operation": "metasurface-sweep",
            "input": {},
        },
        tmp_path,
    )

    assert calls == ["http://127.0.0.1:5005"]
