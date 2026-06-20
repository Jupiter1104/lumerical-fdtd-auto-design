# Deliverable Personal FDTD MCP 0.1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前项目实现为可交付的个人 FDTD MCP 0.1.0：Mac 端 MCP 能通过 Windows RPC 完成通用 FDTD 操作闭环、DeviceRecipe 编译/build、Generic SweepPlan plan/mock/real 提交、安装配置和非物理验收。

**Architecture:** 保留现有 Mac FastMCP → RpcClient → Windows Flask RPC → raw lumapi 架构。新增能力分三层：纯 Python 编译器层负责 DeviceRecipe 与 Generic SweepPlan；Mac typed tools 只做 schema/审批/转发；Windows route/adapter 使用同一编译器复算指纹并通过 fake lumapi 契约测试覆盖 20 步闭环。

**Tech Stack:** Python 3.10+、FastMCP、requests、Flask、pytest、Lumerical v242 raw lumapi、Windows CMD/PowerShell、macOS zsh。

---

## Assumptions

- 本计划只写实现路径，不启动 C4/C5 真实 sweep，不验证 2π 物理结论。
- 当前未提交的文档同步改动属于既有工作；执行本计划时只提交本计划任务涉及的文件。
- `plan/mock` 测试必须能在无 Windows、无 Lumerical、无飞书 Webhook 环境通过。
- Windows solver smoke 是固定低成本技术 smoke，只验证“能运行并读取结果”，报告必须标记 `technical_smoke=true` 和 `physical_conclusion=false`。
- 执行时如果工作树仍有不相关改动，先创建隔离 worktree 或只 stage 当前任务文件。

## Success Criteria

- `tools/list` 精确包含 spec 中 69 个工具，不包含任何 `fdtd_sweep_*`。
- 通用 20 步 FDTD 流程每一步至少有一个工具和一个 fake-lumapi 契约测试覆盖。
- DeviceRecipe validate/compile/build 的 fingerprint gate 生效；build 不运行求解。
- Generic SweepPlan validate/plan/start 的确定性展开、预算、approval 和 `recipe-sweep` job 落盘生效。
- Codex、Claude Code、Hermes 配置脚本可重复执行，写入前备份，失败时事务回滚。
- Windows setup/start/status/stop/restart 统一使用 `%LOCALAPPDATA%\fdtd-mcp\` 状态目录，关闭 `.bat` 不终止后台 RPC。
- 完整离线验证通过；Windows 最小 solver smoke 单独通过。

## File Map

### Mac MCP tools

- Modify `src/server.py`
  - 注册新的 typed tool modules。
  - 不再注册 legacy `fdtd_sweep_*` 和旧低层重复工具。
- Create `src/tools/project.py`
  - `fdtd_project_new/load/save/status/switch_to_layout`。
- Create `src/tools/objects.py`
  - `fdtd_object_create/list/get/update/copy/rename/delete`、`fdtd_group_update`。
- Create `src/tools/materials.py`
  - `fdtd_material_create/list/get/update/assign/fit_diagnose`。
- Create `src/tools/solver.py`
  - `fdtd_solver_get/update`、`fdtd_mesh_diagnose`、`fdtd_resource_estimate`。
- Create `src/tools/sources.py`
  - `fdtd_source_create/get/update`。
- Create `src/tools/monitors.py`
  - `fdtd_monitor_create/get/update`。
- Create `src/tools/analysis_groups.py`
  - `fdtd_analysis_group_create/get/update`。
- Create `src/tools/results.py`
  - `fdtd_simulation_run/status`、`fdtd_result_list/describe/read`、`fdtd_results_download`。
- Create `src/tools/raw.py`
  - `fdtd_eval/getv/setv`，默认注册。
- Create `src/tools/recipes.py`
  - `fdtd_device_recipe_validate/compile/build`。
- Create `src/tools/generic_sweeps.py`
  - `fdtd_generic_sweep_validate/plan/start`。
- Modify `src/tools/model.py`, `src/tools/geometry.py`, `src/tools/simulation.py`, `src/tools/analysis.py`
  - 保留 Python 兼容代码一轮版本，但从 `src/server.py` 的交付注册路径移除。

### Shared pure logic

- Create `src/fdtd_schema.py`
  - API v1 envelope helpers、stable JSON、fingerprint helpers、validation error helpers。
- Create `src/fdtd_script.py`
  - Lumerical script quote/assignment/property helpers。
- Create `src/fdtd_operations.py`
  - 通用 object/material/solver/source/monitor/analysis 操作 schema 和 dry-run script compiler。
- Create `src/device_recipe.py`
  - DeviceRecipe normalize/validate/expression parsing/compile/report/fingerprint。
- Create `src/generic_sweep.py`
  - SweepPlan normalize/validate/Cartesian expansion/task IDs/plan packet。
- Modify `src/simulation_plan.py`
  - 保持现有 metasurface SimulationPlan 对外语义，内部增加到通用 Recipe/SweepPlan 的兼容转换。

### RPC client and Windows server

- Modify `src/rpc_client/client.py`
  - 增加 project/object/material/solver/source/monitor/analysis/result/recipe route methods。
- Modify `rpc_server.py`
  - 增加 project/object/material/solver/source/monitor/analysis/result/recipe routes。
  - 增加 `job_type=recipe-sweep` 的 plan/start 分支。
  - 增加 Windows workspace/job root 路径边界检查。
- Create `src/windows_fdtd_adapter.py`
  - 对 raw lumapi 的统一 adapter；fake lumapi 和真实 lumapi 共用调用路径。
- Modify `src/job_store.py`
  - 支持 `recipe-sweep` inputs/compiled/scripts/tasks 落盘结构。

### Install, smoke, docs

- Create `requirements-runtime.txt`
  - Mac MCP 默认运行依赖；不包含 pytest。
- Create `scripts/macos/install_mcp.sh`
  - macOS 安装入口。
- Create `scripts/macos/configure_mcp_clients.py`
  - Codex TOML、Claude JSON、Hermes YAML 事务写入。
- Create `scripts/validate_parameter_file.py`
  - 用户参数文件无损 validate/normalize/compile 检查。
- Modify `scripts/windows/manage_rpc.ps1`
  - 统一 `%LOCALAPPDATA%\fdtd-mcp\` 状态目录、pythonw 后台启动、PID/日志/health。
- Create `scripts/windows/setup_rpc.ps1`
  - 首次配置入口逻辑。
- Modify `scripts/windows/setup_rpc.bat`
  - 调用 `setup_rpc.ps1`。
- Modify `scripts/windows/start_rpc.bat`, `status_rpc.bat`, `stop_rpc.bat`, `restart_rpc.bat`
  - 统一读取 `rpc.env`。
- Create `scripts/windows/minimal_solver_smoke.py`
  - 固定单模型技术 smoke。
- Create `docs/MCP_USER_GUIDE.md`
- Create `docs/FDTD_OPERATIONS_V1.md`
- Create `docs/DEVICE_RECIPE_V1.md`
- Create `docs/GENERIC_SWEEP_PLAN_V1.md`
- Modify `README.md`, `REQUIREMENTS.md`, `TECH_STACK.md`, `docs/RPC_API_V1.md`, `docs/WINDOWS_RUNBOOK.md`, `DEV_LOG.md`
  - 当前入口改成 MCP 交付状态。

---

## Task 1: Lock the 0.1.0 MCP tool registry contract

**Files:**
- Modify: `tests/test_mcp_registration.py`
- Modify: `src/server.py`
- Create: `src/tools/project.py`
- Create: `src/tools/objects.py`
- Create: `src/tools/materials.py`
- Create: `src/tools/solver.py`
- Create: `src/tools/sources.py`
- Create: `src/tools/monitors.py`
- Create: `src/tools/analysis_groups.py`
- Create: `src/tools/results.py`
- Create: `src/tools/raw.py`
- Create: `src/tools/recipes.py`
- Create: `src/tools/generic_sweeps.py`

- [ ] **Step 1: Write the failing registry test**

In `tests/test_mcp_registration.py`, add a test that asserts the exact 69-tool target:

```python
EXPECTED_DELIVERABLE_TOOLS = {
    "fdtd_health",
    "fdtd_session_start",
    "fdtd_session_pause",
    "fdtd_session_close",
    "fdtd_project_new",
    "fdtd_project_load",
    "fdtd_project_save",
    "fdtd_project_status",
    "fdtd_switch_to_layout",
    "fdtd_object_create",
    "fdtd_object_list",
    "fdtd_object_get",
    "fdtd_object_update",
    "fdtd_object_copy",
    "fdtd_object_rename",
    "fdtd_object_delete",
    "fdtd_group_update",
    "fdtd_material_create",
    "fdtd_material_list",
    "fdtd_material_get",
    "fdtd_material_update",
    "fdtd_material_assign",
    "fdtd_material_fit_diagnose",
    "fdtd_solver_get",
    "fdtd_solver_update",
    "fdtd_mesh_diagnose",
    "fdtd_resource_estimate",
    "fdtd_source_create",
    "fdtd_source_get",
    "fdtd_source_update",
    "fdtd_monitor_create",
    "fdtd_monitor_get",
    "fdtd_monitor_update",
    "fdtd_analysis_group_create",
    "fdtd_analysis_group_get",
    "fdtd_analysis_group_update",
    "fdtd_simulation_run",
    "fdtd_simulation_status",
    "fdtd_result_list",
    "fdtd_result_describe",
    "fdtd_result_read",
    "fdtd_results_download",
    "fdtd_export_gds",
    "fdtd_export_data",
    "fdtd_eval",
    "fdtd_getv",
    "fdtd_setv",
    "fdtd_device_recipe_validate",
    "fdtd_device_recipe_compile",
    "fdtd_device_recipe_build",
    "fdtd_generic_sweep_validate",
    "fdtd_generic_sweep_plan",
    "fdtd_generic_sweep_start",
    "fdtd_simulation_plan_validate",
    "fdtd_simulation_plan_approve",
    "fdtd_simulation_plan_start",
    "fdtd_simulation_plan_real_preflight",
    "fdtd_simulation_plan_production_preflight",
    "fdtd_job_plan",
    "fdtd_job_start",
    "fdtd_job_status",
    "fdtd_job_tasks",
    "fdtd_job_resume",
    "fdtd_metasurface_sweep_plan",
    "fdtd_metasurface_sweep_start",
    "fdtd_device_template",
    "fdtd_list_devices",
    "fdtd_troubleshoot",
    "fdtd_best_practices",
}


def test_deliverable_tool_registry_exact():
    from src import server

    tool_names = set(server.collect_registered_tool_names_for_tests())
    assert tool_names == EXPECTED_DELIVERABLE_TOOLS
    assert not {name for name in tool_names if name.startswith("fdtd_sweep_")}
```

- [ ] **Step 2: Run test to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_mcp_registration.py::test_deliverable_tool_registry_exact -q
```

Expected: FAIL because `collect_registered_tool_names_for_tests` and the new modules do not exist.

- [ ] **Step 3: Add test-friendly registration collection**

Modify `src/server.py` so registration can be inspected without starting stdio:

```python
def collect_registered_tool_names_for_tests() -> list[str]:
    class CollectingMcp:
        def __init__(self) -> None:
            self.names: list[str] = []

        def tool(self):
            def decorator(fn):
                self.names.append(fn.__name__)
                return fn

            return decorator

    collector = CollectingMcp()
    test_rpc = RpcClient(RPC_URL)
    register_deliverable_tools(collector, test_rpc)
    return sorted(collector.names)
```

Also split `register_all_tools()` into:

```python
def register_deliverable_tools(target_mcp, target_rpc) -> None:
    register_session_tools(target_mcp, target_rpc)
    register_project_tools(target_mcp, target_rpc)
    register_object_tools(target_mcp, target_rpc)
    register_material_tools(target_mcp, target_rpc)
    register_solver_tools(target_mcp, target_rpc)
    register_source_tools(target_mcp, target_rpc)
    register_monitor_tools(target_mcp, target_rpc)
    register_analysis_group_tools(target_mcp, target_rpc)
    register_result_tools(target_mcp, target_rpc)
    register_raw_tools(target_mcp, target_rpc)
    register_recipe_tools(target_mcp, target_rpc)
    register_generic_sweep_tools(target_mcp, target_rpc)
    register_plan_tools(target_mcp, target_rpc)
    register_job_tools(target_mcp, target_rpc)
    register_export_tools(target_mcp, target_rpc)
    register_knowledge_tools(target_mcp)
```

- [ ] **Step 4: Add minimal tool wrapper modules**

Create each new `src/tools/*.py` module with thin wrappers that call same-named `RpcClient` or compiler methods. Example for `src/tools/raw.py`:

```python
"""Raw Lumerical debug tools."""

from mcp.server.fastmcp import FastMCP

from ..rpc_client.client import RpcClient


def register_raw_tools(mcp: FastMCP, rpc: RpcClient) -> None:
    @mcp.tool()
    def fdtd_eval(cmd: str) -> dict:
        return rpc.eval(cmd)

    @mcp.tool()
    def fdtd_getv(name: str) -> dict:
        return rpc.getv(name)

    @mcp.tool()
    def fdtd_setv(name: str, value) -> dict:
        return rpc.setv(name, value)
```

Use the same pattern for project/object/material/solver/source/monitor/analysis/result modules. Each wrapper should pass `dry_run` through when the tool mutates model state.

- [ ] **Step 5: Run registry test to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_mcp_registration.py::test_deliverable_tool_registry_exact -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit Task 1**

Run:

```zsh
git add src/server.py src/tools tests/test_mcp_registration.py
git commit -m "feat: define fdtd mcp 0.1 tool registry"
```

---

## Task 2: Add RpcClient methods for the typed API v1 surface

**Files:**
- Modify: `src/rpc_client/client.py`
- Modify: `tests/test_rpc_client_contract.py`

- [ ] **Step 1: Write route-contract tests**

Add table-driven tests in `tests/test_rpc_client_contract.py` that assert method, path, and body for:

```python
ROUTE_CASES = [
    ("project_new", ("new_device", True), "POST", "/project/new", {"name": "new_device", "discard_unsaved": True}),
    ("project_status", (), "GET", "/project/status", None),
    ("switch_to_layout", (), "POST", "/model/layout", {}),
    ("object_create", ("rectangle", "rect_1", {"x span": 1e-6}, True), "POST", "/objects", {"object_type": "rectangle", "name": "rect_1", "properties": {"x span": 1e-6}, "dry_run": True}),
    ("object_get", ("rect_1", None), "GET", "/objects/rect_1", None),
    ("material_list", (), "GET", "/materials", None),
    ("solver_get", (), "GET", "/solver", None),
    ("source_create", ("plane_source", "src", {"wavelength start": 1.5e-6}, True), "POST", "/sources", {"source_type": "plane_source", "name": "src", "properties": {"wavelength start": 1.5e-6}, "dry_run": True}),
    ("monitor_create", ("power_monitor", "mon", {"frequency points": 5}, True), "POST", "/monitors", {"monitor_type": "power_monitor", "name": "mon", "properties": {"frequency points": 5}, "dry_run": True}),
    ("analysis_group_create", ("ag", {"script": "T=1;"}, True), "POST", "/analysis-groups", {"name": "ag", "properties": {"script": "T=1;"}, "dry_run": True}),
    ("result_list", (), "GET", "/results", None),
    ("result_read", ("mon", "T"), "GET", "/results/mon/T", None),
]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_rpc_client_contract.py -q
```

Expected: FAIL on missing `RpcClient` methods.

- [ ] **Step 3: Implement minimal methods**

Add methods to `src/rpc_client/client.py` using existing `_get` and `_post`. Use `quote(name, safe="")` for path segments.

Example:

```python
def project_new(self, name: str = "untitled", discard_unsaved: bool = False) -> dict:
    return self._post("/project/new", {"name": name, "discard_unsaved": discard_unsaved})

def object_create(self, object_type: str, name: str, properties: dict, dry_run: bool = False) -> dict:
    return self._post(
        "/objects",
        {
            "object_type": object_type,
            "name": name,
            "properties": properties,
            "dry_run": dry_run,
        },
    )
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_rpc_client_contract.py -q
```

Expected: all client contract tests pass.

- [ ] **Step 5: Commit Task 2**

Run:

```zsh
git add src/rpc_client/client.py tests/test_rpc_client_contract.py
git commit -m "feat: add typed api v1 rpc client methods"
```

---

## Task 3: Implement shared operation schemas and dry-run script compilation

**Files:**
- Create: `src/fdtd_schema.py`
- Create: `src/fdtd_script.py`
- Create: `src/fdtd_operations.py`
- Create: `tests/test_fdtd_operations.py`

- [ ] **Step 1: Write tests for stable JSON, fingerprints, and object dry-run**

Create `tests/test_fdtd_operations.py`:

```python
from src.fdtd_operations import compile_object_create, validate_object_type
from src.fdtd_schema import fingerprint_json, stable_json_dumps


def test_stable_json_and_fingerprint_are_order_independent():
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}
    assert stable_json_dumps(left) == stable_json_dumps(right)
    assert fingerprint_json(left) == fingerprint_json(right)


def test_object_create_dry_run_script_and_warnings():
    result = compile_object_create(
        object_type="rectangle",
        name="rect_1",
        properties={"x span": 1e-6, "material": "Si"},
    )
    assert result["ok"] is True
    assert "addrect;" in result["script"]
    assert 'set("name","rect_1");' in result["script"]
    assert 'set("x span",1e-06);' in result["script"]
    assert result["script_sha256"].startswith("sha256:")


def test_source_type_rejected_from_generic_object_create():
    assert validate_object_type("plane_source") == {
        "ok": False,
        "error": {
            "type": "use_typed_domain_tool",
            "message": "Use fdtd_source_create for object_type=plane_source.",
            "details": {"tool": "fdtd_source_create"},
        },
    }
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_fdtd_operations.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement helpers**

Implement:

- `stable_json_dumps(value)`: `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`。
- `fingerprint_json(value)`: SHA-256 over stable JSON, returned as `sha256:<hex>`.
- `quote_lsf_string(value)`: JSON string quoting for safe Lumerical script strings.
- `format_lsf_value(value)`: bool/number/string/list conversion.
- `compile_object_create(object_type, name, properties)`: produce deterministic script and `script_sha256`.
- `validate_object_type(object_type)`: accept only `fdtd_region`, `rectangle`, `circle`, `ring`, `polygon`, `structure_group`, `mesh_override` for generic objects.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_fdtd_operations.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit Task 3**

Run:

```zsh
git add src/fdtd_schema.py src/fdtd_script.py src/fdtd_operations.py tests/test_fdtd_operations.py
git commit -m "feat: add fdtd operation compiler primitives"
```

---

## Task 4: Add Windows fake-lumapi adapter and typed RPC routes

**Files:**
- Create: `src/windows_fdtd_adapter.py`
- Modify: `rpc_server.py`
- Modify: `tests/test_rpc_server_contract.py`
- Create: `tests/test_fdtd_20_step_fake_lumapi.py`

- [ ] **Step 1: Write fake-lumapi 20-step route test**

Create a fake backend in `tests/test_fdtd_20_step_fake_lumapi.py` that records commands and values. The test must call Flask routes through `create_app(fake_backend=...)` and cover:

- `/project/new`
- `/objects`
- `/materials`
- `/solver`
- `/sources`
- `/monitors`
- `/analysis-groups`
- `/simulation/run`
- `/results`
- `/results/<object>/<result>`

Assert each response has `ok=true` and the fake backend recorded the expected operation names in order.

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_fdtd_20_step_fake_lumapi.py -q
```

Expected: FAIL because routes do not exist.

- [ ] **Step 3: Implement `WindowsFdtdAdapter`**

Create adapter methods:

- `project_new(name, discard_unsaved)`
- `project_status()`
- `switch_to_layout()`
- `object_create(object_type, name, properties, dry_run)`
- `object_list(scope, object_type)`
- `object_get(name, properties)`
- `object_update(name, properties, dry_run)`
- `object_copy(name, new_name, transform, dry_run)`
- `object_rename(name, new_name, dry_run)`
- `object_delete(name, dry_run)`
- `group_update(group_name, add, remove, dry_run)`
- `material_create/list/get/update/assign/fit_diagnose`
- `solver_get/update/mesh_diagnose/resource_estimate`
- `source_create/get/update`
- `monitor_create/get/update`
- `analysis_group_create/get/update`
- `simulation_run/status`
- `result_list/describe/read/download`

For `dry_run=true`, return compiled script without touching fake or real backend.

- [ ] **Step 4: Wire routes in `rpc_server.py`**

Add Flask route groups from the spec. Reuse existing v1 envelope and `RpcError` handling. Each mutating route reads `dry_run` from JSON body and returns the adapter result.

- [ ] **Step 5: Run fake-lumapi route tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_fdtd_20_step_fake_lumapi.py tests/test_rpc_server_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 4**

Run:

```zsh
git add src/windows_fdtd_adapter.py rpc_server.py tests/test_rpc_server_contract.py tests/test_fdtd_20_step_fake_lumapi.py
git commit -m "feat: add typed fdtd rpc routes"
```

---

## Task 5: Implement DeviceRecipe validate and compile

**Files:**
- Create: `src/device_recipe.py`
- Create: `tests/test_device_recipe.py`
- Modify: `src/tools/recipes.py`

- [ ] **Step 1: Write Recipe validation tests**

Create tests for:

- required parameter with `source_ref.locator` passes。
- required parameter without locator fails with `missing_required_source_ref`。
- non-critical default without `assumption.reason` fails with `missing_assumption`。
- expression `${pillar_radius} * 2` resolves。
- Python-like expression `__import__("os")` fails with `invalid_expression`。
- compile output contains `recipe_fingerprint`, `compile_fingerprint`, `script_sha256`, object lifecycle list, assumptions report, raw hook hashes。

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_device_recipe.py -q
```

Expected: FAIL because `src.device_recipe` does not exist.

- [ ] **Step 3: Implement expression parser and validator**

Implement a restricted AST parser that accepts only:

- numeric constants
- parameter references written as `${name}`
- `+`, `-`, `*`, `/`
- parentheses
- unary plus and minus

Return structured errors for undeclared parameters, non-finite values, division by zero, and unsupported syntax.

- [ ] **Step 4: Implement compiler**

Compiler order:

```text
pre_geometry
materials
geometry
post_geometry
simulation region
boundaries
mesh
sources
monitors
save model
```

`pre_run` and `post_run` are included in the report but not executed in build-only script.

- [ ] **Step 5: Wire MCP tools**

`src/tools/recipes.py` must expose:

- `fdtd_device_recipe_validate(recipe: dict) -> dict`
- `fdtd_device_recipe_compile(recipe: dict) -> dict`
- `fdtd_device_recipe_build(recipe: dict, compile_fingerprint: str, output_fsp: str, approved: bool) -> dict`

The build tool must recompile locally and reject mismatched fingerprint before calling RPC.

- [ ] **Step 6: Run tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_device_recipe.py tests/test_mcp_registration.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 5**

Run:

```zsh
git add src/device_recipe.py src/tools/recipes.py tests/test_device_recipe.py
git commit -m "feat: add device recipe compiler"
```

---

## Task 6: Add Recipe build route with fingerprint gate

**Files:**
- Modify: `src/rpc_client/client.py`
- Modify: `rpc_server.py`
- Modify: `tests/test_rpc_client_contract.py`
- Modify: `tests/test_rpc_server_contract.py`

- [ ] **Step 1: Add client/server tests**

Test client method:

```python
rpc.recipe_build(
    recipe={"schema_version": "1.0"},
    compile_fingerprint="sha256:abc",
    output_fsp="C:\\Users\\me\\device.fsp",
    approved=True,
)
```

Expected route: `POST /recipes/build` with exact JSON keys `recipe`, `compile_fingerprint`, `output_fsp`, `approved`。

Server test must assert:

- `approved=false` returns `ok=false`, `error.type="approval_required"`。
- mismatched compile fingerprint returns `compile_fingerprint_mismatch`。
- matching fingerprint saves `.fsp` through fake backend and returns `model_path`。

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_rpc_client_contract.py tests/test_rpc_server_contract.py -q
```

Expected: FAIL on missing `/recipes/build`.

- [ ] **Step 3: Implement route and client method**

Windows route must:

1. Re-run `compile_device_recipe(recipe)`。
2. Compare computed compile fingerprint with request fingerprint。
3. Refuse if active real job is running。
4. Create clean project。
5. Execute build-only script。
6. Save `output_fsp` after path boundary check。
7. Return object list, model path, and log summary。

- [ ] **Step 4: Run tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_rpc_client_contract.py tests/test_rpc_server_contract.py tests/test_device_recipe.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 6**

Run:

```zsh
git add src/rpc_client/client.py rpc_server.py tests/test_rpc_client_contract.py tests/test_rpc_server_contract.py
git commit -m "feat: add recipe build approval gate"
```

---

## Task 7: Implement Generic SweepPlan validate and plan

**Files:**
- Create: `src/generic_sweep.py`
- Create: `tests/test_generic_sweep.py`
- Modify: `src/tools/generic_sweeps.py`

- [ ] **Step 1: Write deterministic expansion tests**

Create tests asserting:

- explicit `values` preserves order。
- `range` uses inclusive start/stop and exact final stop。
- last declared parameter changes fastest。
- duplicate values fail。
- task count above `max_tasks` fails without truncation。
- same Recipe/SweepPlan generates same packet fingerprint。

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_generic_sweep.py -q
```

Expected: FAIL because `src.generic_sweep` does not exist.

- [ ] **Step 3: Implement `validate_sweep_plan` and `plan_generic_sweep`**

Implementation must:

- accept inline Recipe or Recipe file path, not both。
- verify every sweep parameter exists in Recipe `parameters`。
- expand Cartesian product in declaration order。
- generate stable `task_id` from recipe fingerprint, sweep fingerprint, index, and parameter snapshot。
- compile every task Recipe using `src.device_recipe`。
- return exact plan packet, task manifest, output paths, task count, and coverage risks。

- [ ] **Step 4: Wire MCP tools**

`fdtd_generic_sweep_validate` runs local validation without compiling all task scripts。

`fdtd_generic_sweep_plan` runs full task expansion and script compilation。

`fdtd_generic_sweep_start` re-plans, checks `packet_fingerprint`, checks `approved=true`, and calls RPC only for `mode="mock"` or `mode="real"`。

- [ ] **Step 5: Run tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_generic_sweep.py tests/test_mcp_registration.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 7**

Run:

```zsh
git add src/generic_sweep.py src/tools/generic_sweeps.py tests/test_generic_sweep.py
git commit -m "feat: add generic sweep planner"
```

---

## Task 8: Add `recipe-sweep` persistent job support

**Files:**
- Modify: `src/job_store.py`
- Modify: `rpc_server.py`
- Create: `tests/test_recipe_sweep_job.py`
- Modify: `tests/test_rpc_server_jobs.py`

- [ ] **Step 1: Write job-store tests**

Test that `/jobs/plan` with `job_type="recipe-sweep"` creates:

```text
inputs/recipe.json
inputs/sweep_plan.json
compiled/compile_report.json
compiled/scripts/<task_id>.lsf
tasks/<task_id>.json
```

Each task JSON must include `parameters`, `script_sha256`, `synthetic`, `status`, `model_path`, and `metrics_path` keys.

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_recipe_sweep_job.py tests/test_rpc_server_jobs.py -q
```

Expected: FAIL because `recipe-sweep` is unsupported.

- [ ] **Step 3: Implement plan and mock start**

In `/jobs/plan`:

- normalize Recipe and SweepPlan using shared compiler。
- recalculate fingerprints。
- reject expected fingerprint mismatch。
- write planned job directory。

In `/jobs/start` with `mode="mock"`:

- create same job structure。
- write synthetic metrics with `synthetic=true`。
- write `summary.json` and status `succeeded`。
- send Feishu terminal notification through existing notification path if webhook exists。

- [ ] **Step 4: Implement real start handshake**

For `mode="real"`:

- require exact packet fingerprint。
- require real-run approval object。
- create job and task files。
- return `202 + job_id` without waiting for solve。
- do not poll after submission。

- [ ] **Step 5: Run tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_recipe_sweep_job.py tests/test_rpc_server_jobs.py tests/test_job_store.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 8**

Run:

```zsh
git add src/job_store.py rpc_server.py tests/test_recipe_sweep_job.py tests/test_rpc_server_jobs.py
git commit -m "feat: add recipe sweep persistent jobs"
```

---

## Task 9: Preserve SimulationPlan compatibility through the generic core

**Files:**
- Modify: `src/simulation_plan.py`
- Modify: `src/plan_compilers/metasurface.py`
- Modify: `tests/test_simulation_plan.py`
- Modify: `tests/test_metasurface_plan_compiler.py`
- Modify: `tests/test_simulation_plan_workflow.py`

- [ ] **Step 1: Add compatibility tests**

Add tests asserting existing metasurface inputs still produce the same:

- ratio/period/height parameter semantics。
- task count。
- plan fingerprint approval behavior。
- max task budget。
- `EXPRESS_MODE=0` CPU default。

Also assert compiler internally exposes a `to_device_recipe_and_sweep_plan()` result with DeviceRecipe and Generic SweepPlan fingerprints.

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_simulation_plan.py tests/test_metasurface_plan_compiler.py tests/test_simulation_plan_workflow.py -q
```

Expected: existing tests pass or new compatibility assertions fail until bridge is implemented.

- [ ] **Step 3: Implement bridge**

Add a conversion function:

```python
def metasurface_plan_to_recipe_sweep(plan: dict) -> dict:
    return {
        "recipe": normalized_recipe,
        "sweep_plan": normalized_sweep_plan,
        "compatibility": {
            "source": "metasurface SimulationPlan v0.1",
            "preserves_legacy_fingerprint": True,
        },
    }
```

Keep existing public tool responses stable. Add new fingerprints as extra fields only.

- [ ] **Step 4: Run compatibility tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_simulation_plan.py tests/test_metasurface_plan_compiler.py tests/test_simulation_plan_workflow.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 9**

Run:

```zsh
git add src/simulation_plan.py src/plan_compilers/metasurface.py tests/test_simulation_plan.py tests/test_metasurface_plan_compiler.py tests/test_simulation_plan_workflow.py
git commit -m "feat: bridge simulationplan to generic recipe sweep"
```

---

## Task 10: Add MCP stdio protocol acceptance tests

**Files:**
- Create: `tests/test_mcp_stdio_acceptance.py`
- Modify: `requirements-dev.txt`

- [ ] **Step 1: Write stdio acceptance test**

The test must launch:

```zsh
FDTD_RPC_URL=http://127.0.0.1:59999 .venv/bin/python -m src.server
```

Then perform MCP:

1. `initialize`
2. `tools/list`
3. `tools/call(fdtd_health)`
4. `tools/call(fdtd_project_status)`
5. `tools/call(fdtd_object_create, dry_run=true)`
6. `tools/call(fdtd_source_create, dry_run=true)`
7. `tools/call(fdtd_monitor_create, dry_run=true)`
8. `tools/call(fdtd_device_recipe_validate)`
9. `tools/call(fdtd_device_recipe_compile)`
10. `tools/call(fdtd_generic_sweep_plan)`
11. `tools/call(fdtd_generic_sweep_start, mode=mock)`

For offline CI, `fdtd_health` may return `connection_error`; dry-run and pure compiler calls must succeed.

- [ ] **Step 2: Run test to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_mcp_stdio_acceptance.py -q
```

Expected: FAIL until server and tools support stdio calls.

- [ ] **Step 3: Fix protocol issues**

Fix only serialization, tool signatures, and offline dry-run behavior surfaced by this test.

- [ ] **Step 4: Run test to verify GREEN**

Run:

```zsh
.venv/bin/python -m pytest tests/test_mcp_stdio_acceptance.py -q
```

Expected: stdio acceptance passes without Windows.

- [ ] **Step 5: Commit Task 10**

Run:

```zsh
git add tests/test_mcp_stdio_acceptance.py requirements-dev.txt src
git commit -m "test: add mcp stdio acceptance coverage"
```

---

## Task 11: Add Mac installer and three-client config transaction

**Files:**
- Create: `requirements-runtime.txt`
- Create: `scripts/macos/install_mcp.sh`
- Create: `scripts/macos/configure_mcp_clients.py`
- Create: `tests/test_macos_mcp_config.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write config transaction tests**

Tests must use temporary HOME and project root. Cover:

- Codex TOML writes only `[mcp_servers.fdtd]`。
- Claude `.mcp.json` preserves existing servers and replaces only `fdtd`。
- Hermes YAML preserves unrelated config and appends `fdtd` to explicit `toolsets` only when missing。
- invalid target config causes no files to change。
- backups use `.backup-YYYYMMDD-HHMMSS` suffix。

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_macos_mcp_config.py -q
```

Expected: FAIL because scripts do not exist.

- [ ] **Step 3: Implement config writer**

Use structured parsers:

- TOML: Python 3.11 `tomllib` for read and a small deterministic writer for the `fdtd` block。
- JSON: `json.load` and `json.dump(indent=2, ensure_ascii=False)`。
- YAML: use existing dependency if already present; if not, add `PyYAML` to `requirements-runtime.txt`。

Write all target files to temporary files first. After all parse and render steps succeed, replace files atomically.

- [ ] **Step 4: Implement shell installer**

`scripts/macos/install_mcp.sh` must:

- require Python 3.10+。
- create `.venv`。
- install `requirements-runtime.txt`。
- accept `--rpc-url` and `--connection-mode`。
- run `/health` check and clearly report failure。
- call `configure_mcp_clients.py`。
- print exact next commands for Codex、Claude Code、Hermes。

- [ ] **Step 5: Run tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_macos_mcp_config.py -q
scripts/macos/install_mcp.sh --help
```

Expected: pytest passes; help exits 0.

- [ ] **Step 6: Commit Task 11**

Run:

```zsh
git add requirements-runtime.txt scripts/macos tests/test_macos_mcp_config.py .gitignore
git commit -m "feat: add mac mcp installer"
```

---

## Task 12: Add Windows setup and persistent local state directory

**Files:**
- Create: `scripts/windows/setup_rpc.ps1`
- Modify: `scripts/windows/setup_rpc.bat`
- Modify: `scripts/windows/manage_rpc.ps1`
- Modify: `scripts/windows/start_rpc.bat`
- Modify: `scripts/windows/status_rpc.bat`
- Modify: `scripts/windows/stop_rpc.bat`
- Modify: `scripts/windows/restart_rpc.bat`
- Create: `tests/test_windows_scripts_static.py`

- [ ] **Step 1: Write static script tests**

Tests must assert:

- all `.bat` entrypoints call PowerShell or `manage_rpc.ps1` consistently。
- `setup_rpc.ps1` writes `%LOCALAPPDATA%\fdtd-mcp\config\rpc.env`。
- `manage_rpc.ps1` uses `pythonw.exe` for background start。
- `FDTD_FEISHU_WEBHOOK` is not written into `rpc.env`。
- scripts expose `/?, --help, or -Help` help output strings。

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_windows_scripts_static.py -q
```

Expected: FAIL until scripts are updated.

- [ ] **Step 3: Implement setup**

`setup_rpc.ps1` must:

- detect or prompt for Lumerical v242 Python。
- verify `import lumapi` using selected Python。
- install Flask if missing。
- select `ssh` or `lan`。
- write `rpc.env` with `FDTD_PYTHON`, `LUMAPI_PATH`, `FDTD_RPC_HOST`, `FDTD_RPC_PORT`, `FDTD_JOB_ROOT`。
- create Windows private-network firewall rule only for `lan`。
- start RPC and call `/health`。

- [ ] **Step 4: Implement management**

`manage_rpc.ps1` must implement `start`, `status`, `stop`, `restart` using:

- `%LOCALAPPDATA%\fdtd-mcp\run\rpc_server.pid`
- `%LOCALAPPDATA%\fdtd-mcp\logs\rpc_server.out.log`
- `%LOCALAPPDATA%\fdtd-mcp\logs\rpc_server.err.log`
- stale PID detection。
- port ownership display。
- health check display。

- [ ] **Step 5: Run static tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_windows_scripts_static.py -q
```

Expected: all static script tests pass.

- [ ] **Step 6: Commit Task 12**

Run:

```zsh
git add scripts/windows tests/test_windows_scripts_static.py
git commit -m "feat: add windows rpc setup workflow"
```

---

## Task 13: Add parameter-file validation without physical claims

**Files:**
- Create: `scripts/validate_parameter_file.py`
- Create: `tests/fixtures/synthetic_parameters.json`
- Create: `tests/test_parameter_file_validation.py`

- [ ] **Step 1: Write tests**

Tests must assert:

- JSON parse errors are reported。
- parameter order and numeric values are preserved through Recipe/SweepPlan validate and plan。
- task count equals Cartesian product size。
- no call to `/jobs/start` occurs。
- output contains `physical_conclusion=false`。

- [ ] **Step 2: Run tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_parameter_file_validation.py -q
```

Expected: FAIL because script does not exist.

- [ ] **Step 3: Implement script**

CLI:

```zsh
.venv/bin/python scripts/validate_parameter_file.py --parameter-file tests/fixtures/synthetic_parameters.json
```

Output JSON fields:

- `ok`
- `parameter_count`
- `task_count`
- `recipe_fingerprint`
- `sweep_fingerprint`
- `packet_fingerprint`
- `technical_validation=true`
- `physical_conclusion=false`

- [ ] **Step 4: Run tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_parameter_file_validation.py -q
.venv/bin/python scripts/validate_parameter_file.py --help
```

Expected: pytest passes; help exits 0.

- [ ] **Step 5: Commit Task 13**

Run:

```zsh
git add scripts/validate_parameter_file.py tests/fixtures/synthetic_parameters.json tests/test_parameter_file_validation.py
git commit -m "feat: add parameter file validation"
```

---

## Task 14: Add Windows minimal solver smoke

**Files:**
- Create: `scripts/windows/minimal_solver_smoke.py`
- Create: `tests/test_minimal_solver_smoke_static.py`
- Modify: `docs/WINDOWS_RUNBOOK.md`

- [ ] **Step 1: Write static smoke tests**

Tests must assert the script:

- creates one project。
- creates one fixed simple structure。
- creates one small FDTD region。
- creates one source。
- creates one monitor。
- creates one analysis group。
- runs once。
- reads one result。
- downloads or writes one structured result file。
- writes `technical_smoke=true` and `physical_conclusion=false` in the report。

- [ ] **Step 2: Run static tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_minimal_solver_smoke_static.py -q
```

Expected: FAIL because script does not exist.

- [ ] **Step 3: Implement script**

The script must accept:

```cmd
scripts\windows\minimal_solver_smoke.py --rpc http://127.0.0.1:5000 --output %LOCALAPPDATA%\fdtd-mcp\smoke
```

It must run exactly one model and one solve. It must not create sweep jobs or optimization loops.

- [ ] **Step 4: Run static tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_minimal_solver_smoke_static.py -q
```

Expected: static tests pass.

- [ ] **Step 5: Commit Task 14**

Run:

```zsh
git add scripts/windows/minimal_solver_smoke.py tests/test_minimal_solver_smoke_static.py docs/WINDOWS_RUNBOOK.md
git commit -m "feat: add windows minimal solver smoke"
```

---

## Task 15: Rewrite user-facing docs for MCP delivery

**Files:**
- Modify: `README.md`
- Modify: `REQUIREMENTS.md`
- Modify: `TECH_STACK.md`
- Modify: `docs/RPC_API_V1.md`
- Modify: `docs/WINDOWS_RUNBOOK.md`
- Create: `docs/MCP_USER_GUIDE.md`
- Create: `docs/FDTD_OPERATIONS_V1.md`
- Create: `docs/DEVICE_RECIPE_V1.md`
- Create: `docs/GENERIC_SWEEP_PLAN_V1.md`
- Modify: `DEV_LOG.md`

- [ ] **Step 1: Write docs lint tests**

Create or extend docs tests to assert:

- README contains “五分钟安装”, “SSH 隧道”, “局域网直连”, “Codex”, “Claude Code”, “Hermes”。
- `docs/MCP_USER_GUIDE.md` lists all 69 tools。
- `docs/FDTD_OPERATIONS_V1.md` maps all 20 FDTD steps。
- `docs/DEVICE_RECIPE_V1.md` documents source refs, assumptions, expressions, raw hooks。
- `docs/GENERIC_SWEEP_PLAN_V1.md` documents values/range, task order, max_tasks, approval。
- README and REQUIREMENTS do not present C4/C5真实 sweep as MCP completion prerequisite。

- [ ] **Step 2: Run docs tests to verify RED**

Run:

```zsh
.venv/bin/python -m pytest tests/test_docs_current_state.py -q
```

Expected: FAIL until docs are rewritten or the docs test file is added.

- [ ] **Step 3: Rewrite docs**

Write concise Chinese docs. Keep history in existing implementation plans and DEV_LOG; make README the current entry point.

- [ ] **Step 4: Run docs tests**

Run:

```zsh
.venv/bin/python -m pytest tests/test_docs_current_state.py -q
```

Expected: docs tests pass.

- [ ] **Step 5: Commit Task 15**

Run:

```zsh
git add README.md REQUIREMENTS.md TECH_STACK.md docs/RPC_API_V1.md docs/WINDOWS_RUNBOOK.md docs/MCP_USER_GUIDE.md docs/FDTD_OPERATIONS_V1.md docs/DEVICE_RECIPE_V1.md docs/GENERIC_SWEEP_PLAN_V1.md DEV_LOG.md tests/test_docs_current_state.py
git commit -m "docs: document personal fdtd mcp delivery"
```

---

## Task 16: Final 0.1.0 verification and release marker

**Files:**
- Create: `src/version.py`
- Modify: `src/__init__.py`
- Create: `tests/test_version.py`
- Modify: `RETROSPECTIVE.md`

- [ ] **Step 1: Add version test**

Test:

```python
from src.version import __version__


def test_version_is_single_source_for_0_1_0():
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run complete offline verification**

Run:

```zsh
.venv/bin/python -m compileall -q rpc_server.py src scripts tests
.venv/bin/python -m pytest -q
```

Expected: all offline tests pass.

- [ ] **Step 3: Run Mac installer help and parameter validation**

Run:

```zsh
scripts/macos/install_mcp.sh --help
.venv/bin/python scripts/validate_parameter_file.py --parameter-file tests/fixtures/synthetic_parameters.json
```

Expected: help exits 0; validation exits 0 and prints `physical_conclusion=false`。

- [ ] **Step 4: Run Windows manual checks**

On Windows CMD:

```cmd
scripts\windows\setup_rpc.bat --help
scripts\windows\status_rpc.bat
```

Expected: help/status display config path, PID, log path, host, port, and health status.

- [ ] **Step 5: Run Windows minimal solver smoke**

On Windows CMD after RPC health passes:

```cmd
"F:\Program Files\Lumerical\v242\python\python.exe" scripts\windows\minimal_solver_smoke.py --rpc http://127.0.0.1:5000 --output "%LOCALAPPDATA%\fdtd-mcp\smoke"
```

Expected: report contains `technical_smoke=true`, `physical_conclusion=false`, one run, one result read, one result file.

- [ ] **Step 6: Record retrospective**

Append a short `2026-06-20 - 0.1.0 MCP 交付验收` entry to `RETROSPECTIVE.md` with:

- offline test command and result。
- Windows smoke command and result。
- known non-goals that remain non-goals。
- next recommended physical-use workflow。

- [ ] **Step 7: Commit Task 16**

Run:

```zsh
git add src/version.py src/__init__.py tests/test_version.py RETROSPECTIVE.md
git commit -m "chore: mark fdtd mcp 0.1.0"
```

---

## Self-Review Checklist

- Spec coverage:
  - 通用 FDTD 操作闭环：Tasks 1-4, 10, 14。
  - DeviceRecipe：Tasks 5-6。
  - Generic SweepPlan：Tasks 7-8。
  - SimulationPlan compatibility：Task 9。
  - Mac install and three clients：Task 11。
  - Windows setup and migration：Task 12。
  - 参数集无损传递：Task 13。
  - 文档交付：Task 15。
  - 0.1.0 release and verification：Task 16。
- Placeholder scan:
  - Plan contains no placeholder markers。
  - Plan contains no instruction to silently fill missing validation。
  - Every task has concrete files, test command, expected result, and commit command。
- Type consistency:
  - MCP tool names match the 69-tool spec list。
  - DeviceRecipe uses `recipe_fingerprint`, `compile_fingerprint`, and `script_sha256` consistently。
  - Generic SweepPlan uses `sweep_fingerprint`, `packet_fingerprint`, `task_id`, and `script_sha256` consistently。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-20-deliverable-personal-fdtd-mcp-0-1-0.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.
