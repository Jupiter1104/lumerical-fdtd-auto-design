# MCP Jobs API 接线设计

## 决策

先把 MCP Server 从旧 `/sweep/*` 工作流接到当前已验证的新 `/jobs/*` API v1。这个阶段只解决“Agent 能通过 MCP 调用持久 job 状态机”的问题，不实现自然语言计划编译、不新增器件 recipe、不启动真实 FDTD。

## 背景

当前项目已经具备：

- Windows RPC API v1，默认端口 `5000`。
- 持久 `/jobs/plan`、`/jobs/start`、`/jobs/<job_id>`、`/jobs/<job_id>/tasks`、`/jobs/<job_id>/resume`。
- `metasurface-sweep` 原生 Phase 1-4，真实 2×2 验证通过，质量报告和 evidence-first 输出已落盘。
- Mac 端 `RpcClient` 已有 `jobs_plan/start/get/tasks/resume` 方法。

当前缺口：

- MCP `simulation.py` 仍暴露旧式 `fdtd_sweep_*` 工具，并调用 `/sweep/*`。
- 新 `rpc_server.py` 没有 `/sweep/*` 路由。
- Claude Code 即使接上 MCP，也无法自然使用当前已经验证过的 `/jobs/*` 状态机。

## 目标

1. MCP 暴露新 job 工具：
   - `fdtd_job_plan`
   - `fdtd_job_start`
   - `fdtd_job_status`
   - `fdtd_job_tasks`
   - `fdtd_job_resume`
2. MCP 暴露 metasurface 专用便捷工具：
   - `fdtd_metasurface_sweep_plan`
   - `fdtd_metasurface_sweep_start`
3. 所有新工具都走 `RpcClient.jobs_*`，不调用旧 `/sweep/*`。
4. `real` job 工具必须保留审批语义：请求里必须有 `approval={"approved": true, "approved_for": "real_run"}`，工具文档必须提醒真实运行需要人工批准。
5. 新增 `.mcp.json`，默认让 Claude Code 通过 `FDTD_RPC_URL=http://localhost:5000` 连接本地 SSH 隧道或 Windows 直连代理。
6. 补测试确认：
   - MCP 注册包含新 job 工具。
   - `RpcClient` job 方法路由正确。
   - metasurface 便捷工具构造的请求符合 `/jobs/*` 契约。

## 非目标

- 不修改 Windows `rpc_server.py` 的 job 行为。
- 不启动真实 FDTD，不新增真实仿真。
- 不实现自然语言 `SimulationPlan` compiler。
- 不新增 waveguide/MMI/ring 等器件 recipe。
- 不删除旧 `fdtd_sweep_*` 工具；本阶段只标记为 legacy，避免一次性破坏兼容。
- 不实现结果文件下载新协议；继续使用当前 job summary/evidence 路径作为主要回传。

## 工具设计

### 通用 job 工具

`fdtd_job_plan(request: dict) -> dict`

- 调用 `POST /jobs/plan`。
- 用于 `plan` 模式和成本预览。
- 返回 job manifest、status、summary 和 task_count。

`fdtd_job_start(request: dict) -> dict`

- 调用 `POST /jobs/start`。
- 支持 `mock` 和 `real`。
- `real` 请求必须由调用者显式传入 approval。
- 长任务可能返回 `202 + job_id`，调用者继续用 status/tasks 轮询。

`fdtd_job_status(job_id: str) -> dict`

- 调用 `GET /jobs/<job_id>`。
- 返回 manifest/status/summary。

`fdtd_job_tasks(job_id: str) -> dict`

- 调用 `GET /jobs/<job_id>/tasks`。
- 返回逐 task 状态。

`fdtd_job_resume(job_id: str, request: Optional[dict] = None) -> dict`

- 调用 `POST /jobs/<job_id>/resume`。
- 默认 `{}`。
- 只用于用户明确要求 resume 的场景。

### Metasurface 便捷工具

`fdtd_metasurface_sweep_plan(ratio_list: Optional[List[float]], period_list: Optional[List[float]], base_height: float, base_period: float, phases: Optional[List[int]], template: str, include_models: bool) -> dict`

- 构造：
  ```json
  {
    "mode": "plan",
    "job_type": "metasurface-sweep",
    "sweep": {
      "template": "templates/metasurface/base_model.fsp",
      "phases": [1, 2, 3, 4],
      "hide": true,
      "include_models": false,
      "config": {
        "SWEEP_Y_AXIS": "period",
        "RATIO_LIST": [0.2, 0.8],
        "PERIOD_LIST": [3.9e-7, 5.4e-7],
        "BASE_HEIGHT": 7e-7,
        "BASE_PERIOD": 4.7e-7,
        "FDTD_PROCESSES": 1,
        "FDTD_CAPACITY": 1,
        "EXPRESS_MODE": 0
      }
    }
  }
  ```
- 调用 `fdtd_job_plan` 的同一路径。
- 默认 CPU：`EXPRESS_MODE=0`。

`fdtd_metasurface_sweep_start(mode: str, ratio_list: Optional[List[float]], period_list: Optional[List[float]], base_height: float, base_period: float, phases: Optional[List[int]], template: str, include_models: bool, approved: bool) -> dict`

- 构造同上，但 `mode` 可为 `mock` 或 `real`。
- `real` 时必须要求 `approved=True`；工具内部写入 `approval={"approved": true, "approved_for": "real_run"}`。
- `mock` 不需要 approval。
- 默认 `mode="mock"`，避免自然语言误触发真实求解。

## 数据流

```text
Claude Code / Agent
  -> MCP tool: fdtd_metasurface_sweep_start(mode="mock" or "real")
  -> RpcClient.jobs_start(request)
  -> Windows RPC /jobs/start
  -> JobStore + NativeSweepRunner
  -> /jobs/<job_id> and /jobs/<job_id>/tasks polling
  -> summary / quality_report / evidence paths
```

## 安全与约束

- 工具 docstring 必须清楚区分 `plan`、`mock`、`real`。
- `real` 默认不开启；必须显式 `mode="real"` 且 `approved=True`。
- 工具不自动扩大 sweep 参数空间。
- 工具不自动改变 mesh/boundary/resource；当前 metasurface 默认 CPU `EXPRESS_MODE=0`。
- 工具不下载逐点 `.fsp`。
- 旧 `fdtd_sweep_*` 文档标记为 legacy，提示新工作流优先用 `fdtd_job_*` 和 `fdtd_metasurface_sweep_*`。

## 测试策略

离线测试为主，不依赖 Windows 或 Lumerical：

1. `tests/test_rpc_client_contract.py`
   - 已有 `jobs_start` 路由测试，补齐 `jobs_plan/get/tasks/resume` 或确认覆盖。
2. `tests/test_mcp_registration.py`
   - 新工具名必须出现在 MCP 注册列表。
3. 新增 `tests/test_mcp_jobs_tools.py`
   - 使用 fake `RpcClient` 注册工具，调用 metasurface 便捷工具，断言构造的 request 正确。
   - 覆盖 `mock` 默认不带 approval。
   - 覆盖 `real` 未批准时返回本地错误，不发请求。
   - 覆盖 `real` 已批准时 approval 字段精确为 `real_run`。

## 验收标准

- `src/server.py` 注册后 MCP 工具列表包含新 job 工具和 metasurface 便捷工具。
- 新工具调用的 HTTP 路由全部是 `/jobs/*`。
- 默认 metasurface 便捷工具为 `mock` + CPU `EXPRESS_MODE=0`。
- `real` 便捷工具无批准时被本地拒绝，不触发远端请求。
- `.mcp.json` 存在，默认使用 `FDTD_RPC_URL=http://localhost:5000`。
- 本地验证通过：
  ```bash
  .venv/bin/python -m compileall -q rpc_server.py src scripts tests
  .venv/bin/python -m pytest -q
  ```
