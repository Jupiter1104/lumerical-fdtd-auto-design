"""Tests for official Object Library analysis group creation."""

import importlib
import sys

import pytest

from src.windows_fdtd_adapter import AdapterError, WindowsFdtdAdapter


class FakeBackend:
    def __init__(self):
        self.scripts = []

    def eval(self, script):
        self.scripts.append(script)
        return "ok"


def test_prefer_builtin_with_script_id_uses_addobject_dry_run():
    adapter = WindowsFdtdAdapter(FakeBackend())

    result = adapter.analysis_group_create(
        name="analysis_builtin",
        properties={"x": 0},
        dry_run=True,
        prefer_builtin=True,
        script_id="power_transmission_box",
    )

    assert 'addobject("power_transmission_box");' in result["script"]
    assert 'set("name","analysis_builtin");' in result["script"]
    assert 'set("x",0);' in result["script"]
    assert "addanalysisgroup;" not in result["script"]
    assert result["source"] == "builtin"
    assert result["script_id"] == "power_transmission_box"
    assert result["fallback_used"] is False


def test_prefer_builtin_without_script_id_falls_back_to_custom_dry_run():
    adapter = WindowsFdtdAdapter(FakeBackend())

    result = adapter.analysis_group_create(
        name="analysis_custom",
        properties={},
        dry_run=True,
        prefer_builtin=True,
    )

    assert "addanalysisgroup;" in result["script"]
    assert "addobject(" not in result["script"]
    assert result["source"] == "custom"
    assert result["script_id"] == ""
    assert result["fallback_used"] is True


def test_require_builtin_without_script_id_raises_structured_error():
    adapter = WindowsFdtdAdapter(FakeBackend())

    with pytest.raises(AdapterError) as exc_info:
        adapter.analysis_group_create(
            name="analysis_required",
            properties={},
            require_builtin=True,
        )

    assert exc_info.value.error_type == "builtin_analysis_group_required"
    assert exc_info.value.status_code == 400


@pytest.fixture
def server_module():
    sys.modules.pop("rpc_server", None)
    return importlib.import_module("rpc_server")


def test_analysis_group_route_passes_builtin_fields_to_adapter(server_module):
    backend = FakeBackend()
    app = server_module.create_app(backend=backend)
    app.config.update(TESTING=True)

    response = app.test_client().post("/analysis-groups", json={
        "name": "analysis_builtin",
        "properties": {},
        "dry_run": True,
        "prefer_builtin": True,
        "script_id": "power_transmission_box",
    })

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["source"] == "builtin"
    assert payload["script_id"] == "power_transmission_box"
    assert 'addobject("power_transmission_box");' in payload["script"]
