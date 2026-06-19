import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_claude_mcp_config_points_to_local_fdtd_server():
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))

    fdtd = config["mcpServers"]["fdtd"]
    assert fdtd["command"] == str(ROOT / ".venv/bin/python")
    assert fdtd["args"] == ["-m", "src.server"]
    assert fdtd["cwd"] == str(ROOT)
    assert fdtd["env"]["FDTD_RPC_URL"] == "http://localhost:5000"
