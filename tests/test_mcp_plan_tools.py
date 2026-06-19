from src.tools.plans import register_plan_tools


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

    def jobs_start(self, request):
        self.calls.append(("jobs_start", request))
        return {
            "ok": True,
            "job_id": "job_mock",
            "task_count": 4,
            "summary": {
                "quality_report": {"conclusion": "pass"},
                "evidence": {"index": "evidence/index.json"},
            },
        }


def registered_tools():
    mcp = FakeMcp()
    rpc = FakeRpc()
    register_plan_tools(mcp, rpc)
    return mcp.tools, rpc


def test_validate_and_approve_are_local_only():
    tools, rpc = registered_tools()

    validated = tools["fdtd_simulation_plan_validate"]({})
    approved = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )

    assert validated["ok"] is True
    assert approved["ok"] is True
    assert rpc.calls == []


def test_mock_start_requires_plan_approval_without_rpc_call():
    tools, rpc = registered_tools()

    response = tools["fdtd_simulation_plan_start"](
        plan={},
        plan_approval=None,
        mode="mock",
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "plan_approval_required"
    assert rpc.calls == []


def test_approved_mock_compiles_and_calls_jobs_start_once():
    tools, rpc = registered_tools()
    validated = tools["fdtd_simulation_plan_validate"]({})
    approval = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]

    response = tools["fdtd_simulation_plan_start"](
        plan=validated["normalized_plan"],
        plan_approval=approval,
        mode="mock",
    )

    assert response["ok"] is True
    assert response["job_id"] == "job_mock"
    assert len(rpc.calls) == 1
    request = rpc.calls[0][1]
    assert request["mode"] == "mock"
    assert request["job_type"] == "metasurface-sweep"
    assert "approval" not in request


def test_changed_plan_rejects_old_approval_without_rpc_call():
    tools, rpc = registered_tools()
    validated = tools["fdtd_simulation_plan_validate"]({})
    approval = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]

    response = tools["fdtd_simulation_plan_start"](
        plan={"sweep": {"ratio_values": [0.2, 0.5]}},
        plan_approval=approval,
        mode="mock",
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "plan_fingerprint_mismatch"
    assert rpc.calls == []


def test_real_is_locally_rejected_without_second_approval():
    tools, rpc = registered_tools()
    validated = tools["fdtd_simulation_plan_validate"]({})
    approval = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]

    response = tools["fdtd_simulation_plan_start"](
        plan=validated["normalized_plan"],
        plan_approval=approval,
        mode="real",
    )

    assert response["ok"] is False
    assert response["error"]["type"] == "real_run_approval_required"
    assert rpc.calls == []


def test_real_preflight_is_local_only_and_does_not_call_rpc():
    from tests.test_template_contract import valid_b1_contract

    tools, rpc = registered_tools()
    validated = tools["fdtd_simulation_plan_validate"]({})
    approval = tools["fdtd_simulation_plan_approve"](
        validated["normalized_plan"],
        validated["plan_fingerprint"],
    )["approval"]

    packet = tools["fdtd_simulation_plan_real_preflight"](
        plan=validated["normalized_plan"],
        plan_approval=approval,
        template_contract=valid_b1_contract(),
    )

    assert packet["ok"] is True
    assert packet["status"] == "ready_for_human_approval"
    assert packet["task_count"] == 4
    assert rpc.calls == []


def test_real_preflight_rejects_without_plan_approval_and_does_not_call_rpc():
    from tests.test_template_contract import valid_b1_contract

    tools, rpc = registered_tools()

    packet = tools["fdtd_simulation_plan_real_preflight"](
        plan={},
        plan_approval=None,
        template_contract=valid_b1_contract(),
    )

    assert packet["ok"] is False
    assert packet["error"]["type"] == "plan_approval_required"
    assert rpc.calls == []
