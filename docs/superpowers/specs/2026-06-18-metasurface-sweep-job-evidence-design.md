# 原生 Metasurface Sweep Job 设计

## 决策

新项目不再调用、修复或依赖旧 Autosweep RPC 服务。

开发和真实 2×2 验证期间，新 API v1 服务继续使用 `5004`。原生 sweep 通过验证后，将新项目管理脚本和 Server 的默认端口切换为 `5000`。

旧项目只允许作为一次性的已验证算法与模板来源。模板复制进新项目后，运行时不得读取旧项目目录、端口或结果服务。

## 背景

当前新项目已经具备：

- API v1 session/model/geometry/debug 端点。
- 持久 `/jobs/*`、审批、幂等和 resume 地基。
- `geometry-smoke` 真实验证。
- `metasurface-sweep` 的 mock、质量报告和 evidence index。

此前的 bridge 方案证明了 job/task 与证据链可用，但真实执行仍依赖旧 RPC，继承了陈旧会话、错误健康检查、启动脚本和目录耦合等问题。新路线将四阶段 sweep 直接实现到新项目中。

## 目标

1. `5004` 直接通过当前 `SessionManager` 和 raw lumapi 执行 metasurface sweep。
2. 每个参数点映射为一个持久 sample task，支持逐样本状态、证据和 resume。
3. `real metasurface-sweep` 异步启动，立即返回 `202 + job_id`，不让 HTTP 请求等待求解。
4. 原生执行四阶段：
   - Phase 1：从只读模板生成逐点 `.fsp` 并加入 FDTD job queue。
   - Phase 2：统一执行 `runjobs()`。
   - Phase 3：逐点提取 `T` 和 `S21_Gn` 相位。
   - Phase 4：用新项目自身的 Python 后处理生成 CSV/JSON 和关键 SVG，不依赖旧 MATLAB 脚本。
5. 每个完成 job 生成 `summary.json`、`quality_report.json` 和 `evidence/index.json`。
6. 真实 2×2、phases `[1,2,3,4]` 验证通过后，将默认服务端口从 `5004` 切换为 `5000`。

## 非目标

- 不继续修复旧 Autosweep RPC。
- 不调用旧项目的 `/sweep/*`、`/results/*` 或任何端口。
- 不实现优化算法、取消队列、多机调度或多个并行 real job。
- 不自动扩大参数范围、修改 mesh/boundary 或改变模板物理设置。
- 不默认回传所有逐点 `.fsp`。

## 模板迁移

新项目使用：

```text
templates/metasurface/base_model.fsp
templates/metasurface/README.md
```

约束：

- `.fsp` 继续被 Git 忽略，不提交大二进制。
- Windows 初次部署时，将已验证模板复制到新项目目录。
- `manifest.json` 记录模板绝对路径、文件大小、修改时间和 SHA-256。
- executor 只读模板；逐点模型写入 `jobs/<job_id>/models/`。
- 模板必须包含：
  - `FDTD`
  - `::model`
  - `::model::s_params`
  - `::model` 的 `ratio`、`height`、`period` 属性。

## 请求模型

```json
{
  "mode": "real",
  "job_type": "metasurface-sweep",
  "idempotency_key": "optional-key",
  "sweep": {
    "config": {
      "SWEEP_Y_AXIS": "period",
      "RATIO_LIST": [0.2, 0.8],
      "PERIOD_LIST": [3.9e-7, 5.4e-7],
      "BASE_HEIGHT": 7e-7,
      "BASE_PERIOD": 4.7e-7,
      "FDTD_PROCESSES": 1,
      "FDTD_CAPACITY": 1
    },
    "phases": [1, 2, 3, 4],
    "hide": true,
    "template": "templates/metasurface/base_model.fsp",
    "include_models": false
  },
  "approval": {
    "approved": true,
    "approved_for": "real_run"
  }
}
```

兼容简写：

- 如果只提供 `RATIO_PTS` 和 `PERIOD_PTS`，系统用安全默认边界生成列表。
- `phases` 默认 `[1,2,3]`。
- `hide` 默认 `true`。
- `include_models` 默认 `false`。

## Sample Task 模型

每个参数点对应一个 task：

```json
{
  "task_id": "task_0001",
  "operation": "metasurface-sample",
  "state": "pending",
  "phase": "pending",
  "input": {
    "ratio": 0.2,
    "height": 7e-7,
    "period": 3.9e-7,
    "sample_index": 0
  },
  "outputs": {
    "model_file": "...",
    "result_file": "...",
    "transmission": 0.0,
    "phase_rad": 0.0
  }
}
```

task 状态仍使用 `pending | running | succeeded | failed | skipped`。新增 `phase` 字段记录 `generating | queued | solving | extracting | complete`，不扩大顶层状态枚举。

## 执行架构

新增 `NativeSweepRunner`，由一个 real sweep 后台线程调用。

### 启动

1. `/jobs/start` 校验审批、模板和参数预算。
2. `JobStore` 先创建 job 与全部 sample task。
3. Server 返回 HTTP 202，包含 `job_id`、task 数和审批摘要。
4. 后台线程获取单机 sweep 锁并执行。
5. 同一时间只允许一个 real metasurface sweep；有活动 sweep 时拒绝新 real sweep，不创建重复求解。

### Phase 1

1. 若没有可用 FDTD 会话，启动 `hide=true` 会话。
2. 调用 `clearjobs()` 和 `redrawoff()`。
3. 设置 processes/capacity；不支持时记录 warning。
4. 对选中的 pending/failed task：
   - `load(template)`
   - `switchtolayout()`
   - 每次 load 后设置 `express mode=1`
   - 设置 `ratio/height/period`
   - 保存到 `jobs/<job_id>/models/<task_id>.fsp`
   - `addjob(model_path)`
   - task phase 更新为 `queued`

### Phase 2

1. 对本轮加入队列的模型统一 `runjobs()`。
2. task phase 更新为 `solving`。
3. HTTP/MCP 不同步等待。

### Phase 3

对本轮 task：

1. 加载逐点模型。
2. 执行 `runanalysis("::model::s_params")`。
3. 读取 `T` 和 `S21_Gn`。
4. 写 `results/<task_id>.json`。
5. 成功 task 标记 `succeeded/complete`；单点失败标记 `failed`，不丢失其他点。

### Phase 4

新项目用 Python 生成：

- `results/sweep_results.csv`
- `results/sweep_summary.json`
- `evidence/transmission_heatmap.svg`
- `evidence/phase_heatmap.svg`

SVG 使用标准库直接生成，避免给 Windows Lumerical Python 增加 matplotlib 依赖。

## JobStore 扩展

新增受控公共方法，避免 runner 直接散乱修改 JSON：

- `enqueue(request) -> job`
- `execute(job_id, runner)`
- `update_task(job_id, task_id, ...)`
- `append_log(job_id, message)`
- `recover_interrupted_jobs()`

`recover_interrupted_jobs()` 在 Server 启动时：

- 将残留 `running` job 改为 `partial`。
- 将残留 `running` task 改为 `failed`。
- error type 为 `interrupted`。
- 不自动重新求解，等待显式 `/resume`。

## Resume

`POST /jobs/<job_id>/resume`：

- 只选择 `pending/failed` sample task。
- 使用原 manifest、模板指纹和物理参数。
- 不覆盖已成功 task 的结果。
- 重新生成并求解选中样本。
- 模板指纹变化时拒绝 resume，要求创建新 job。

## 质量报告

`quality_report.json` 包含：

- solver/job 完成状态。
- requested/succeeded/failed/missing 数量。
- transmission 数值有限性。
- 无源器件基础范围检查：明显超出 `[0,1]` 标记 warning/fail。
- 参数网格完整性。
- 异常跳变标记。
- `conclusion: pass | warning | fail`
- `requires_human_review: true`

solver 完成不等于物理通过。

## Evidence-first

默认 API 返回：

- manifest/status/summary
- task 摘要
- 每点标量结果
- quality report
- 两张 SVG
- evidence index

默认不返回逐点 `.fsp` 内容。`include_models=true` 只让 evidence index 列出模型路径。

## 并发和会话安全

- 所有 real sweep 使用进程内单一 sweep 锁。
- sweep 运行时拒绝通用 session/model/geometry 的破坏性操作，避免共享会话被修改。
- FDTD cleanup 可超时；job 事实状态以磁盘为准。
- mock 不获取 FDTD 锁。

## 错误处理

- 模板缺失或结构不合格：启动前 HTTP 400，不消耗真实求解。
- real 未审批：HTTP 403。
- 已有 real sweep：HTTP 409。
- 单点失败：task failed，job partial。
- 全部失败：job failed。
- 服务退出：启动恢复为 interrupted，允许显式 resume。
- Phase 4 失败但标量结果完整：job partial 或 quality warning，保留 Phase 3 结果。

## 端口迁移

阶段 A：

- 开发和离线测试：`5004`。
- Windows 真实 2×2：`5004`。

阶段 B，仅在 2×2 的 phases `[1,2,3,4]`、质量报告和 evidence 全部验证后：

- `scripts/windows/manage_rpc.ps1` 默认端口改为 `5000`。
- `rpc_server.py` CLI 默认端口改为 `5000`。
- 文档和 smoke 默认地址改为 `5000`。
- 最后在 `5000` 跑 health 与 mock smoke；不未经新审批重复真实 sweep。

## 测试策略

离线：

1. 参数网格展开为稳定 sample task。
2. async start 返回 202，不同步执行 solver。
3. fake lumapi 验证 Phase 1 顺序：`clearjobs → load → express mode → set parameters → save → addjob`。
4. fake lumapi 验证 batch `runjobs()` 只调用一次。
5. Phase 3 独立记录成功与失败样本。
6. resume 只选择 pending/failed。
7. interrupted recovery。
8. quality report 和 SVG/evidence。
9. sweep 锁和破坏性端点保护。

Windows：

1. 复制并指纹记录模板。
2. `5004` mock 2×2。
3. 明确审批后 `5004` real 2×2，phases `[1,2,3,4]`。
4. 核验 4 个 sample task、4 个模型、4 个标量结果、CSV、两张 SVG、quality report 和 evidence index。
5. 通过后切默认端口到 `5000`。
6. `5000` health 与 mock smoke。

## 验收标准

- 新项目运行时不访问旧 Autosweep 端口或目录。
- real start 在 2 秒内返回 `202 + job_id`。
- 2×2 真实 sweep 为 4 个独立 sample task。
- 服务重启后状态仍可读，interrupted task 可显式 resume。
- 质量报告与 evidence-first 产物齐全。
- 最终新服务默认端口为 `5000`。
