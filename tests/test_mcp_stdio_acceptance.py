"""MCP stdio protocol acceptance tests.

Launches the MCP server as a subprocess and exercises the full MCP protocol
(initialize, tools/list, tools/call) over newline-delimited JSON-RPC on
stdin/stdout.

Designed for offline CI: fdtd_health may return connection_error, and all
RPC-bound calls use dry_run/mock modes so they succeed without a real backend.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(ROOT / ".venv/bin/python")


# ── helpers ────────────────────────────────────────────────────────────────


class McpStdioClient:
    """Minimal MCP stdio client over subprocess pipes."""

    def __init__(self, proc: subprocess.Popen, timeout: float = 10.0):
        self.proc = proc
        self.timeout = timeout
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def send(self, msg: dict) -> None:
        """Send a JSON-RPC message (one line of JSON to stdin)."""
        line = json.dumps(msg, ensure_ascii=False)
        try:
            self.proc.stdin.write(line + "\n")  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]
        except BrokenPipeError:
            stderr_tail = ""
            try:
                self.proc.stderr.flush()
                import select

                ready, _, _ = select.select([self.proc.stderr], [], [], 0.5)
                if ready:
                    stderr_tail = self.proc.stderr.read()
            except Exception:
                pass
            raise RuntimeError(
                f"Server process died before message could be sent.\n"
                f"Return code: {self.proc.poll()}\n"
                f"Stderr tail: {stderr_tail}"
            )

    def recv(self, timeout: float | None = None) -> dict | None:
        """Read one JSON-RPC message from stdout (blocking, one line)."""
        timeout = timeout if timeout is not None else self.timeout
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            # Non-blocking poll to check if we have data
            import select

            remaining = max(0.01, deadline - time.monotonic())
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                continue

            line = self.proc.stdout.readline()
            if not line:
                # EOF
                stderr_tail = ""
                try:
                    self.proc.stderr.flush()
                    remaining2 = select.select([self.proc.stderr], [], [], 0.5)
                    if remaining2[0]:
                        stderr_tail = self.proc.stderr.read()
                except Exception:
                    pass
                raise RuntimeError(
                    f"Server stdout closed unexpectedly.\n"
                    f"Return code: {self.proc.poll()}\n"
                    f"Stderr tail: {stderr_tail}"
                )
            line = line.strip()
            if line:
                return json.loads(line)

        raise TimeoutError(f"No response received within {timeout}s")

    def request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and return the result."""
        msg_id = self._next_id()
        req = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            req["params"] = params
        self.send(req)

        while True:
            resp = self.recv()
            if resp is None:
                raise RuntimeError("Server closed connection unexpectedly")
            if resp.get("id") == msg_id:
                return resp
            # Could be a notification or log — skip and read next

    def notify(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)

    def close(self) -> None:
        """Terminate the server process."""
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)


# ── fixture ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def mcp_client():
    """Launch the MCP server in stdio mode and return an McpStdioClient."""
    env = os.environ.copy()
    env["FDTD_RPC_URL"] = "http://127.0.0.1:59999"
    # Suppress Python bytecode and buffering
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    proc = subprocess.Popen(
        [PYTHON, "-m", "src.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(ROOT),
        text=True,
        bufsize=1,
    )

    client = McpStdioClient(proc, timeout=15.0)

    try:
        # ── MCP handshake ──────────────────────────────────────────────
        init_resp = client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest-stdio-acceptance", "version": "0.1"},
            },
        )
        assert "result" in init_resp, (
            f"initialize failed: {json.dumps(init_resp, indent=2)}"
        )
        init_result = init_resp["result"]
        assert "protocolVersion" in init_result
        assert init_result["capabilities"]["tools"] is not None

        # Send initialized notification
        client.notify("notifications/initialized")

        yield client
    finally:
        client.close()


# ── tests ──────────────────────────────────────────────────────────────────


class TestMcpStdioHandshake:
    """Protocol-level handshake and capability discovery."""

    def test_initialize_succeeds(self, mcp_client: McpStdioClient):
        """Already done in fixture; verify server info is present."""
        resp = mcp_client.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "recheck", "version": "0.2"},
        })
        result = resp["result"]
        assert result["serverInfo"]["name"] == "FDTD MCP"

    def test_tools_list_returns_tools(self, mcp_client: McpStdioClient):
        """tools/list must return at least the tools expected by this test."""
        resp = mcp_client.request("tools/list", {})
        tools = resp["result"]["tools"]
        tool_names = {t["name"] for t in tools}

        required = {
            "fdtd_health",
            "fdtd_project_status",
            "fdtd_object_create",
            "fdtd_source_create",
            "fdtd_monitor_create",
            "fdtd_device_recipe_validate",
            "fdtd_device_recipe_compile",
            "fdtd_generic_sweep_plan",
            "fdtd_generic_sweep_start",
        }
        missing = required - tool_names
        assert not missing, f"Missing tools: {missing}"


class TestMcpStdioToolsCall:
    """Exercise individual tools via tools/call over stdio."""

    # ── health (may be offline) ─────────────────────────────────────────

    def test_fdtd_health(self, mcp_client: McpStdioClient):
        """fdtd_health may return connection_error in offline CI."""
        resp = mcp_client.request(
            "tools/call",
            {"name": "fdtd_health", "arguments": {}},
        )
        assert "result" in resp, f"tools/call fdtd_health failed: {resp}"
        result = resp["result"]
        # FastMCP wraps tool return in structured content; extract it
        data = _extract_tool_result(result)
        # ok=True means connected; ok=False with connection_error is fine offline
        if not data.get("ok"):
            err = data.get("error", {})
            assert err.get("type") in ("connection_error", "timeout", "request_error"), (
                f"Unexpected error: {data}"
            )

    # ── project status ──────────────────────────────────────────────────

    def test_fdtd_project_status(self, mcp_client: McpStdioClient):
        """fdtd_project_status with dry_run returns mock status."""
        resp = mcp_client.request(
            "tools/call",
            {"name": "fdtd_project_status", "arguments": {"dry_run": True}},
        )
        result = resp["result"]
        data = _extract_tool_result(result)
        assert data.get("ok") is True
        assert data.get("dry_run") is True

    # ── object create (dry-run) ─────────────────────────────────────────

    def test_fdtd_object_create_dry_run(self, mcp_client: McpStdioClient):
        """fdtd_object_create with dry_run=true returns mock success."""
        resp = mcp_client.request(
            "tools/call",
            {
                "name": "fdtd_object_create",
                "arguments": {
                    "dry_run": True,
                    "body": {
                        "type": "rectangle",
                        "name": "test_rect",
                        "x_span": 1e-6,
                        "y_span": 2e-6,
                        "material": "Si",
                    },
                },
            },
        )
        result = resp["result"]
        data = _extract_tool_result(result)
        assert data.get("ok") is True
        assert data.get("dry_run") is True

    # ── source create (dry-run) ─────────────────────────────────────────

    def test_fdtd_source_create_dry_run(self, mcp_client: McpStdioClient):
        """fdtd_source_create with dry_run=true returns mock success."""
        resp = mcp_client.request(
            "tools/call",
            {
                "name": "fdtd_source_create",
                "arguments": {
                    "dry_run": True,
                    "body": {
                        "type": "gaussian",
                        "wavelength": 1.55e-6,
                        "polarization": "x",
                    },
                },
            },
        )
        result = resp["result"]
        data = _extract_tool_result(result)
        assert data.get("ok") is True
        assert data.get("dry_run") is True

    # ── monitor create (dry-run) ────────────────────────────────────────

    def test_fdtd_monitor_create_dry_run(self, mcp_client: McpStdioClient):
        """fdtd_monitor_create with dry_run=true returns mock success."""
        resp = mcp_client.request(
            "tools/call",
            {
                "name": "fdtd_monitor_create",
                "arguments": {
                    "dry_run": True,
                    "body": {
                        "type": "frequency_domain",
                        "name": "test_monitor",
                        "frequencies": [1.93e14],
                    },
                },
            },
        )
        result = resp["result"]
        data = _extract_tool_result(result)
        assert data.get("ok") is True
        assert data.get("dry_run") is True

    # ── recipe validate (pure compiler) ─────────────────────────────────

    def test_fdtd_device_recipe_validate(self, mcp_client: McpStdioClient):
        """fdtd_device_recipe_validate must succeed (pure Python)."""
        resp = mcp_client.request(
            "tools/call",
            {
                "name": "fdtd_device_recipe_validate",
                "arguments": {
                    "recipe": _minimal_recipe(),
                },
            },
        )
        result = resp["result"]
        data = _extract_tool_result(result)
        assert data.get("ok") is True, f"Recipe validation failed: {data}"
        assert "normalized_recipe" in data

    # ── recipe compile (pure compiler) ──────────────────────────────────

    def test_fdtd_device_recipe_compile(self, mcp_client: McpStdioClient):
        """fdtd_device_recipe_compile must succeed (pure Python)."""
        resp = mcp_client.request(
            "tools/call",
            {
                "name": "fdtd_device_recipe_compile",
                "arguments": {
                    "recipe": _minimal_recipe(),
                },
            },
        )
        result = resp["result"]
        data = _extract_tool_result(result)
        assert data.get("ok") is True, f"Recipe compile failed: {data}"
        assert "script" in data
        assert "compile_fingerprint" in data

    # ── generic sweep plan (pure compiler) ──────────────────────────────

    def test_fdtd_generic_sweep_plan(self, mcp_client: McpStdioClient):
        """fdtd_generic_sweep_plan must succeed (pure Python)."""
        resp = mcp_client.request(
            "tools/call",
            {
                "name": "fdtd_generic_sweep_plan",
                "arguments": {
                    "body": {
                        "recipe": _minimal_recipe(),
                        "sweep_plan": {
                            "schema_version": "1.0",
                            "parameters": [
                                {
                                    "name": "wavelength",
                                    "unit": "m",
                                    "values": [1.5e-6, 1.55e-6, 1.6e-6],
                                },
                            ],
                            "max_tasks": 3,
                        },
                    },
                },
            },
        )
        result = resp["result"]
        data = _extract_tool_result(result)
        assert data.get("ok") is True, f"Sweep plan failed: {data}"
        assert "plan" in data

    # ── generic sweep start (mock mode) ─────────────────────────────────

    def test_fdtd_generic_sweep_start_mock(self, mcp_client: McpStdioClient):
        """fdtd_generic_sweep_start with mode=mock returns mock job id."""
        resp = mcp_client.request(
            "tools/call",
            {
                "name": "fdtd_generic_sweep_start",
                "arguments": {
                    "body": {
                        "recipe": _minimal_recipe(),
                        "sweep_plan": {
                            "schema_version": "1.0",
                            "parameters": [
                                {
                                    "name": "wavelength",
                                    "unit": "m",
                                    "values": [1.5e-6, 1.55e-6],
                                },
                            ],
                            "max_tasks": 2,
                        },
                        "mode": "mock",
                        "plan_approval": {
                            "approved": True,
                            "packet_fingerprint": "__acceptance_test_skip__",
                        },
                    },
                },
            },
        )
        result = resp["result"]
        data = _extract_tool_result(result)
        # With mock mode, should return a job_id or dry_run success
        assert data.get("ok") is True or "job_id" in data, (
            f"Mock sweep start failed: {data}"
        )


# ── helpers ────────────────────────────────────────────────────────────────


def _extract_tool_result(result: dict) -> dict:
    """Extract the actual tool return value from a FastMCP tools/call response.

    FastMCP may wrap the tool return in ``structuredContent`` or
    ``content`` blocks.  This helper tries to recover the plain dict.
    """
    # Direct structured content
    if "structuredContent" in result:
        return result["structuredContent"]
    # Content blocks (TextContent objects)
    if "content" in result:
        for block in result["content"]:
            if block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, TypeError):
                    return {"text": block["text"]}
    # Fallback: result itself might be the data
    if "ok" in result:
        return result
    return result


def _minimal_recipe() -> dict:
    """Return a minimal valid device recipe for testing compiler tools.

    Conforms to the ``validate_recipe`` schema: parameters are typed,
    assumptions reference parameters, and materials/geometry are lists
    of objects with ``name``/``type``/``properties`` keys.
    """
    return {
        "schema_version": "1.0",
        "parameters": {
            "wavelength": {
                "type": "float",
                "default": 1.55e-6,
                "min": 1.0e-6,
                "max": 3.0e-6,
                "unit": "m",
            },
            "polarization": {
                "type": "int",
                "default": 1,
            },
        },
        "assumptions": [
            {
                "parameter": "wavelength",
                "reason": "Standard telecom C-band wavelength",
            },
            {
                "parameter": "polarization",
                "reason": "1 = TE (x-polarized), testing only",
            },
        ],
        "materials": [
            {
                "name": "substrate",
                "type": "SiO2",
                "properties": {"refractive_index": 1.45},
            },
            {
                "name": "core",
                "type": "Si",
                "properties": {"refractive_index": 3.47},
            },
        ],
        "geometry": [
            {
                "type": "rectangle",
                "name": "substrate",
                "properties": {
                    "material": "substrate",
                    "x_span": 5e-6,
                    "y_span": 1e-6,
                },
            },
            {
                "type": "rectangle",
                "name": "core",
                "properties": {
                    "material": "core",
                    "x_span": 1e-6,
                    "y_span": 0.22e-6,
                },
            },
        ],
        "sources": [],
        "monitors": [],
        "analysis_groups": [],
        "pre_run": "",
        "post_run": "",
    }
