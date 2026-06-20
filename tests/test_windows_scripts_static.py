"""Static analysis tests for Windows scripts.

These tests verify Windows PowerShell/batch scripts contain expected patterns
without requiring Windows execution. Tests parse script text only.
"""

import re
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent.parent / "scripts" / "windows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# — .bat entrypoint tests —


def test_restart_rpc_bat_calls_manage_rpc_ps1():
    content = _read(SCRIPT_DIR / "restart_rpc.bat")
    assert "manage_rpc.ps1" in content
    assert "-Action Restart" in content


def test_start_rpc_bat_calls_manage_rpc_ps1():
    content = _read(SCRIPT_DIR / "start_rpc.bat")
    assert "manage_rpc.ps1" in content
    assert "-Action Start" in content


def test_status_rpc_bat_calls_manage_rpc_ps1():
    content = _read(SCRIPT_DIR / "status_rpc.bat")
    assert "manage_rpc.ps1" in content
    assert "-Action Status" in content


def test_stop_rpc_bat_calls_manage_rpc_ps1():
    content = _read(SCRIPT_DIR / "stop_rpc.bat")
    assert "manage_rpc.ps1" in content
    assert "-Action Stop" in content


def test_setup_rpc_bat_calls_setup_rpc_ps1():
    content = _read(SCRIPT_DIR / "setup_rpc.bat")
    assert "setup_rpc.ps1" in content


# — manage_rpc.ps1 static checks —


def test_manage_rpc_uses_localappdata_state_root():
    content = _read(SCRIPT_DIR / "manage_rpc.ps1")
    assert "LOCALAPPDATA" in content
    assert "fdtd-mcp" in content


def test_manage_rpc_loads_rpc_env():
    content = _read(SCRIPT_DIR / "manage_rpc.ps1")
    assert "rpc.env" in content
    assert "ConfigFile" in content


def test_manage_rpc_uses_pythonw():
    content = _read(SCRIPT_DIR / "manage_rpc.ps1")
    assert "pythonw.exe" in content
    assert "Launcher" in content


def test_manage_rpc_uses_state_run_dir_for_pid():
    content = _read(SCRIPT_DIR / "manage_rpc.ps1")
    assert "rpc_server.pid" in content
    assert "RunDir" in content


def test_manage_rpc_uses_state_logs_dir():
    content = _read(SCRIPT_DIR / "manage_rpc.ps1")
    assert "rpc_server.out.log" in content
    assert "LogDir" in content


# — setup_rpc.ps1 static checks —


def test_setup_rpc_writes_to_localappdata_fdtd_mcp_config():
    content = _read(SCRIPT_DIR / "setup_rpc.ps1")
    assert "LOCALAPPDATA" in content
    assert "fdtd-mcp" in content
    assert "config" in content
    assert "rpc.env" in content


def test_setup_rpc_excludes_feishu_webhook_from_env_file():
    content = _read(SCRIPT_DIR / "setup_rpc.ps1")
    assert "Do not store secrets" in content
    # FDTD_FEISHU_WEBHOOK must NOT be written to rpc.env config content.
    # It may be mentioned in comments instructing users where to set it.
    # Check that the config content block does not contain FDTD_FEISHU_WEBHOOK:
    config_block_start = content.index('$configContent = @"')
    config_block_end = content.index('"@', config_block_start + 20)
    config_block = content[config_block_start:config_block_end]
    assert "FDTD_FEISHU_WEBHOOK" not in config_block


def test_setup_rpc_has_help():
    content = _read(SCRIPT_DIR / "setup_rpc.ps1")
    assert "-Help" in content or "Help" in content


def test_setup_rpc_verifies_lumapi():
    content = _read(SCRIPT_DIR / "setup_rpc.ps1")
    assert "import lumapi" in content


def test_setup_rpc_uses_pythonw():
    content = _read(SCRIPT_DIR / "setup_rpc.ps1")
    assert "pythonw.exe" in content


# — manage_rpc.ps1 help/usage —


def test_manage_rpc_has_action_validate_set():
    content = _read(SCRIPT_DIR / "manage_rpc.ps1")
    assert 'ValidateSet' in content
    assert '"Start"' in content
    assert '"Stop"' in content
    assert '"Status"' in content
    assert '"Restart"' in content
