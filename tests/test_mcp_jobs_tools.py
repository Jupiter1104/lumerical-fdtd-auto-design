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
