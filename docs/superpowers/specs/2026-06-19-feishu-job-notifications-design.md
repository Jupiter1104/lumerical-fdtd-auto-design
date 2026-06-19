# 持久 Job 飞书终态通知设计

## 目标

真实或模拟仿真提交后，Agent 只需返回 `job_id`，不再持续轮询和消耗上下文。持久 job 到达应通知的状态后，由 Windows RPC 服务主动发送飞书消息；用户收到消息后再让 Agent 读取并分析结果。

本功能仅通知已经创建持久 `job_id` 的 `plan`、`mock`、`real` job。普通 SimulationPlan 校验、审批和本地 preflight 不通知。

## 范围

### 包含

- `plan` job 创建并稳定进入 `planned` 后通知。
- `mock`、`real` job 进入 `succeeded`、`failed` 或 `partial` 终态后通知。
- 从环境变量 `FDTD_FEISHU_WEBHOOK` 读取飞书自定义机器人 Webhook。
- 使用 Python 标准库发送飞书 `text` 消息。
- 通知结果和失败原因写入 job 的 `run.log`。
- 同一 job、同一通知状态最多成功发送一次。

### 不包含

- 不通知无 `job_id` 的校验、审批或 preflight。
- 不增加数据库、消息队列、定时轮询服务、MCP 工具或第三方依赖。
- 不自动下载结果、不自动分析物理结果、不自动启动下一轮仿真。
- 不把 Webhook 写入 Git、请求 JSON、manifest 或配置文件。
- 不复制旧项目的 `DONE` / `FAILED` 标记；新项目继续以 `status.json` 为状态事实来源。

## 架构

新增独立模块 `src/job_notifications.py`，负责：

1. 构建通知文本。
2. 从环境变量读取 Webhook。
3. 通过 `urllib.request` 发送 HTTP POST。
4. 记录通知是否已经成功发送。
5. 将发送、跳过或失败结果追加到 `run.log`。

`JobStore` 仍负责持久状态，不负责飞书协议细节。它只在两个明确位置调用通知模块：

- `_create_job()`：当持久 `plan` job 已完成落盘后，尝试发送 `planned` 通知。
- `finalize()` 和内部 `_run_job()` 的统一终态路径：在状态、summary 和 quality report 已完成落盘后，尝试发送终态通知。

若代码中存在两条终态路径，二者可以调用同一幂等通知函数；通知记录负责消除重复发送。

## 通知幂等性

每个 job 目录新增：

```text
notifications.json
```

文件只保存通知元数据，不保存 Webhook。建议结构：

```json
{
  "planned": {
    "sent": true,
    "sent_at": "2026-06-19T15:00:00+00:00"
  },
  "succeeded": {
    "sent": true,
    "sent_at": "2026-06-19T16:00:00+00:00"
  }
}
```

规则：

- 只有飞书接口成功返回后才记录 `sent=true`。
- Webhook 缺失或网络失败不标记成功，保留以后人工重试的可能。
- 已成功记录的相同状态再次触发时直接跳过。
- `planned` 和最终状态是不同通知键，因此 plan job 只收到一次 `planned`；mock/real 不发送 queued/running 通知。

## 通知内容

消息使用飞书机器人 `text` 类型：

```json
{"msg_type": "text", "content": {"text": "..."}}
```

计划 job 示例：

```text
FDTD job planned
mode: plan
job: job_...
tasks: 25 total
job_dir: F:\...\jobs\job_...
```

终态示例：

```text
FDTD job succeeded
mode: real
job: job_...
tasks: 25 succeeded / 0 failed / 25 total
quality: pass
job_dir: F:\...\jobs\job_...
```

失败或 partial 消息沿用相同结构，并显示失败数量。若 job 没有 `quality_report.json`，显示 `quality: unavailable`，不把通知本身判为失败。

## 错误处理

- `FDTD_FEISHU_WEBHOOK` 未设置：跳过并写日志，不影响 job。
- HTTP、DNS、超时或飞书返回错误：捕获异常并写日志，不影响 job。
- 通知记录损坏：按未成功发送处理并写日志，不影响 job 状态文件。
- 通知函数不得抛出异常到仿真执行线程。
- 默认 HTTP 超时为 10 秒，避免飞书网络问题长期占用 job 线程。

## Agent 工作流变化

真实或模拟长任务的默认交互改为：

```text
Agent 提交 job
→ 返回 job_id、模式和“等待飞书通知”
→ Agent 停止轮询并结束当前工作
→ Windows 独立执行
→ job 到达终态后发送飞书
→ 用户回来让 Agent 读取并分析结果
```

只有用户明确要求“现在检查进度”时，Agent 才执行一次只读状态查询，不自动进入持续监控。

## 配置

Windows 用户环境变量：

```powershell
setx FDTD_FEISHU_WEBHOOK "https://open.feishu.cn/open-apis/bot/v2/hook/你的Webhook"
```

设置后必须重启 RPC 服务，使 `pythonw.exe` 继承新环境变量。

Webhook 不得出现在测试输出、日志、异常文本或版本库中。

## 测试

新增纯离线测试，使用 mock 替代真实 HTTP：

- 持久 plan job 发送一次 `planned` 通知。
- mock succeeded 发送终态通知。
- real succeeded 发送终态通知。
- failed 和 partial 均发送终态通知。
- queued/running 不通知。
- 无 Webhook 时安全跳过。
- HTTP 失败不改变 job 终态。
- 同一状态重复触发只成功发送一次。
- 通知文本包含 mode、job ID、task counts、quality 和 job directory。
- 通知记录不包含 Webhook。

全量测试不得访问飞书网络，也不得启动 FDTD。

## 验收标准

1. `plan`、`mock`、`real` 的持久 job 都按上述规则发送通知。
2. 一个 mock/real job 的同一最终状态最多成功通知一次。
3. 通知不可用时 job 仍能正常进入正确终态。
4. Agent 提交长任务后无需轮询。
5. 实现只使用标准库，且 Webhook 不落盘、不入 Git。
6. Windows 设置环境变量并重启服务后，可以用一个持久 plan/mock job 完成真实飞书 smoke test；该 smoke 不启动 FDTD 求解。

