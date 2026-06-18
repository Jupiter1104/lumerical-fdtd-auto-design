# 持久 job/task 状态机设计

## 背景

新 `5004` RPC API v1 已完成真实 Windows smoke：FDTD GUI 启动、最小建模、保存 `.fsp`、旧 `/session/stop` 兼容和 final health 全流程通过。下一步需要解决长任务的核心风险：任务只存在进程内存时，Flask 重启、Windows 重启、HTTP 超时或 Agent 上下文中断都会让运行状态不可恢复。

本设计只实现持久 job/task 状态机的第一版地基，不接入完整真实 sweep 引擎，不实现自然语言计划编译器。

## 目标

- 每次运行先创建稳定 `job_id`，并把输入、状态、任务清单和日志落盘。
- 每个 task 有稳定 `task_id` 和独立 JSON 记录。
- RPC Server 重启后可以从磁盘读取 job 和 task 状态。
- 支持幂等创建：同一 `idempotency_key` 不重复创建 job。
- 支持受限 resume：只重试未完成或失败 task，不改变物理设置。
- 搭好 `plan`、`mock`、`real` 的状态和审批语义，但第一版只执行 `mock` 和短 `geometry-smoke`。

## 非目标

- 不实现完整自然语言 `SimulationPlan` 编译器。
- 不接入旧 `5003` metasurface sweep 生产服务。
- 不运行长真实仿真或优化。
- 不实现多进程队列、取消、并发调度或 Web UI。
- 不把 mock 输出当成物理证据。

## 目录结构

所有 job 默认写入仓库工作目录下的 `jobs/`，该目录不进入 git。

```text
jobs/
└── job_YYYYMMDD_HHMMSS_<slug>/
    ├── manifest.json
    ├── status.json
    ├── summary.json
    ├── run.log
    ├── inputs/
    │   └── request.json
    ├── tasks/
    │   ├── task_0001.json
    │   └── task_0002.json
    ├── models/
    ├── results/
    └── evidence/
```

## 状态模型

### Job 状态

```text
planned -> queued -> running -> succeeded
                         ├── failed
                         └── partial
```

- `planned`：只生成计划和 task 清单，不执行。
- `queued`：已创建，等待执行。
- `running`：至少一个 task 正在执行。
- `succeeded`：所有 task 成功。
- `partial`：部分 task 成功，部分失败或未完成。
- `failed`：没有可用结果，或初始化失败。

### Task 状态

```text
pending -> running -> succeeded
                   ├── failed
                   └── skipped
```

`resume` 只能把 `pending` 或 `failed` task 重新放回可执行集合；不得修改 task 的输入快照、物理参数、资源设置或输出路径。

## 数据文件

### `manifest.json`

记录不会随进度变化的事实：

```json
{
  "job_id": "job_20260618_183000_geometry_smoke",
  "created_at": "2026-06-18T18:30:00+08:00",
  "mode": "mock",
  "job_type": "geometry-smoke",
  "idempotency_key": "optional-user-key",
  "request_hash": "sha256...",
  "code_version": "git-sha",
  "rpc_api_version": "v1",
  "paths": {
    "job_dir": "jobs/job_...",
    "tasks_dir": "jobs/job_.../tasks",
    "models_dir": "jobs/job_.../models",
    "results_dir": "jobs/job_.../results",
    "evidence_dir": "jobs/job_.../evidence"
  },
  "approval": {
    "approved": false,
    "approved_for": null
  }
}
```

### `status.json`

记录可变进度：

```json
{
  "job_id": "job_...",
  "state": "running",
  "message": "Running task_0001.",
  "task_counts": {
    "total": 2,
    "pending": 1,
    "running": 1,
    "succeeded": 0,
    "failed": 0,
    "skipped": 0
  },
  "started_at": "2026-06-18T18:31:00+08:00",
  "updated_at": "2026-06-18T18:31:05+08:00",
  "finished_at": null
}
```

### `tasks/<task_id>.json`

每个 task 独立记录：

```json
{
  "task_id": "task_0001",
  "state": "succeeded",
  "mode": "mock",
  "operation": "geometry-smoke",
  "input": {
    "hide": false
  },
  "outputs": {
    "model_file": "jobs/job_.../models/task_0001.fsp"
  },
  "error": null,
  "attempts": 1,
  "created_at": "2026-06-18T18:30:00+08:00",
  "updated_at": "2026-06-18T18:31:05+08:00"
}
```

## RPC API

### `POST /jobs/plan`

只校验请求、展开 task 清单并落盘，不执行真实任务。响应：

```json
{
  "ok": true,
  "job_id": "job_...",
  "state": "planned",
  "task_count": 2,
  "job_dir": "jobs/job_..."
}
```

### `POST /jobs/start`

创建并执行 job。第一版支持：

- `mode=mock`：不启动 FDTD，只写 task 状态和 summary。
- `mode=real` + `job_type=geometry-smoke`：执行短 GUI/model/save smoke，作为状态机接真实 RPC 的最小验证。

`mode=real` 必须包含：

```json
{
  "approval": {
    "approved": true,
    "approved_for": "real_run"
  }
}
```

否则返回 HTTP 403，`error.type=approval_required`。

### `GET /jobs/<job_id>`

读取 `manifest.json`、`status.json` 和 `summary.json` 摘要。

### `GET /jobs/<job_id>/tasks`

列出 task JSON 的轻量摘要；默认不回传 `.fsp` 或大结果。

### `POST /jobs/<job_id>/resume`

读取磁盘状态，选择 `pending` 和 `failed` task 重新执行。必须校验当前请求的物理参数 hash 与原 `request_hash` 一致；不一致返回 HTTP 409，`error.type=resume_conflict`。

## 执行模型

第一版以简单同步执行为主，但 API 语义按异步 job 设计：

- `plan` 立即返回。
- `mock` 可以同步完成。
- `real geometry-smoke` 是短任务，可同步完成；响应仍返回 `job_id`，真实状态从磁盘读取。

长任务异步线程、取消和队列留到第二版。这样第一版可以先验证落盘状态、幂等、审批和恢复语义，避免同时处理线程调度和真实仿真复杂性。

## 幂等规则

- 如果请求带 `idempotency_key`，Server 在 `jobs/index.json` 中查找同 key。
- 若 key 存在且 `request_hash` 相同，返回已有 job。
- 若 key 存在但 `request_hash` 不同，返回 HTTP 409，`error.type=idempotency_conflict`。
- 无 key 时每次创建新 job。

`jobs/index.json` 只保存轻量映射：

```json
{
  "idempotency_keys": {
    "user-key": {
      "job_id": "job_...",
      "request_hash": "sha256..."
    }
  }
}
```

## 错误处理

- 参数错误：HTTP 400，`validation_error`。
- 真实运行缺审批：HTTP 403，`approval_required`。
- job 不存在：HTTP 404，`job_not_found`。
- 幂等冲突：HTTP 409，`idempotency_conflict`。
- resume 物理参数不一致：HTTP 409，`resume_conflict`。
- task 执行失败：job 进入 `partial` 或 `failed`，task JSON 写入结构化 `error`。

所有响应继续使用 RPC API v1 envelope：成功 `{"ok": true, ...}`，失败 `{"ok": false, "error": {...}}`。

## 测试计划

新增离线测试，不依赖 Lumerical：

1. `JobStore` 创建目录结构和基础 JSON。
2. `plan` 只落盘不执行 task。
3. `mock start` 写入 succeeded task、status 和 summary。
4. `real start` 缺审批返回 403。
5. 幂等 key 相同请求复用 job。
6. 幂等 key 相同但 request 不同返回 409。
7. `resume` 只选择 `pending`/`failed` task。
8. RPC endpoint 保持 v1 envelope。

可选 Windows 验证：

1. 同步代码并本地重启 `5004`。
2. 调用 `POST /jobs/start`，`mode=real`，`job_type=geometry-smoke`。
3. 确认生成 job 目录、`.fsp`、summary，并且 final health 为 `connected=false`。

## 验收标准

- Mac 离线测试全部通过。
- `jobs/` 已加入 `.gitignore`。
- 重启 RPC Server 后，已有 job 可通过 `GET /jobs/<job_id>` 读取。
- 无审批的 `real` 请求被拒绝。
- 相同幂等 key 不重复创建 job。
- `resume` 不修改原始 request hash。
- 第一版代码不触碰旧 `5003` sweep 服务逻辑。
