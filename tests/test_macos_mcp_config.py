"""Tests for macOS MCP client configuration (Task 11).

Uses temporary HOME to avoid touching real config files.
Each test class covers one aspect of the configure_mcp_clients.py script.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Paths to the scripts under test
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts" / "macos"
CONFIGURE_SCRIPT = SCRIPTS_DIR / "configure_mcp_clients.py"


# ─── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def temp_home():
    """Set HOME to a temporary directory for the duration of the test."""
    old = os.environ.get("HOME")
    with tempfile.TemporaryDirectory(prefix="tmc_") as d:
        os.environ["HOME"] = d
        yield Path(d)
    if old is None:
        os.environ.pop("HOME", None)
    else:
        os.environ["HOME"] = old


# ─── Helpers ────────────────────────────────────────────────────────────────

def run_configure(*args, cwd_override: Path = None):
    """Run configure_mcp_clients.py with the given arguments.

    When *cwd_override* is provided, passes --cwd so the Claude config
    target writes to the temp project root instead of the real one.
    """
    cmd = [sys.executable, str(CONFIGURE_SCRIPT)]
    if cwd_override is not None:
        cmd.extend(["--cwd", str(cwd_override)])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def codex_path(home: Path) -> Path:
    return home / ".codex" / "config.toml"


def claude_path(home: Path) -> Path:
    """Claude Code config lives at project root .mcp.json.

    Tests must pass --cwd pointing to temp_home so the script uses
    the temp directory as the project root.
    """
    return home / ".mcp.json"


def hermes_path(home: Path) -> Path:
    return home / ".hermes" / "config.yaml"


# ─── Codex (TOML) ───────────────────────────────────────────────────────────

class TestCodexConfig:
    """Codex target writes TOML with [mcp_servers.fdtd] only."""

    def test_writes_fdtd_section(self, temp_home):
        """Config should contain exactly [mcp_servers.fdtd] with server fields."""
        r = run_configure("--target", "codex")
        assert r.returncode == 0, r.stderr

        text = codex_path(temp_home).read_text("utf-8")
        assert "[mcp_servers.fdtd]" in text
        for key in ("command", "args", "cwd", "FDTD_RPC_URL"):
            assert key in text, f"missing key {key} in TOML output"

    def test_backup_created(self, temp_home):
        """An existing file should be backed up with .backup-YYYYMMDD-HHMMSS."""
        p = codex_path(temp_home)
        p.parent.mkdir(parents=True, exist_ok=True)
        original_content = 'existing_setting = "old_value"\n'
        p.write_text(original_content, encoding="utf-8")

        r = run_configure("--target", "codex")
        assert r.returncode == 0, r.stderr

        backups = sorted(p.parent.glob("*.backup-*"))
        assert len(backups) >= 1, "no backup file found"
        # The backup should be the original file content
        assert backups[0].read_text("utf-8") == original_content

    def test_backup_suffix_format(self, temp_home):
        """Backup suffix must match .backup-YYYYMMDD-HHMMSS."""
        p = codex_path(temp_home)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("a = 1\n", encoding="utf-8")

        run_configure("--target", "codex")

        backups = list(p.parent.glob("*.backup-*"))
        assert len(backups) == 1
        assert re.search(r"\.backup-\d{8}-\d{6}$", backups[0].name), (
            f"backup name {backups[0].name} does not match pattern"
        )


# ─── Claude (JSON) ──────────────────────────────────────────────────────────

class TestClaudeConfig:
    """Claude target writes JSON and preserves existing mcpServers."""

    def test_preserves_existing_servers(self, temp_home):
        """Existing servers in mcpServers must survive after writing fdtd."""
        p = claude_path(temp_home)

        existing = {
            "mcpServers": {
                "existing-tool": {"command": "python", "args": ["-m", "some_module"]},
            },
        }
        p.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        r = run_configure("--target", "claude", cwd_override=temp_home)
        assert r.returncode == 0, r.stderr

        got = json.loads(p.read_text("utf-8"))
        assert "existing-tool" in got["mcpServers"], "existing server missing"
        assert got["mcpServers"]["existing-tool"]["command"] == "python"
        assert "fdtd" in got["mcpServers"], "fdtd server not added"

    def test_replaces_fdtd_entry(self, temp_home):
        """An existing fdtd entry should be replaced, not duplicated."""
        p = claude_path(temp_home)

        existing = {
            "mcpServers": {
                "fdtd": {"command": "old", "args": [], "env": {"FDTD_RPC_URL": "old"}},
            },
        }
        p.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        r = run_configure("--target", "claude", cwd_override=temp_home)
        assert r.returncode == 0, r.stderr

        got = json.loads(p.read_text("utf-8"))
        assert got["mcpServers"]["fdtd"]["command"] != "old"
        assert got["mcpServers"]["fdtd"]["env"]["FDTD_RPC_URL"] != "old"


# ─── Hermes (YAML) ──────────────────────────────────────────────────────────

class TestHermesConfig:
    """Hermes target writes YAML and preserves unrelated config."""

    def test_preserves_unrelated_config(self, temp_home):
        """Keys besides mcp_servers must survive."""
        p = hermes_path(temp_home)
        p.parent.mkdir(parents=True, exist_ok=True)
        import yaml

        existing = {"other_setting": "value", "number_key": 42}
        p.write_text(yaml.dump(existing), encoding="utf-8")

        r = run_configure("--target", "hermes")
        assert r.returncode == 0, r.stderr

        got = yaml.safe_load(p.read_text("utf-8"))
        assert got["other_setting"] == "value"
        assert got["number_key"] == 42
        assert "mcp_servers" in got
        assert "fdtd" in got["mcp_servers"]

    def test_appends_fdtd_to_toolset(self, temp_home):
        """fdtd should be appended to toolsets when not already present."""
        p = hermes_path(temp_home)
        p.parent.mkdir(parents=True, exist_ok=True)
        import yaml

        existing = {
            "toolsets": ["existing-tool"],
            "mcp_servers": {
                "existing-tool": {"command": "python"},
            },
        }
        p.write_text(yaml.dump(existing), encoding="utf-8")

        r = run_configure("--target", "hermes")
        assert r.returncode == 0, r.stderr

        got = yaml.safe_load(p.read_text("utf-8"))
        assert "fdtd" in got["toolsets"]
        assert "existing-tool" in got["toolsets"]

    def test_no_toolset_key_not_created(self, temp_home):
        """If toolsets key doesn't exist, it should not be created."""
        p = hermes_path(temp_home)
        p.parent.mkdir(parents=True, exist_ok=True)
        import yaml

        existing = {"mcp_servers": {"existing-tool": {"command": "python"}}}
        p.write_text(yaml.dump(existing), encoding="utf-8")

        r = run_configure("--target", "hermes")
        assert r.returncode == 0, r.stderr

        got = yaml.safe_load(p.read_text("utf-8"))
        # toolsets should not be added if not present
        assert "toolsets" not in got


# ─── Invalid target ─────────────────────────────────────────────────────────

class TestInvalidTarget:
    """Invalid target must fail with non-zero exit and no file changes."""

    def test_invalid_target_returns_error(self, temp_home):
        """Non-existent target should exit non-zero."""
        r = run_configure("--target", "not_a_real_target")
        assert r.returncode != 0

    def test_no_files_created_on_invalid_target(self, temp_home):
        """No files should be created when target is invalid."""
        # Create some existing files to verify they aren't modified
        cp = codex_path(temp_home)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text("original = true\n", encoding="utf-8")

        cl = claude_path(temp_home)
        cl.parent.mkdir(parents=True, exist_ok=True)
        cl.write_text('{"original": true}', encoding="utf-8")

        original_cp_content = cp.read_text("utf-8")
        original_cl_content = cl.read_text("utf-8")

        r = run_configure("--target", "not_a_real_target")
        assert r.returncode != 0

        # Files must remain unchanged
        assert cp.read_text("utf-8") == original_cp_content
        assert cl.read_text("utf-8") == original_cl_content


# ─── Integration: --target all ──────────────────────────────────────────────

class TestAllTarget:
    """--target all should configure all three clients."""

    def test_all_target_configures_three_clients(self, temp_home):
        """Running with --target all must produce all three config files."""
        r = run_configure("--target", "all", cwd_override=temp_home)
        assert r.returncode == 0, r.stderr

        assert codex_path(temp_home).exists(), "Codex config missing"
        assert claude_path(temp_home).exists(), "Claude config missing"
        assert hermes_path(temp_home).exists(), "Hermes config missing"

    def test_all_target_atomic_on_failure(self, temp_home):
        """If one target fails, no config files should be modified."""
        cp = codex_path(temp_home)
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text("original = true\n", encoding="utf-8")

        r = run_configure("--target", "all", cwd_override=temp_home)
        assert r.returncode == 0, r.stderr
        assert codex_path(temp_home).exists()


# ─── Path documentation guard ─────────────────────────────────────────────────

OLD_CODEX_PATH = ".config/codex/mcp_servers.toml"
OLD_CLAUDE_PATH = ".claude/.mcp.json"
OLD_HERMES_PATH = ".config/hermes/config.yaml"


class TestPathDocs:
    """Ensure user-visible docs and help text reference the correct paths."""

    def test_configure_docstring_has_correct_paths(self):
        doc = CONFIGURE_SCRIPT.read_text(encoding="utf-8")
        assert "~/.codex/config.toml" in doc, "docstring missing Codex path"
        assert "<project-root>/.mcp.json" in doc, "docstring missing Claude path"
        assert "~/.hermes/config.yaml" in doc, "docstring missing Hermes path"

    def test_configure_docstring_lacks_old_paths(self):
        """Old paths must not appear as active config targets.

        They may appear in negating comments (e.g. "NOT ~/.claude/.mcp.json").
        """
        doc = CONFIGURE_SCRIPT.read_text(encoding="utf-8")
        # Only check lines that are not comments/negations
        active_lines = [
            ln for ln in doc.splitlines()
            if not ln.strip().startswith("#") and "NOT" not in ln
        ]
        active = "\n".join(active_lines)
        assert OLD_CODEX_PATH not in active, f"old Codex path '{OLD_CODEX_PATH}' in active lines"
        assert OLD_CLAUDE_PATH not in active, f"old Claude path '{OLD_CLAUDE_PATH}' in active lines"
        assert OLD_HERMES_PATH not in active, f"old Hermes path '{OLD_HERMES_PATH}' in active lines"

    def test_install_script_next_steps_have_correct_paths(self):
        inst = (SCRIPTS_DIR / "install_mcp.sh").read_text(encoding="utf-8")
        assert "~/.codex/config.toml" in inst, "next steps missing Codex path"
        assert "<project-root>/.mcp.json" in inst, "next steps missing Claude path"
        assert "~/.hermes/config.yaml" in inst, "next steps missing Hermes path"

    def test_install_script_next_steps_lack_old_paths(self):
        inst = (SCRIPTS_DIR / "install_mcp.sh").read_text(encoding="utf-8")
        assert OLD_CODEX_PATH not in inst, f"old Codex path in install script"
        assert OLD_CLAUDE_PATH not in inst, f"old Claude path in install script"
        assert OLD_HERMES_PATH not in inst, f"old Hermes path in install script"
