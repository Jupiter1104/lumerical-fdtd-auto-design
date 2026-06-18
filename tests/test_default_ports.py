from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_native_rpc_defaults_to_port_5000():
    server = (ROOT / "rpc_server.py").read_text(encoding="utf-8")
    manager = (ROOT / "scripts/windows/manage_rpc.ps1").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/v1_smoke_test.py").read_text(encoding="utf-8")

    assert "default=5000" in server
    assert "Server port (default: 5000)" in server
    assert "} else {\n    5000\n}" in manager
    assert 'default="http://127.0.0.1:5000"' in smoke
    assert "RPC Server URL (default: http://127.0.0.1:5000)" in smoke
