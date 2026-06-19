import importlib
import sys
import threading
from unittest.mock import patch

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


def test_real_sweep_start_returns_202_before_runner_finishes(
    server_module,
    fake_session,
    tmp_path,
):
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    started = threading.Event()
    release = threading.Event()

    class BlockingRunner:
        def run(self, job_id):
            started.job_id = job_id
            started.set()
            release.wait(timeout=2)

    app = server_module.create_app(
        fake_session,
        job_store=server_module.JobStore(tmp_path / "jobs", code_version="test-sha"),
        sweep_runner=BlockingRunner(),
    )
    app.config.update(TESTING=True)
    client = app.test_client()

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
            "approval": {"approved": True, "approved_for": "real_run"},
        },
    )

    try:
        payload = response.get_json()
        assert response.status_code == 202
        assert payload["ok"] is True
        assert payload["state"] == "queued"
        assert started.wait(timeout=1)
        assert payload["job_id"] == started.job_id
    finally:
        release.set()


def test_real_sweep_rejects_second_start_while_running(
    server_module,
    fake_session,
    tmp_path,
):
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    started = threading.Event()
    release = threading.Event()

    class BlockingRunner:
        def run(self, job_id):
            started.set()
            release.wait(timeout=2)

    app = server_module.create_app(
        fake_session,
        job_store=server_module.JobStore(tmp_path / "jobs", code_version="test-sha"),
        sweep_runner=BlockingRunner(),
    )
    app.config.update(TESTING=True)
    client = app.test_client()
    body = {
        "mode": "real",
        "job_type": "metasurface-sweep",
        "sweep": {
            "template": str(template),
            "config": {"RATIO_LIST": [0.2], "PERIOD_LIST": [390e-9]},
        },
        "approval": {"approved": True, "approved_for": "real_run"},
    }

    try:
        first = client.post("/jobs/start", json=body)
        assert first.status_code == 202
        assert started.wait(timeout=1)

        second = client.post("/jobs/start", json={**body, "idempotency_key": "two"})

        assert second.status_code == 409
        assert second.get_json()["error"]["type"] == "sweep_already_running"
    finally:
        release.set()


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/model/load", {"file_path": "a.fsp"}),
        ("/geometry/rectangle", {"name": "wg"}),
        ("/session/close", {}),
    ],
)
def test_destructive_routes_reject_while_real_sweep_is_running(
    server_module,
    fake_session,
    tmp_path,
    path,
    body,
):
    template = tmp_path / "base_model.fsp"
    template.write_bytes(b"template")
    started = threading.Event()
    release = threading.Event()

    class BlockingRunner:
        def run(self, job_id):
            started.set()
            release.wait(timeout=2)

    app = server_module.create_app(
        fake_session,
        job_store=server_module.JobStore(tmp_path / "jobs", code_version="test-sha"),
        sweep_runner=BlockingRunner(),
    )
    app.config.update(TESTING=True)
    client = app.test_client()

    try:
        response = client.post(
            "/jobs/start",
            json={
                "mode": "real",
                "job_type": "metasurface-sweep",
                "sweep": {
                    "template": str(template),
                    "config": {"RATIO_LIST": [0.2], "PERIOD_LIST": [390e-9]},
                },
                "approval": {"approved": True, "approved_for": "real_run"},
            },
        )
        assert response.status_code == 202
        assert started.wait(timeout=1)

        blocked = client.post(path, json=body)

        assert blocked.status_code == 409
        assert blocked.get_json()["error"]["type"] == "sweep_running"
    finally:
        release.set()


def test_real_metasurface_sweep_rejects_missing_template(
    client,
    tmp_path,
):
    response = client.post(
        "/jobs/start",
        json={
            "mode": "real",
            "job_type": "metasurface-sweep",
            "sweep": {
                "template": str(tmp_path / "missing.fsp"),
                "config": {"RATIO_LIST": [0.2], "PERIOD_LIST": [390e-9]},
            },
            "approval": {"approved": True, "approved_for": "real_run"},
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["type"] == "template_not_found"


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

    store = JobStore(
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
