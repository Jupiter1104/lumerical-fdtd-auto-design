# MCP Jobs API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the verified RPC API v1 `/jobs/*` workflow through the Mac-side MCP server so Claude Code can plan, start, monitor, and resume persistent jobs without using legacy `/sweep/*` routes.

**Architecture:** Add a new focused MCP module `src/tools/jobs.py` that wraps `RpcClient.jobs_*` and owns metasurface convenience request construction. Keep legacy `fdtd_sweep_*` tools registered for compatibility but mark them as legacy. Update `src/server.py` to register the new module, add `.mcp.json` for local Claude Code configuration, and verify everything offline with fake clients.

**Tech Stack:** Python 3.10+, FastMCP, `RpcClient`, pytest, existing Flask RPC API v1 contract.

---

## File Map

- Create `src/tools/jobs.py`
  - Responsibility: MCP tools for `/jobs/*` and metasurface job request construction.
  - Public helper: `build_metasurface_sweep_request(mode, ratio_list, period_list, base_height, base_period, phases, template, include_models, approved)` for testable request construction.
  - Public registration: `register_job_tools(mcp, rpc)`.
- Modify `src/server.py`
  - Import and register `register_job_tools`.
  - Update module docstring and default `RPC_URL` from old `5001` to current `5000`.
- Modify `src/tools/simulation.py`
  - Mark existing `fdtd_sweep_*` docstrings as legacy compatibility tools.
  - No route or behavior changes.
- Modify `tests/test_mcp_registration.py`
  - Expect new job and metasurface MCP tools in the registered set.
- Create `tests/test_mcp_jobs_tools.py`
  - Use fake MCP and fake RPC objects to call registered tool functions directly.
  - Verify request construction, approval guard, and `/jobs/*` routing through `RpcClient` methods.
- Create `.mcp.json`
  - Claude Code local MCP configuration with `FDTD_RPC_URL=http://localhost:5000`.
- Modify `README.md`, `TECH_STACK.md`, `docs/RPC_API_V1.md`, and `DEV_LOG.md`
  - Document new MCP job tools and the fact that legacy `fdtd_sweep_*` tools are not the preferred v1 path.

---

## Task 1: Add MCP job tools with TDD

**Files:**
- Create: `src/tools/jobs.py`
- Create: `tests/test_mcp_jobs_tools.py`

- [ ] **Step 1: Write failing tests for generic job tools**

Create `tests/test_mcp_jobs_tools.py` with:

```python
from src.tools.jobs import register_job_tools


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

    def jobs_plan(self, request):
        self.calls.append(("jobs_plan", request))
        return {"ok": True, "route": "plan", "request": request}

    def jobs_start(self, request):
        self.calls.append(("jobs_start", request))
        return {"ok": True, "route": "start", "request": request}

    def jobs_get(self, job_id):
        self.calls.append(("jobs_get", job_id))
        return {"ok": True, "job_id": job_id}

    def jobs_tasks(self, job_id):
        self.calls.append(("jobs_tasks", job_id))
        return {"ok": True, "job_id": job_id, "tasks": []}

    def jobs_resume(self, job_id, request=None):
        self.calls.append(("jobs_resume", job_id, request))
        return {"ok": True, "job_id": job_id, "request": request or {}}


def registered_tools():
    mcp = FakeMcp()
    rpc = FakeRpc()
    register_job_tools(mcp, rpc)
    return mcp.tools, rpc


def test_generic_job_tools_call_rpc_jobs_methods():
    tools, rpc = registered_tools()
    request = {"mode": "mock", "job_type": "geometry-smoke"}

    assert tools["fdtd_job_plan"](request) == {
        "ok": True,
        "route": "plan",
        "request": request,
    }
    assert tools["fdtd_job_start"](request) == {
        "ok": True,
        "route": "start",
        "request": request,
    }
    assert tools["fdtd_job_status"]("job_1") == {"ok": True, "job_id": "job_1"}
    assert tools["fdtd_job_tasks"]("job_1") == {
        "ok": True,
        "job_id": "job_1",
        "tasks": [],
    }
    assert tools["fdtd_job_resume"]("job_1") == {
        "ok": True,
        "job_id": "job_1",
        "request": {},
    }

    assert rpc.calls == [
        ("jobs_plan", request),
        ("jobs_start", request),
        ("jobs_get", "job_1"),
        ("jobs_tasks", "job_1"),
        ("jobs_resume", "job_1", None),
    ]
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py::test_generic_job_tools_call_rpc_jobs_methods -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.tools.jobs'`.

- [ ] **Step 3: Implement minimal generic job tools**

Create `src/tools/jobs.py`:

```python
"""Persistent job tools for FDTD MCP Server."""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_job_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    """Register RPC API v1 persistent job tools."""

    @mcp.tool()
    def fdtd_job_plan(request: dict) -> dict:
        """
        Create a persistent planned job without running FDTD.

        Use this before real runs to preview task count, job paths, and request
        shape. For natural-language workflows this is the safe first step.
        """
        return rpc.jobs_plan(request)

    @mcp.tool()
    def fdtd_job_start(request: dict) -> dict:
        """
        Start a mock or real persistent job through RPC API v1 `/jobs/start`.

        Real jobs require explicit human approval in the request:
        {"approval": {"approved": true, "approved_for": "real_run"}}.
        Long real jobs may return immediately with a job_id; poll with
        fdtd_job_status() and fdtd_job_tasks().
        """
        return rpc.jobs_start(request)

    @mcp.tool()
    def fdtd_job_status(job_id: str) -> dict:
        """Read manifest, status, and summary for a persistent job."""
        return rpc.jobs_get(job_id)

    @mcp.tool()
    def fdtd_job_tasks(job_id: str) -> dict:
        """Read per-task state for a persistent job."""
        return rpc.jobs_tasks(job_id)

    @mcp.tool()
    def fdtd_job_resume(job_id: str, request: Optional[dict] = None) -> dict:
        """
        Resume pending or failed tasks for a persistent job.

        Use only when the user explicitly asks to resume. Resume must not
        change physical settings, mesh, boundary conditions, template, or
        sweep ranges.
        """
        return rpc.jobs_resume(job_id, request)
```

- [ ] **Step 4: Run test and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py::test_generic_job_tools_call_rpc_jobs_methods -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add src/tools/jobs.py tests/test_mcp_jobs_tools.py
git commit -m "feat: add mcp job tools"
```

---

## Task 2: Add metasurface convenience tools with TDD

**Files:**
- Modify: `src/tools/jobs.py`
- Modify: `tests/test_mcp_jobs_tools.py`

- [ ] **Step 1: Write failing tests for metasurface request construction**

Append to `tests/test_mcp_jobs_tools.py`:

```python
from src.tools.jobs import build_metasurface_sweep_request


def test_build_metasurface_sweep_request_defaults_to_cpu_mock_grid():
    request = build_metasurface_sweep_request(
        mode="mock",
        ratio_list=None,
        period_list=None,
        base_height=700e-9,
        base_period=470e-9,
        phases=None,
        template="templates/metasurface/base_model.fsp",
        include_models=False,
        approved=False,
    )

    assert request == {
        "mode": "mock",
        "job_type": "metasurface-sweep",
        "sweep": {
            "template": "templates/metasurface/base_model.fsp",
            "phases": [1, 2, 3, 4],
            "hide": True,
            "include_models": False,
            "config": {
                "SWEEP_Y_AXIS": "period",
                "RATIO_LIST": [0.2, 0.8],
                "PERIOD_LIST": [390e-9, 540e-9],
                "BASE_HEIGHT": 700e-9,
                "BASE_PERIOD": 470e-9,
                "FDTD_PROCESSES": 1,
                "FDTD_CAPACITY": 1,
                "EXPRESS_MODE": 0,
            },
        },
    }


def test_build_metasurface_sweep_request_rejects_unapproved_real_run():
    request = build_metasurface_sweep_request(
        mode="real",
        ratio_list=[0.2],
        period_list=[390e-9],
        base_height=700e-9,
        base_period=470e-9,
        phases=[1, 2, 3, 4],
        template="templates/metasurface/base_model.fsp",
        include_models=False,
        approved=False,
    )

    assert request["ok"] is False
    assert request["error"]["type"] == "approval_required"


def test_build_metasurface_sweep_request_adds_real_run_approval_when_approved():
    request = build_metasurface_sweep_request(
        mode="real",
        ratio_list=[0.2],
        period_list=[390e-9],
        base_height=700e-9,
        base_period=470e-9,
        phases=[1, 2, 3, 4],
        template="templates/metasurface/base_model.fsp",
        include_models=False,
        approved=True,
    )

    assert request["approval"] == {"approved": True, "approved_for": "real_run"}
    assert request["sweep"]["config"]["RATIO_LIST"] == [0.2]
    assert request["sweep"]["config"]["PERIOD_LIST"] == [390e-9]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py -q
```

Expected: FAIL with `ImportError` or `AttributeError` for `build_metasurface_sweep_request`.

- [ ] **Step 3: Implement request builder**

Modify `src/tools/jobs.py` imports and add helpers before `register_job_tools`:

```python
from typing import List, Optional
```

Add:

```python
DEFAULT_RATIO_LIST = [0.2, 0.8]
DEFAULT_PERIOD_LIST = [390e-9, 540e-9]
DEFAULT_PHASES = [1, 2, 3, 4]
DEFAULT_TEMPLATE = "templates/metasurface/base_model.fsp"


def _approval_required_error() -> dict:
    return {
        "ok": False,
        "error": {
            "type": "approval_required",
            "message": "Real metasurface sweeps require approved=True.",
            "details": {"approved_for": "real_run"},
        },
    }


def build_metasurface_sweep_request(
    *,
    mode: str = "mock",
    ratio_list: Optional[List[float]] = None,
    period_list: Optional[List[float]] = None,
    base_height: float = 700e-9,
    base_period: float = 470e-9,
    phases: Optional[List[int]] = None,
    template: str = DEFAULT_TEMPLATE,
    include_models: bool = False,
    approved: bool = False,
) -> dict:
    """Build the RPC API v1 request for a metasurface sweep job."""
    if mode not in {"mock", "real", "plan"}:
        return {
            "ok": False,
            "error": {
                "type": "validation_error",
                "message": "mode must be one of plan, mock, or real.",
                "details": {"mode": mode},
            },
        }
    if mode == "real" and approved is not True:
        return _approval_required_error()

    request = {
        "mode": mode,
        "job_type": "metasurface-sweep",
        "sweep": {
            "template": template,
            "phases": phases or DEFAULT_PHASES,
            "hide": True,
            "include_models": include_models,
            "config": {
                "SWEEP_Y_AXIS": "period",
                "RATIO_LIST": ratio_list or DEFAULT_RATIO_LIST,
                "PERIOD_LIST": period_list or DEFAULT_PERIOD_LIST,
                "BASE_HEIGHT": base_height,
                "BASE_PERIOD": base_period,
                "FDTD_PROCESSES": 1,
                "FDTD_CAPACITY": 1,
                "EXPRESS_MODE": 0,
            },
        },
    }
    if mode == "real":
        request["approval"] = {"approved": True, "approved_for": "real_run"}
    return request
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py -q
```

Expected: all tests in `tests/test_mcp_jobs_tools.py` pass.

- [ ] **Step 5: Write failing tests for metasurface MCP tools**

Append to `tests/test_mcp_jobs_tools.py`:

```python
def test_metasurface_plan_tool_calls_jobs_plan():
    tools, rpc = registered_tools()

    response = tools["fdtd_metasurface_sweep_plan"]()

    assert response["ok"] is True
    assert response["route"] == "plan"
    request = rpc.calls[-1][1]
    assert request["mode"] == "plan"
    assert request["job_type"] == "metasurface-sweep"
    assert request["sweep"]["config"]["EXPRESS_MODE"] == 0


def test_metasurface_start_defaults_to_mock_without_approval():
    tools, rpc = registered_tools()

    response = tools["fdtd_metasurface_sweep_start"]()

    assert response["ok"] is True
    assert response["route"] == "start"
    request = rpc.calls[-1][1]
    assert request["mode"] == "mock"
    assert "approval" not in request


def test_metasurface_start_refuses_unapproved_real_without_rpc_call():
    tools, rpc = registered_tools()

    response = tools["fdtd_metasurface_sweep_start"](mode="real", approved=False)

    assert response["ok"] is False
    assert response["error"]["type"] == "approval_required"
    assert rpc.calls == []


def test_metasurface_start_sends_real_approval_when_approved():
    tools, rpc = registered_tools()

    response = tools["fdtd_metasurface_sweep_start"](
        mode="real",
        ratio_list=[0.2],
        period_list=[390e-9],
        approved=True,
    )

    assert response["ok"] is True
    request = rpc.calls[-1][1]
    assert request["approval"] == {"approved": True, "approved_for": "real_run"}
    assert request["sweep"]["config"]["RATIO_LIST"] == [0.2]
    assert request["sweep"]["config"]["PERIOD_LIST"] == [390e-9]
```

- [ ] **Step 6: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py -q
```

Expected: FAIL with missing `fdtd_metasurface_sweep_plan` or `fdtd_metasurface_sweep_start`.

- [ ] **Step 7: Implement metasurface MCP tools**

Append inside `register_job_tools(mcp, rpc)` in `src/tools/jobs.py`, after `fdtd_job_resume`:

```python
    @mcp.tool()
    def fdtd_metasurface_sweep_plan(
        ratio_list: Optional[List[float]] = None,
        period_list: Optional[List[float]] = None,
        base_height: float = 700e-9,
        base_period: float = 470e-9,
        phases: Optional[List[int]] = None,
        template: str = DEFAULT_TEMPLATE,
        include_models: bool = False,
    ) -> dict:
        """
        Plan a metasurface sweep job without running FDTD.

        Defaults to a safe 2x2 CPU grid. Use this to preview task count,
        template path, output directories, and request shape before mock or
        real execution.
        """
        request = build_metasurface_sweep_request(
            mode="plan",
            ratio_list=ratio_list,
            period_list=period_list,
            base_height=base_height,
            base_period=base_period,
            phases=phases,
            template=template,
            include_models=include_models,
            approved=False,
        )
        return rpc.jobs_plan(request)

    @mcp.tool()
    def fdtd_metasurface_sweep_start(
        mode: str = "mock",
        ratio_list: Optional[List[float]] = None,
        period_list: Optional[List[float]] = None,
        base_height: float = 700e-9,
        base_period: float = 470e-9,
        phases: Optional[List[int]] = None,
        template: str = DEFAULT_TEMPLATE,
        include_models: bool = False,
        approved: bool = False,
    ) -> dict:
        """
        Start a mock or real metasurface sweep job through `/jobs/start`.

        The default mode is mock. For real FDTD execution, first present a
        run summary to the user and only call with mode="real" and
        approved=True after explicit approval. This tool uses CPU defaults:
        EXPRESS_MODE=0, FDTD_PROCESSES=1, FDTD_CAPACITY=1.
        """
        request = build_metasurface_sweep_request(
            mode=mode,
            ratio_list=ratio_list,
            period_list=period_list,
            base_height=base_height,
            base_period=base_period,
            phases=phases,
            template=template,
            include_models=include_models,
            approved=approved,
        )
        if request.get("ok") is False:
            return request
        return rpc.jobs_start(request)
```

- [ ] **Step 8: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 2**

Run:

```bash
git add src/tools/jobs.py tests/test_mcp_jobs_tools.py
git commit -m "feat: add mcp metasurface job helpers"
```

---

## Task 3: Register new tools and update MCP defaults

**Files:**
- Modify: `src/server.py`
- Modify: `tests/test_mcp_registration.py`

- [ ] **Step 1: Write failing registration test**

Modify the expected set in `tests/test_mcp_registration.py` to include:

```python
        "fdtd_job_plan",
        "fdtd_job_start",
        "fdtd_job_status",
        "fdtd_job_tasks",
        "fdtd_job_resume",
        "fdtd_metasurface_sweep_plan",
        "fdtd_metasurface_sweep_start",
```

Keep all existing legacy `fdtd_sweep_*` entries in the set.

- [ ] **Step 2: Run registration test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_registration.py -q
```

Expected: FAIL showing the new job tool names are missing.

- [ ] **Step 3: Register job tools and update default RPC URL**

Modify `src/server.py` imports:

```python
from .tools.jobs import register_job_tools
```

Modify the docstring examples so every old `5001` reference becomes `5000`.

Modify default `RPC_URL`:

```python
RPC_URL = os.environ.get("FDTD_RPC_URL", "http://localhost:5000")
```

Modify `register_all_tools()`:

```python
    register_simulation_tools(mcp, rpc)
    register_job_tools(mcp, rpc)
    register_analysis_tools(mcp, rpc)
```

- [ ] **Step 4: Run registration test and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_registration.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Run MCP job tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py tests/test_mcp_registration.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add src/server.py tests/test_mcp_registration.py
git commit -m "feat: register mcp job tools"
```

---

## Task 4: Add `.mcp.json` and verify configuration

**Files:**
- Create: `.mcp.json`
- Create: `tests/test_mcp_config.py`

- [ ] **Step 1: Write failing `.mcp.json` test**

Create `tests/test_mcp_config.py`:

```python
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_claude_mcp_config_points_to_local_fdtd_server():
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))

    fdtd = config["mcpServers"]["fdtd"]
    assert fdtd["command"] == "python"
    assert fdtd["args"] == ["-m", "src.server"]
    assert fdtd["cwd"] == str(ROOT)
    assert fdtd["env"]["FDTD_RPC_URL"] == "http://localhost:5000"
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_config.py -q
```

Expected: FAIL with `FileNotFoundError` for `.mcp.json`.

- [ ] **Step 3: Create `.mcp.json`**

Create `.mcp.json` at the project root:

```json
{
  "mcpServers": {
    "fdtd": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/Users/jupiter/AI agent/Codex workspace/projects/2026-06-17-lumerical-fdtd-auto-design",
      "env": {
        "FDTD_RPC_URL": "http://localhost:5000"
      }
    }
  }
}
```

- [ ] **Step 4: Run test and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_config.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add .mcp.json tests/test_mcp_config.py
git commit -m "chore: add fdtd mcp config"
```

---

## Task 5: Mark legacy sweep tools and update docs

**Files:**
- Modify: `src/tools/simulation.py`
- Modify: `README.md`
- Modify: `TECH_STACK.md`
- Modify: `docs/RPC_API_V1.md`

- [ ] **Step 1: Write failing legacy marker test**

Append to `tests/test_mcp_jobs_tools.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_legacy_sweep_tools_are_marked_as_legacy():
    text = (ROOT / "src/tools/simulation.py").read_text(encoding="utf-8")

    assert "Legacy compatibility tools" in text
    assert "Prefer fdtd_job_* and fdtd_metasurface_sweep_*" in text
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py::test_legacy_sweep_tools_are_marked_as_legacy -q
```

Expected: FAIL because the legacy marker text is not present.

- [ ] **Step 3: Update legacy sweep docstrings**

Modify the module docstring at the top of `src/tools/simulation.py` to:

```python
"""Legacy sweep pipeline tools for FDTD MCP Server.

Legacy compatibility tools for the historical `/sweep/*` RPC shape.
Prefer fdtd_job_* and fdtd_metasurface_sweep_* for the current RPC API v1
persistent job workflow.
"""
```

Add this sentence near the beginning of each `fdtd_sweep_*` tool docstring:

```text
Legacy compatibility tool. Prefer fdtd_job_* and fdtd_metasurface_sweep_* for new work.
```

Do not change any function body.

- [ ] **Step 4: Run test and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py::test_legacy_sweep_tools_are_marked_as_legacy -q
```

Expected: `1 passed`.

- [ ] **Step 5: Update README current status**

In `README.md`, update the “当前代码状态” or “主要下一步” section to mention:

```md
- MCP Server 已新增 `/jobs/*` 工具：`fdtd_job_plan/start/status/tasks/resume`，以及 metasurface 便捷工具 `fdtd_metasurface_sweep_plan/start`。旧 `fdtd_sweep_*` 仅保留为 legacy compatibility。
```

- [ ] **Step 6: Update TECH_STACK MCP section**

In `TECH_STACK.md`, in the MCP tools area, add a Jobs row:

```md
| Jobs | `fdtd_job_plan`, `fdtd_job_start`, `fdtd_job_status`, `fdtd_job_tasks`, `fdtd_job_resume` |
| Metasurface Jobs | `fdtd_metasurface_sweep_plan`, `fdtd_metasurface_sweep_start` |
```

Also update any MCP startup example that still uses old `5001` to `5000`.

- [ ] **Step 7: Update RPC API docs**

In `docs/RPC_API_V1.md`, add a short “MCP 对应工具” note near the `/jobs/*` routes:

```md
MCP 新工作流优先使用 `fdtd_job_*` 和 `fdtd_metasurface_sweep_*`；旧 `fdtd_sweep_*` 工具仅保留为 legacy compatibility，不对应当前新 `rpc_server.py` 的 `/jobs/*` 主路径。
```

- [ ] **Step 8: Run docs/legacy tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_mcp_jobs_tools.py tests/test_mcp_config.py tests/test_mcp_registration.py -q
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 5**

Run:

```bash
git add src/tools/simulation.py README.md TECH_STACK.md docs/RPC_API_V1.md tests/test_mcp_jobs_tools.py
git commit -m "docs: document mcp jobs workflow"
```

---

## Task 6: Full verification and final commit hygiene

**Files:**
- Modify: `DEV_LOG.md`

- [ ] **Step 1: Run compileall**

Run:

```bash
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
```

Expected: exits `0`.

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. Expected count should be higher than the previous `114 passed` because this plan adds new tests.
Expected final summary: `124 passed`.

- [ ] **Step 3: Scan for old MCP default port**

Run:

```bash
rg -n "localhost:5001|127\\.0\\.0\\.1:5001|5001" src/server.py README.md TECH_STACK.md docs/RPC_API_V1.md .mcp.json tests/test_mcp_config.py || true
```

Expected: no output.

- [ ] **Step 4: Scan for accidental `/sweep/*` use in new jobs module**

Run:

```bash
rg -n 'sweep_config|sweep_run|sweep_status|/sweep' src/tools/jobs.py tests/test_mcp_jobs_tools.py
```

Expected: no output.

- [ ] **Step 5: Append final DEV_LOG entry**

Append this entry to `DEV_LOG.md`:

```md
## 2026-06-19 - MCP 接入持久 jobs API

- 目标：让 Claude Code / MCP 直接调用当前已验证的 `/jobs/*` 状态机，而不是旧 `/sweep/*`。
- 修改：
  - 新增 `src/tools/jobs.py`，注册 `fdtd_job_plan/start/status/tasks/resume`。
  - 新增 metasurface 便捷工具 `fdtd_metasurface_sweep_plan/start`，默认 mock、CPU、`EXPRESS_MODE=0`，real 需要 `approved=True` 后才写入 `approved_for=real_run`。
  - `.mcp.json` 默认指向 `FDTD_RPC_URL=http://localhost:5000`。
  - 旧 `fdtd_sweep_*` 标记为 legacy compatibility。
- 验证：
  - `.venv/bin/python -m compileall -q rpc_server.py src scripts tests`：通过。
  - `.venv/bin/python -m pytest -q`：`124 passed`。
  - `rg -n "localhost:5001|127\\.0\\.0\\.1:5001|5001" src/server.py README.md TECH_STACK.md docs/RPC_API_V1.md .mcp.json tests/test_mcp_config.py || true`：无输出。
  - `rg -n 'sweep_config|sweep_run|sweep_status|/sweep' src/tools/jobs.py tests/test_mcp_jobs_tools.py`：无输出。
```

- [ ] **Step 6: Commit verification log if changed**

Run:

```bash
git add DEV_LOG.md
git commit -m "docs: record mcp jobs verification"
```

- [ ] **Step 7: Check git status**

Run:

```bash
git status --short
git log -5 --oneline
```

Expected: clean worktree. Recent commits should include the task commits from this plan.

---

## Final Notes for Executor

- Do not run real FDTD in this plan.
- Do not restart Windows services in this plan.
- Do not remove old `fdtd_sweep_*` tools; only label them legacy.
- Keep all new metasurface MCP defaults CPU-safe: `EXPRESS_MODE=0`, `FDTD_PROCESSES=1`, `FDTD_CAPACITY=1`.
- Any future real run still requires the existing project approval summary and explicit user approval.
