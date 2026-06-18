# Metasurface Sweep Job Evidence 设计

## 背景

当前项目有两条已经验证过的链路：

- 旧 `5003` Autosweep 服务：已经跑通过 metasurface 4 点真实 sweep，包含 `.fsp` 生成、并行求解、S 参数提取和 MATLAB 后处理经验。
- 新 `5004` API v1 服务：已经具备 `/jobs/*` 持久 job/task 状态机，并跑通过短 `real geometry-smoke` job。

本阶段目标不是重写旧 sweep 引擎，而是把旧 sweep/后处理能力接入新 `5004` 的持久 job/task 模型，并补齐质量报告与 evidence-first 回传。

## 目标

1. 新增 `job_type="metasurface-sweep"`，支持 `plan`、`mock` 和 `real`。
2. 每个 sweep job 使用稳定的 `jobs/<job_id>/` 目录保存 manifest、status、summary、task、结果索引、质量报告和证据索引。
3. `real` sweep 仍必须经过明确审批，不允许无审批启动真实求解。
4. 首版质量报告区分“求解完成”和“物理质量结论”，结论只允许 `pass`、`warning`、`fail`。
5. 默认回传轻量证据索引，不全量回传逐点 `.fsp`。
6. 保持旧 `5003` 服务可并行运行；新实现优先在 `5004` 内承载迁移后的 job API。

## 非目标

- 不实现新的自然语言器件编译器。
- 不实现优化循环、取消队列或多 job 并发调度。
- 不自动扩大扫描范围、改变 mesh、boundary、scheduler 或物理设置。
- 不把所有 `.fsp` 模型文件作为默认 HTTP 响应或默认下载内容。
- 不删除旧 `5003` 接口；旧服务仍作为已验证 baseline 和回退路径。

## 推荐路线

采用桥接式迁移：

1. 先把 `JobStore` 从单一 `geometry-smoke` 扩展为支持 `metasurface-sweep`。
2. 新增一个 sweep job 适配层，负责把 request 转成 job task、执行结果、summary、quality report 和 evidence index。
3. mock 模式使用合成结果验证状态机和报告链，不调用 Lumerical。
4. real 模式在 `5004` 进程内调用迁移后的 sweep executor；如果旧完整执行逻辑暂时不可离线测试，则用薄接口隔离，测试只覆盖接口契约和产物写入。

这条路线最小化风险：先让持久状态机接管运行记录与证据，再逐步把旧 sweep 的内部代码迁入或封装。

## 请求模型

`/jobs/plan` 和 `/jobs/start` 接收：

```json
{
  "mode": "mock",
  "job_type": "metasurface-sweep",
  "idempotency_key": "optional-key",
  "sweep": {
    "config": {
      "SWEEP_Y_AXIS": "period",
      "RATIO_PTS": 2,
      "PERIOD_PTS": 2,
      "FDTD_PROCESSES": 1,
      "FDTD_CAPACITY": 1
    },
    "phases": [1, 2, 3],
    "hide": true,
    "template": "base_model.fsp",
    "include_models": false
  },
  "approval": {
    "approved": false,
    "approved_for": null
  }
}
```

字段约定：

- `mode`: `plan | mock | real`。
- `job_type`: `geometry-smoke | metasurface-sweep`。
- `sweep.config`: 旧 Autosweep 配置子集；首版至少支持 `SWEEP_Y_AXIS`、`RATIO_PTS`、`PERIOD_PTS`、`FDTD_PROCESSES`、`FDTD_CAPACITY`。
- `sweep.phases`: 默认 `[1, 2, 3]`；包含 `4` 时表示请求 MATLAB 后处理。
- `sweep.hide`: 生产默认 `true`，GUI 调试可设 `false`。
- `sweep.include_models`: 默认 `false`；只影响 evidence index 是否列出逐点 `.fsp` 调试资产，不改变默认 API 响应大小。
- `approval`: `real` 模式必须为 `{"approved": true, "approved_for": "real_run"}`。

## Task 模型

首版把一个 metasurface sweep job 表示为一个高层 task：

```json
{
  "task_id": "task_0001",
  "operation": "metasurface-sweep",
  "input": {
    "config": {},
    "phases": [1, 2, 3],
    "hide": true,
    "template": "base_model.fsp",
    "include_models": false
  }
}
```

原因：旧 sweep 引擎内部已经管理逐点样本、求解和提取。现在先把“整个 sweep 流水线”作为可恢复的高层 task 记录，避免在首版里重写 sample-level 调度。

后续如果要支持逐 sample resume，再把旧内部 sample 映射成多个 `tasks/task_XXXX.json`。

## 输出文件

每个 sweep job 至少生成：

```text
jobs/<job_id>/
├── manifest.json
├── status.json
├── summary.json
├── quality_report.json
├── run.log
├── inputs/
│   └── request.json
├── tasks/
│   └── task_0001.json
├── results/
│   ├── sweep_summary.json
│   └── ...
└── evidence/
    └── index.json
```

`summary.json` 需要包含：

- `task_counts`
- `results`
- `quality_report`
- `evidence`

`quality_report.json` 需要包含：

- `job_id`
- `generated_at`
- `solver_status`
- `result_completeness`
- `physical_checks`
- `conclusion`
- `requires_human_review`

`evidence/index.json` 需要包含：

- `job_id`
- `generated_at`
- `summary_files`
- `result_files`
- `figure_files`
- `model_files`
- `download_policy`

默认 `download_policy.include_models` 为 `false`。

## 质量门

首版质量门保持保守：

- `fail`：task 失败、无结果摘要、`valid_count == 0`、或存在明确错误。
- `warning`：有缺失样本、未运行后处理、缺少可视化、或物理检查不足。
- `pass`：solver 成功、结果完整、没有缺失样本、基础物理检查未触发失败。

无论结论如何，`requires_human_review` 都为 `true`。Agent 只产出证据与建议，不宣称物理最终正确。

## Evidence-first 回传

`GET /jobs/<job_id>` 默认返回轻量信息：

- manifest
- status
- summary
- quality report 摘要或路径
- evidence index 摘要或路径

不把逐点 `.fsp`、大 `.mat` 或大图片直接塞进 JSON 响应。下载大文件仍走显式结果下载或后续专门的 evidence 下载端点。

## RPC 路由影响

首版继续使用已有路由：

- `POST /jobs/plan`
- `POST /jobs/start`
- `GET /jobs/<job_id>`
- `GET /jobs/<job_id>/tasks`
- `POST /jobs/<job_id>/resume`

不新增外部路由，避免 API 面膨胀。`RpcClient.jobs_*` 方法继续可用。

## 错误处理

- 不支持的 `job_type` 返回 HTTP 400 `validation_error`。
- `real` 缺少审批返回 HTTP 403 `approval_required`。
- 幂等键冲突返回 HTTP 409 `idempotency_conflict`。
- sweep executor 失败不抛出为 HTTP 500；它应落到 task `failed`、job `failed/partial`，并写入 `quality_report.json`。
- HTTP 超时仍表示远端状态未知，用户应通过 `GET /jobs/<job_id>` 读取磁盘状态。

## 测试策略

离线测试优先：

1. `JobStore` 能 plan/start `metasurface-sweep`。
2. mock sweep 生成 `summary.json`、`quality_report.json`、`evidence/index.json`。
3. mock sweep 的 quality report 在完整结果时为 `pass`，缺失结果时为 `warning/fail`。
4. real sweep 缺少审批被拒绝。
5. Flask `/jobs/*` 对 `metasurface-sweep` 返回稳定 v1 envelope。
6. `RpcClient` 不需要新增方法，但现有 `jobs_*` 能透传新 job type。

真实验证：

1. Windows clone `git pull --ff-only`。
2. 用户本地双击 `scripts\windows\restart_rpc.bat`。
3. Mac 通过 HTTP/SSH 触发短 `real metasurface-sweep`，建议先跑 2x2、phases `[1,2,3]`。
4. 核验 job state、task state、`summary.json`、`quality_report.json`、`evidence/index.json` 和旧 sweep 结果文件。

## 后续扩展

- 把旧 sweep 内部每个样本映射为独立 task，实现 sample-level resume。
- 增加 `/jobs/<id>/evidence` 或 `/evidence/<path>` 专用下载端点。
- 将质量报告中的物理检查从基础完整性扩展到 S 参数守恒、异常跳变和曲线可视化。
- MCP 工具层新增 `fdtd_job_plan/start/status/tasks/resume`，让 Claude Code/Hermes 直接操作新 job API。
