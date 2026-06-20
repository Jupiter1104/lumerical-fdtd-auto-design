"""Tests for analysis group MCP tool wrappers."""

from src.tools.analysis_groups import register_analysis_group_tools


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

    def analysis_group_create(
        self,
        name,
        properties,
        dry_run=False,
        prefer_builtin=False,
        require_builtin=False,
        script_id="",
        analysis_intent=None,
        recipe_context=None,
        parameter_overrides=None,
    ):
        self.calls.append((
            "analysis_group_create",
            name,
            properties,
            dry_run,
            prefer_builtin,
            require_builtin,
            script_id,
            analysis_intent,
            recipe_context,
            parameter_overrides,
        ))
        return {"ok": True, "name": name}

    def analysis_group_get(self, name):
        self.calls.append(("analysis_group_get", name))
        return {"ok": True, "name": name}

    def analysis_group_update(self, name, body):
        self.calls.append(("analysis_group_update", name, body))
        return {"ok": True, "name": name}


def registered_tools():
    mcp = FakeMcp()
    rpc = FakeRpc()
    register_analysis_group_tools(mcp, rpc)
    return mcp.tools, rpc


def test_analysis_group_create_tool_extracts_body_fields():
    tools, rpc = registered_tools()

    response = tools["fdtd_analysis_group_create"]({
        "name": "analysis_builtin",
        "properties": {"x": 0},
        "dry_run": True,
        "prefer_builtin": True,
        "require_builtin": False,
        "script_id": "power_transmission_box",
        "analysis_intent": {"kind": "transmission", "outputs": ["T"]},
        "recipe_context": {"outputs": ["T"]},
        "parameter_overrides": {"x span": 2e-6},
    })

    assert response == {"ok": True, "name": "analysis_builtin"}
    assert rpc.calls == [(
        "analysis_group_create",
        "analysis_builtin",
        {"x": 0},
        True,
        True,
        False,
        "power_transmission_box",
        {"kind": "transmission", "outputs": ["T"]},
        {"outputs": ["T"]},
        {"x span": 2e-6},
    )]
