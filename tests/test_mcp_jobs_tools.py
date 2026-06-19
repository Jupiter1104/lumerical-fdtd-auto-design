from src.tools.jobs import register_job_tools


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FakeRpc:
    def __init__(self):
        self.calls = []

    def jobs_plan(self, request):
        self.calls.append(("jobs_plan", request))
        return {"ok": True, "route": "plan", "request": request}

    def jobs_start(self, request):
        self.calls.append(("jobs_start", request))
        return {"ok": True, "route": "start", "request": request}

    def jobs_get(self, job_id):
        self.calls.append(("jobs_get", job_id))
        return {"ok": True, "job_id": job_id}

    def jobs_tasks(self, job_id):
        self.calls.append(("jobs_tasks", job_id))
        return {"ok": True, "job_id": job_id, "tasks": []}

    def jobs_resume(self, job_id, request=None):
        self.calls.append(("jobs_resume", job_id, request))
        return {"ok": True, "job_id": job_id, "request": request or {}}


def registered_tools():
    mcp = FakeMcp()
    rpc = FakeRpc()
    register_job_tools(mcp, rpc)
    return mcp.tools, rpc


def test_generic_job_tools_call_rpc_jobs_methods():
    tools, rpc = registered_tools()
    request = {"mode": "mock", "job_type": "geometry-smoke"}

    assert tools["fdtd_job_plan"](request) == {
        "ok": True,
        "route": "plan",
        "request": request,
    }
    assert tools["fdtd_job_start"](request) == {
        "ok": True,
        "route": "start",
        "request": request,
    }
    assert tools["fdtd_job_status"]("job_1") == {"ok": True, "job_id": "job_1"}
    assert tools["fdtd_job_tasks"]("job_1") == {
        "ok": True,
        "job_id": "job_1",
        "tasks": [],
    }
    assert tools["fdtd_job_resume"]("job_1") == {
        "ok": True,
        "job_id": "job_1",
        "request": {},
    }

    assert rpc.calls == [
        ("jobs_plan", request),
        ("jobs_start", request),
        ("jobs_get", "job_1"),
        ("jobs_tasks", "job_1"),
        ("jobs_resume", "job_1", None),
    ]


from src.tools.jobs import build_metasurface_sweep_request


def test_build_metasurface_sweep_request_defaults_to_cpu_mock_grid():
    request = build_metasurface_sweep_request(
        mode="mock",
        ratio_list=None,
        period_list=None,
        base_height=700e-9,
        base_period=470e-9,
        phases=None,
        template="templates/metasurface/base_model.fsp",
        include_models=False,
        approved=False,
    )

    assert request == {
        "mode": "mock",
        "job_type": "metasurface-sweep",
        "sweep": {
            "template": "templates/metasurface/base_model.fsp",
            "phases": [1, 2, 3, 4],
            "hide": True,
            "include_models": False,
            "config": {
                "SWEEP_Y_AXIS": "period",
                "RATIO_LIST": [0.2, 0.8],
                "PERIOD_LIST": [390e-9, 540e-9],
                "BASE_HEIGHT": 700e-9,
                "BASE_PERIOD": 470e-9,
                "FDTD_PROCESSES": 1,
                "FDTD_CAPACITY": 1,
                "EXPRESS_MODE": 0,
            },
        },
    }


def test_build_metasurface_sweep_request_rejects_unapproved_real_run():
    request = build_metasurface_sweep_request(
        mode="real",
        ratio_list=[0.2],
        period_list=[390e-9],
        base_height=700e-9,
        base_period=470e-9,
        phases=[1, 2, 3, 4],
        template="templates/metasurface/base_model.fsp",
        include_models=False,
        approved=False,
    )

    assert request["ok"] is False
    assert request["error"]["type"] == "approval_required"


def test_build_metasurface_sweep_request_adds_real_run_approval_when_approved():
    request = build_metasurface_sweep_request(
        mode="real",
        ratio_list=[0.2],
        period_list=[390e-9],
        base_height=700e-9,
        base_period=470e-9,
        phases=[1, 2, 3, 4],
        template="templates/metasurface/base_model.fsp",
        include_models=False,
        approved=True,
    )

    assert request["approval"] == {"approved": True, "approved_for": "real_run"}
    assert request["sweep"]["config"]["RATIO_LIST"] == [0.2]
    assert request["sweep"]["config"]["PERIOD_LIST"] == [390e-9]


def test_metasurface_plan_tool_calls_jobs_plan():
    tools, rpc = registered_tools()

    response = tools["fdtd_metasurface_sweep_plan"]()

    assert response["ok"] is True
    assert response["route"] == "plan"
    request = rpc.calls[-1][1]
    assert request["mode"] == "plan"
    assert request["job_type"] == "metasurface-sweep"
    assert request["sweep"]["config"]["EXPRESS_MODE"] == 0


def test_metasurface_start_defaults_to_mock_without_approval():
    tools, rpc = registered_tools()

    response = tools["fdtd_metasurface_sweep_start"]()

    assert response["ok"] is True
    assert response["route"] == "start"
    request = rpc.calls[-1][1]
    assert request["mode"] == "mock"
    assert "approval" not in request


def test_metasurface_start_refuses_unapproved_real_without_rpc_call():
    tools, rpc = registered_tools()

    response = tools["fdtd_metasurface_sweep_start"](mode="real", approved=False)

    assert response["ok"] is False
    assert response["error"]["type"] == "approval_required"
    assert rpc.calls == []


def test_metasurface_start_sends_real_approval_when_approved():
    tools, rpc = registered_tools()

    response = tools["fdtd_metasurface_sweep_start"](
        mode="real",
        ratio_list=[0.2],
        period_list=[390e-9],
        approved=True,
    )

    assert response["ok"] is True
    request = rpc.calls[-1][1]
    assert request["approval"] == {"approved": True, "approved_for": "real_run"}
    assert request["sweep"]["config"]["RATIO_LIST"] == [0.2]
    assert request["sweep"]["config"]["PERIOD_LIST"] == [390e-9]


from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_legacy_sweep_tools_are_marked_as_legacy():
    text = (ROOT / "src/tools/simulation.py").read_text(encoding="utf-8")

    assert "Legacy compatibility tools" in text
    assert "Prefer fdtd_job_* and fdtd_metasurface_sweep_*" in text
