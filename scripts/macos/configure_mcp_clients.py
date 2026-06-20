#!/usr/bin/env python3
"""Configure MCP client configs (Codex, Claude, Hermes) for the FDTD server.

Writes to well-known configuration file locations:
  - Codex:   ~/.codex/config.toml              (TOML)
  - Claude:  <project-root>/.mcp.json           (JSON)
  - Hermes:  ~/.hermes/config.yaml              (YAML)

Usage:
  python configure_mcp_clients.py --target all
  python configure_mcp_clients.py --target codex --rpc-url http://localhost:5000
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# TOML parsing: Python 3.11+ has tomllib in stdlib
import tomllib

# YAML support via PyYAML (optional; required for --target hermes / all)
try:
    import yaml as _yaml
except ImportError:
    _yaml = None


# ─── Constants ───────────────────────────────────────────────────────────────

KNOWN_TARGETS = ("codex", "claude", "hermes")

# Relative paths under $HOME for each client config
# Claude Code uses the project-root .mcp.json, NOT ~/.claude/.mcp.json
CLIENT_PATHS = {
    "codex":  ".codex/config.toml",
    "claude": None,  # special: project-root .mcp.json, handled in config_path()
    "hermes": ".hermes/config.yaml",
}

BACKUP_SUFFIX_PATTERN = re.compile(r"\.backup-\d{8}-\d{6}$")


# ─── Path helpers ────────────────────────────────────────────────────────────

_project_root_override: Path | None = None


def project_root() -> Path:
    """Find the project root by walking up from this script's directory.

    The ``--cwd`` CLI argument sets an override via ``set_project_root_override``.
    """
    if _project_root_override is not None:
        return _project_root_override
    script = Path(__file__).resolve()
    for parent in script.parents:
        if (parent / ".mcp.json").exists() or (parent / "pyproject.toml").exists():
            return parent
    # fallback: two levels up from scripts/macos/
    return script.parent.parent.parent


def set_project_root_override(path: str | Path) -> None:
    """Override the auto-detected project root (used by tests)."""
    global _project_root_override
    _project_root_override = Path(path)


def home() -> Path:
    """Return $HOME as a Path."""
    return Path(os.environ["HOME"])


def config_path(target: str) -> Path:
    """Return the expected config file path for *target*.

    Codex and Hermes live under $HOME.
    Claude Code config lives at the project root (``.mcp.json``).
    """
    if target == "claude":
        return project_root() / ".mcp.json"
    return home() / CLIENT_PATHS[target]


def backup_path(path: Path) -> Path:
    """Return a backup path with a .backup-YYYYMMDD-HHMMSS suffix."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.parent / f"{path.name}.backup-{ts}"


# ─── Server entry builder ───────────────────────────────────────────────────

def build_server_entry(args) -> dict:
    """Build the fdtd MCP server entry dict."""
    return {
        "command": args.command,
        "args": args.args,
        "cwd": str(args.cwd),
        "env": {"FDTD_RPC_URL": args.rpc_url},
    }


# ─── Codex (TOML) writer ────────────────────────────────────────────────────

def read_toml(path: Path) -> dict:
    """Read an existing TOML file, returning {} if missing."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}


def render_codex_toml(config: dict) -> str:
    """Render the TOML output for Codex (only [mcp_servers.fdtd]).

    We build a minimal, deterministic TOML string manually rather than
    using a full TOML writer, since we only ever write the fdtd entry.
    """
    fdtd = config.get("mcp_servers", {}).get("fdtd", {})
    lines = ['[mcp_servers.fdtd]']

    # command: string
    lines.append(f"command = {json.dumps(fdtd['command'])}")

    # args: inline array
    lines.append(f"args = {json.dumps(fdtd['args'])}")

    # cwd: string
    lines.append(f"cwd = {json.dumps(fdtd['cwd'])}")

    # env: inline table  { KEY = "val", ... }
    env_pairs = ", ".join(
        f'{json.dumps(k)} = {json.dumps(v)}'
        for k, v in fdtd.get("env", {}).items()
    )
    lines.append(f"env = {{ {env_pairs} }}")

    return "\n".join(lines) + "\n"


# ─── Claude (JSON) writer ───────────────────────────────────────────────────

def read_json(path: Path) -> dict:
    """Read an existing JSON file, returning {} if missing."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def render_claude_json(config: dict) -> str:
    """Render the JSON output for Claude."""
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


# ─── Hermes (YAML) writer ───────────────────────────────────────────────────

def read_yaml(path: Path) -> dict:
    """Read an existing YAML file, returning {} if missing."""
    if _yaml is None:
        raise RuntimeError("PyYAML is required for Hermes config; install with: pip install pyyaml")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def merge_hermes_config(existing: dict, server_entry: dict) -> dict:
    """Merge the fdtd server entry into an existing Hermes config dict.

    Rules:
    - Preserve all top-level keys.
    - Add/update ``mcp_servers.fdtd``.
    - If ``toolsets`` exists and ``fdtd`` is not already present, append it.
    """
    result = dict(existing)

    # mcp_servers
    if "mcp_servers" not in result:
        result["mcp_servers"] = {}
    result["mcp_servers"]["fdtd"] = server_entry

    # toolsets: only append when the key already exists
    if "toolsets" in result:
        if "fdtd" not in result["toolsets"]:
            result["toolsets"].append("fdtd")

    return result


def render_hermes_yaml(config: dict) -> str:
    """Render the YAML output for Hermes."""
    if _yaml is None:
        raise RuntimeError("PyYAML is required for Hermes config")
    return _yaml.dump(config, default_flow_style=False, sort_keys=False)


# ─── Per-target dispatch ────────────────────────────────────────────────────

def read_config(target: str) -> dict:
    """Read the existing configuration for *target*."""
    path = config_path(target)
    if target == "codex":
        return read_toml(path)
    elif target == "claude":
        return read_json(path)
    elif target == "hermes":
        return read_yaml(path)
    raise ValueError(f"unknown target: {target}")


def merge_config(target: str, existing: dict, server_entry: dict) -> dict:
    """Merge *server_entry* into *existing* config for *target*.

    For codex: replace config with just [mcp_servers.fdtd].
    For claude: add/update mcpServers.fdtd in the existing JSON.
    For hermes: preserve all keys, add/update mcp_servers.fdtd,
                conditionally append to toolsets.
    """
    if target == "codex":
        # Codex config is replaced entirely with just the fdtd entry
        return {"mcp_servers": {"fdtd": server_entry}}
    elif target == "claude":
        result = dict(existing)
        if "mcpServers" not in result:
            result["mcpServers"] = {}
        result["mcpServers"]["fdtd"] = server_entry
        return result
    elif target == "hermes":
        return merge_hermes_config(existing, server_entry)
    raise ValueError(f"unknown target: {target}")


def render_config(target: str, config: dict) -> str:
    """Render *config* to a string for *target*."""
    if target == "codex":
        return render_codex_toml(config)
    elif target == "claude":
        return render_claude_json(config)
    elif target == "hermes":
        return render_hermes_yaml(config)
    raise ValueError(f"unknown target: {target}")


def write_config(target: str, rendered: str) -> Path:
    """Write *rendered* to the config path for *target*.

    Returns the path written to.
    """
    path = config_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temp file first, then atomically rename
    tmp = path.with_suffix(".tmp")
    tmp.write_text(rendered, encoding="utf-8")

    # Backup existing file before replacing
    if path.exists():
        bak = backup_path(path)
        shutil.copy2(path, bak)

    tmp.rename(path)
    return path


# ─── Atomic multi-target write ──────────────────────────────────────────────

class AtomicConfigWriter:
    """Write multiple config files atomically.

    Steps:
    1. Read all existing configs.
    2. Merge fdtd entry into each.
    3. Render each to a string.
    4. Write all to temporary files.
    5. If all temp writes succeed, backup originals and rename.
    6. If any step failed before rename, clean up temps and abort.
    """

    def __init__(self, targets, server_entry):
        self.targets = targets
        self.server_entry = server_entry
        self._staged = []  # list of (target, config_path, tmp_path)

    def run(self):
        """Execute the full write transaction. Returns list of written paths."""
        # Phase 1: read + merge + render + write temps
        for t in self.targets:
            path = config_path(t)
            existing = read_config(t)
            merged = merge_config(t, existing, self.server_entry)
            rendered = render_config(t, merged)

            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                prefix=f"{path.name}.",
                dir=path.parent,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(rendered)
            except Exception:
                os.unlink(tmp_path)
                raise

            self._staged.append((t, path, Path(tmp_path)))

        # Phase 2: backup originals and rename temps
        written = []
        for t, path, tmp_path in self._staged:
            if path.exists():
                bak = backup_path(path)
                shutil.copy2(path, bak)
            tmp_path.rename(path)
            written.append(path)

        return written

    def rollback(self):
        """Clean up any temp files on failure."""
        for _, _, tmp_path in self._staged:
            if tmp_path.exists():
                tmp_path.unlink()


# ─── CLI ────────────────────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Configure MCP clients (Codex, Claude, Hermes) for the FDTD MCP server.",
    )
    parser.add_argument(
        "--target", "-t",
        required=True,
        help="Client to configure: codex, claude, hermes, or all",
    )
    parser.add_argument(
        "--command",
        default=sys.executable,
        help="Path to the Python interpreter (default: sys.executable)",
    )
    parser.add_argument(
        "--args",
        nargs="*",
        default=["-m", "src.server"],
        help="Server module args (default: -m src.server)",
    )
    parser.add_argument(
        "--cwd",
        default=str(project_root()),
        help="Working directory for the server (default: project root)",
    )
    parser.add_argument(
        "--rpc-url",
        default="http://localhost:5000",
        help="FDTD RPC server URL (default: http://localhost:5000)",
    )
    parser.add_argument(
        "--connection-mode",
        default="stdio",
        help="MCP connection mode (default: stdio)",
    )
    return parser.parse_args(argv)


def resolve_targets(target_arg: str):
    """Resolve the --target argument to a list of valid target names."""
    if target_arg == "all":
        targets = list(KNOWN_TARGETS)
    elif target_arg in KNOWN_TARGETS:
        targets = [target_arg]
    else:
        valid = ", ".join(KNOWN_TARGETS)
        print(
            f"Error: unknown target '{target_arg}'. "
            f"Valid targets: {valid}",
            file=sys.stderr,
        )
        sys.exit(1)
    return targets


def main():
    args = parse_args()
    targets = resolve_targets(args.target)

    if args.cwd:
        set_project_root_override(args.cwd)

    server_entry = build_server_entry(args)
    writer = AtomicConfigWriter(targets, server_entry)

    try:
        written = writer.run()
    except Exception as exc:
        writer.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    for path in written:
        print(f"Wrote {path}")
    print("Done.")


if __name__ == "__main__":
    main()
