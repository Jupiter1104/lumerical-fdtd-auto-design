# Lumerical FDTD 自动化开发

## 项目用途

本项目用于开发 Lumerical FDTD/FDE/EME 光学仿真器的自动化脚本和工具链。通过 Python `lumapi` 接口驱动 Lumerical 求解器，实现参数化扫描、优化、版图生成和结果后处理的自动化流程，减少手动 GUI 操作的重复劳动，提高光子器件设计的迭代效率。

典型应用场景包括但不限于：光波导模式求解、光栅耦合器优化、微环谐振器设计、MMI 分束器、逆向设计等。

## 当前状态

- 阶段：个人 FDTD MCP 0.1.0 已完成技术交付验收；当前目标是可复用 MCP 能力，不以 C3/C4 真实 sweep 或物理结果作为交付前置条件
- 文档基线：2026-06-20 — API v1、持久 job/task、SimulationPlan、DeviceRecipe/Generic SweepPlan、0.1.0 MCP 验收、C3 packet 和飞书通知已对齐到当前事实
- 已验证基础：Mac → SSH Tunnel/HTTP → Windows v242 → Stage C1 真实 2×2 SimulationPlan sweep，结果 4/4 valid；Stage C2 evidence review 软件链 `pass`
- 当前代码状态：仓库内通用 `rpc_server.py`、Mac `RpcClient` 和 MCP 已统一为 API v1；Windows `5004` 已完成真实 2×2 原生 `metasurface-sweep` 验证，结果 4/4 valid、quality `pass`。新服务默认端口已提升为 `5000`；`metasurface-sweep` 由 `/jobs/start` 异步返回 `202 + job_id`，包含 Phase 1-4、quality report 和 evidence index。
- 注意：旧 Autosweep 只作为历史 baseline，不再是新 `rpc_server.py` 的运行时依赖。
- MCP Server 已形成 69-tool 0.1.0 工具面，覆盖 project/object/material/solver/source/monitor/analysis/result、DeviceRecipe、Generic SweepPlan、SimulationPlan、persistent jobs、raw eval/getv/setv 和知识工具。
- SimulationPlan v0.1 已支持 metasurface unit-cell：默认值披露、任务预算、SHA-256 指纹、Plan 审批、mock 编译和 MCP 执行。
- DeviceRecipe 的 `analysis_groups[]` 已支持官方 Object Library 优先路径：有已确认 `script_id` 时用 `addobject("script_id")`，无 ID 时按策略回退或报错；Agent 不得猜测官方库 ID。
- mock 前必须批准默认值和假设；real 还需要匹配同一 Plan 指纹的真实运行审批与模板契约。
- real metasurface resume 会重新校验模板 SHA-256；模板变化时拒绝恢复。
- 可选物理工作流保留 C3 包 `runtime/approvals/production_sweep_c3_packet.json`：`status=ready_for_human_approval`、`task_count=25`；该包未获单独批准，不得启动 C4。
- 持久 job 飞书通知已通过 Windows mock smoke 验证，不启动 FDTD。Agent 提交长任务并取得 `job_id` 后默认停止轮询，用户收到终态通知后再要求读取结果。
- Windows minimal solver smoke 已通过：`technical_smoke=true`、`physical_conclusion=false`、`ok=true`，14/14 步完成，产物包含 `smoke_model.fsp`、`smoke_report.json` 和 `downloaded_results.json`。
- 当前基础设施已覆盖计划、审批、持久执行、恢复、质量报告、evidence-first 和终态通知。后续优先推进真实设计工作流；没有具体缺口时不继续扩建基础设施。

## 核心文档

- `AGENTS.md`：项目专属代理规则。
- `REQUIREMENTS.md`：目标、范围、非目标和验收标准。
- `TECH_STACK.md`：技术栈、命令、服务和依赖。
- `DEV_LOG.md`：按日期记录的开发日志。
- `PITFALLS.md`：项目专属错误和修复方案。
- `SOP.md`：项目内可重复执行的流程。
- `RETROSPECTIVE.md`：复盘记录和可复用经验。
- `docs/RPC_API_V1.md`：API v1 路由、错误语义和兼容别名。
- `docs/WINDOWS_RUNBOOK.md`：Windows 本地启动、同步、smoke 与故障排查。
- `docs/MCP_USER_GUIDE.md`：个人安装、三客户端配置、69-tool 能力面和运行模式。
- `docs/FDTD_OPERATIONS_V1.md`：通用 FDTD 操作闭环与 analysis group 官方库优先用法。
- `docs/DEVICE_RECIPE_V1.md`：论文/自然语言结构化后的器件 Recipe 契约。
- `docs/GENERIC_SWEEP_PLAN_V1.md`：通用扫参计划、任务展开和指纹约束。
- `templates/metasurface/README.md`：原生 metasurface sweep 模板安装与结构要求。

`docs/superpowers/specs/` 和 `docs/superpowers/plans/` 是历史设计与执行档案，不作为新人启动入口；当前事实以上述入口文档和代码为准。

## 目标操作链

```text
自然语言需求
  -> 结构化 SimulationPlan
  -> plan 校验与成本预览
  -> 可选 mock 软件链验证
  -> 明确批准 real
  -> Windows 异步 job/task 执行
  -> Agent 返回 job_id 后停止轮询
  -> 飞书终态通知
  -> 结果提取与质量报告
  -> 人工物理审核
  -> 建议下一轮，不自动扩大计算
```
