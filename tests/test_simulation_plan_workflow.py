from rpc_server import create_app
from src.job_store import JobStore
from src.tools.plans import register_plan_tools


class FakeMcp:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class FlaskRpcAdapter:
    def __init__(self, client):
        self.client = client
        self.calls = []

    def jobs_start(self, request):
        self.calls.append(request)
        return self.client.post("/jobs/start", json=request).get_json()


class FakeSession:
    @property
    def is_connected(self):
        return False

    def status(self):
        return {"connected": False, "version": None, "model_file": None}


def test_natural_language_agent_plan_to_approved_persistent_mock(tmp_path):
    app = create_app(
        FakeSession(),
        job_store=JobStore(tmp_path / "jobs", code_version="test-sha"),
    )
    app.config.update(TESTING=True)
    rpc = FlaskRpcAdapter(app.test_client())
    mcp = FakeMcp()
    register_plan_tools(mcp, rpc)

    # Claude/Codex has translated:
    # "Use CPU to sweep metasurface unit-cell ratio and period."
    draft = {
        "intent": {
            "summary": (
                "Use CPU to sweep metasurface unit-cell ratio and period."
            )
        },
        "execution": {"resource": "CPU"},
    }
    validated = mcp.tools["fdtd_simulation_plan_validate"](draft)
    assert validated["ok"] is True
    assert validated["task_count"] == 4
    assert validated["defaults_applied"]
    assert validated["assumptions"]

    approved = mcp.tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )
    response = mcp.tools["fdtd_simulation_plan_start"](
        plan=validated["normalized_plan"],
        plan_approval=approved["approval"],
        mode="mock",
    )

    assert response["ok"] is True
    assert response["task_count"] == 4
    assert response["summary"]["task_counts"]["succeeded"] == 4
    assert response["summary"]["quality_report"]["conclusion"] == "pass"
    assert response["summary"]["evidence"]["download_policy"][
        "default_payload"
    ] == "evidence-only"
    assert all(item["synthetic"] for item in response["summary"]["results"])
    assert len(rpc.calls) == 1
