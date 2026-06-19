# RPC API v1 速查

## 状态

- 代码状态：Windows clone 已同步并加载 raw lumapi `close()` detach/timeout 修复。
- 离线验证：Mac 上新增 `/jobs/*` 离线契约测试，不依赖 Lumerical。
- Windows 状态：开发期 `5004` 已完成真实 v1 smoke 和真实 2×2 原生 `metasurface-sweep` 验证；当前默认端口为 `5000`，Windows 已同步并完成 health/mock smoke。
- Job 状态：`/jobs/start` 支持短 `real geometry-smoke`；`metasurface-sweep` 已支持逐 sample task、原生 Phase 1-4、质量报告和 evidence index。真实 sweep 在新 v1 服务内异步执行，启动成功返回 HTTP 202。每个真实 sweep manifest 记录模板路径、大小、mtime 和 SHA-256。
- 过渡期：旧 Autosweep 只作为历史 baseline，不再是仓库内 `rpc_server.py` 的运行时依赖；本文件只描述新 v1 服务。

## Envelope

成功：

```json
{"ok": true}
```

失败：

```json
{
  "ok": false,
  "error": {
    "type": "validation_error",
    "message": "cmd is required.",
    "details": {}
  }
}
```

约定：

- 参数错误：HTTP 400。
- 无会话或重复启动：HTTP 409。
- 文件不存在：HTTP 404。
- 未处理后端异常：HTTP 500。
- Client 超时返回 `error.type=timeout`，`details.remote_state=unknown`。
- `/session/close` 成功响应可带 `close_state`：`closed`、`timed_out` 或 `error`。

## 已实现路由

| 方法 | 路由 | 说明 |
|---|---|---|
| GET | `/health` | RPC 进程健康、API 版本和会话摘要 |
| GET | `/status` | 当前 FDTD 会话、版本和模型路径 |
| POST | `/session/start` | 启动唯一 FDTD 会话，body: `{"hide": false}` |
| POST | `/session/close` | 摘除 RPC 会话并请求 FDTD 关闭；raw lumapi 关闭不返回时返回 `close_state=timed_out` 以保持服务可用 |
| POST | `/model/save` | 保存当前 `.fsp`，body: `{"file_path": "..."}` |
| POST | `/model/load` | 加载 `.fsp` |
| POST | `/debug/eval` | 受审计的 raw lumapi 调试入口 |
| POST | `/debug/getv` | 读取变量 |
| POST | `/debug/setv` | 写入变量 |
| POST | `/simulation/run` | 同步运行当前模型，仅用于短 smoke |
| POST | `/simulation/result` | 读取 monitor result |
| POST | `/simulation/electric` | 读取电场 |
| POST | `/geometry/fdtd-region` | 添加 FDTD 区域 |
| POST | `/geometry/rectangle` | 添加矩形 |
| POST | `/geometry/circle` | 添加圆形 |
| POST | `/jobs/plan` | 创建 planned job，落盘 task 清单但不执行 |
| POST | `/jobs/start` | 创建并执行 mock 或 real job；`real metasurface-sweep` 异步返回 `202 + job_id` |
| GET | `/jobs/<job_id>` | 读取 manifest/status/summary |
| GET | `/jobs/<job_id>/tasks` | 读取 task 摘要 |
| POST | `/jobs/<job_id>/resume` | 仅重试 pending/failed task |

MCP 新工作流优先使用 `fdtd_job_*` 和 `fdtd_metasurface_sweep_*`；旧 `fdtd_sweep_*` 工具仅保留为 legacy compatibility，不对应当前新 `rpc_server.py` 的 `/jobs/*` 主路径。

## 兼容旧路由

这些别名只保留在 Server 端，新 Client/MCP 不调用：

| 旧路由 | v1 路由 |
|---|---|
| `/session/stop` | `/session/close` |
| `/file/save` | `/model/save` |
| `/file/load` | `/model/load` |
| `/eval` | `/debug/eval` |
| `/getv` | `/debug/getv` |
| `/setv` | `/debug/setv` |
| `/sim/run` | `/simulation/run` |
| `/sim/getresult` | `/simulation/result` |
| `/sim/getelectric` | `/simulation/electric` |
| `/geom/addfdtd` | `/geometry/fdtd-region` |
| `/geom/addrect` | `/geometry/rectangle` |
| `/geom/addcircle` | `/geometry/circle` |

兼容响应会带：

```json
{
  "meta": {
    "deprecated_route": "/session/stop",
    "use_instead": "/session/close"
  }
}
```

## 已知限制

- `/debug/eval` 仅用于诊断，不是自然语言建模入口。
- 文件路径越界限制将在持久 job 层实现；当前 v1 服务仅在受控本地/隧道环境使用。
- `/jobs/*` 已实现 plan、start、status、tasks 和 resume；支持 `geometry-smoke` 和逐 sample `metasurface-sweep` task。
- `real metasurface-sweep` 同一时间只允许一个活动 job；运行中会拒绝破坏性 session/model/geometry/debug/simulation 操作。
- 服务重启会把残留 running job/task 标记为 interrupted/partial，等待用户显式 resume。
- 取消、并发队列、优化仍是后续工作。
- `real metasurface-sweep` resume 已实现模板 SHA-256 指纹保护；模板缺失、无指纹或 SHA-256 变化时返回 HTTP 409 `resume_conflict`。

## SimulationPlan MCP layer

SimulationPlan validation and approval run locally in the Mac MCP process.
Only an approved compiled request reaches the existing `/jobs/start` route.
The RPC Server continues to enforce its existing `real_run` approval as the
final service-side guard.
